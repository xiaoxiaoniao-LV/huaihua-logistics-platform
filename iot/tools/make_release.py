"""生成固件发布包（文件级 OTA 的服务端产物）。

用法（仓库根目录执行）：
    python iot/tools/make_release.py 3.1.0
    python iot/tools/make_release.py 3.1.0 --sign-key <32字节种子 hex/base64>
    OTA_SIGNING_KEY=<种子> python iot/tools/make_release.py 3.1.0

产物：iot/firmware/releases/<version>/
    manifest.json   {"version": "...", "files": [{"name", "size", "sha256"}],
                     "signature": "...", "signature_alg": "ed25519"}
    main.py / ota.py / ...  待分发的逻辑文件

签名：
- 私钥只在本机打包时使用，绝不进入服务端运行环境或设备；
- 签名载荷为规范化 JSON（files 按 name 升序、键排序、无空格），与
  `backend/app/services/ota_signing.py`、`iot/firmware/ed25519.py` 完全一致；
- 生成后请把打印的公钥写入 backend/.env 的 OTA_PUBLIC_KEY 与固件 config.py。

规则：
- 自动收集 firmware 目录下所有 .py，但排除 config.py / boot.py（节点身份与启动配置）；
- 只生成清单和副本，不修改源文件；重复执行会覆盖同版本目录。
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "firmware"
RELEASES_DIR = FIRMWARE_DIR / "releases"

# 复用固件端的 Ed25519 实现，保证签名/验签的规范化规则逐字节一致
sys.path.insert(0, str(FIRMWARE_DIR))
import ed25519  # noqa: E402

# 与 backend/app/routers/devices.py 的 _FW_VERSION_RE 保持一致
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,19}$")

# 与 backend/app/routers/devices.py 的 _FW_EXCLUDED_FILES 保持一致
EXCLUDED = {"config.py", "boot.py", "make_release.py"}


def collect_files():
    files = []
    for path in sorted(FIRMWARE_DIR.glob("*.py")):
        if path.name in EXCLUDED or path.name.endswith(".new"):
            continue
        files.append(path)
    if not files:
        raise SystemExit("firmware 目录下没有可发布的 .py 文件")
    return files


def _decode_seed(text: str) -> bytes:
    """把 32 字节种子从 hex 或 base64 解出。"""
    text = text.strip()
    candidates = []
    try:
        candidates.append(bytes.fromhex(text))
    except ValueError:
        pass
    try:
        candidates.append(base64.b64decode(text + "=" * (-len(text) % 4)))
    except Exception:
        pass
    for raw in candidates:
        if len(raw) == 32:
            return raw
    raise SystemExit("签名种子必须是 32 字节（hex 64 位或 base64）")


def build(version: str, sign_key: str | None = None) -> Path:
    out_dir = RELEASES_DIR / version
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for src in collect_files():
        data = src.read_bytes()
        (out_dir / src.name).write_bytes(data)
        entries.append({
            "name": src.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    manifest = {"version": version, "files": entries}
    if sign_key:
        seed = _decode_seed(sign_key)
        signature = ed25519.sign(seed, ed25519.canonical_payload(manifest))
        manifest["signature"] = base64.b64encode(signature).decode()
        manifest["signature_alg"] = "ed25519"
        manifest["public_key"] = base64.b64encode(ed25519.public_key(seed)).decode()

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


def main():
    parser = argparse.ArgumentParser(description="生成固件发布包")
    parser.add_argument("version", help="目标版本号，如 3.1.0")
    parser.add_argument(
        "--sign-key",
        default=os.environ.get("OTA_SIGNING_KEY", ""),
        help="Ed25519 私钥种子（32 字节 hex/base64），也可用环境变量 OTA_SIGNING_KEY",
    )
    args = parser.parse_args()

    version = args.version.strip()
    if not VERSION_RE.match(version):
        raise SystemExit("版本号只能包含字母、数字、点、下划线、短横线（1~20 位）")

    out_dir = build(version, args.sign_key.strip() or None)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"发布目录: {out_dir}")
    for item in manifest["files"]:
        print(f"  {item['name']:<12} {item['size']:>7} B  {item['sha256'][:16]}...")
    if manifest.get("signature"):
        print("清单已签名（ed25519）")
        print("公钥（写入 backend/.env 的 OTA_PUBLIC_KEY 与固件 config.py）:")
        print("  " + manifest["public_key"])
    else:
        print("警告：未签名清单只能用于调试，生产请用 --sign-key 或 OTA_SIGNING_KEY")
    print("分发时请确认 config.py / boot.py 未被包含（节点专属配置）。")


if __name__ == "__main__":
    main()
