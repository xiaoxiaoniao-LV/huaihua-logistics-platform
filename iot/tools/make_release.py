"""生成固件发布包（文件级 OTA 的服务端产物）。

用法（仓库根目录执行）：
    python iot/tools/make_release.py 3.1.0

产物：iot/firmware/releases/<version>/
    manifest.json   {"version": "...", "files": [{"name", "size", "sha256"}]}
    main.py / ota.py / ...  待分发的逻辑文件

规则：
- 自动收集 firmware 目录下所有 .py，但排除 config.py / boot.py（节点身份与启动配置）；
- 只生成清单和副本，不修改源文件；重复执行会覆盖同版本目录。
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "firmware"
RELEASES_DIR = FIRMWARE_DIR / "releases"

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


def build(version: str) -> Path:
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
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


def main():
    parser = argparse.ArgumentParser(description="生成固件发布包")
    parser.add_argument("version", help="目标版本号，如 3.1.0")
    args = parser.parse_args()

    version = args.version.strip()
    if not VERSION_RE.match(version):
        raise SystemExit("版本号只能包含字母、数字、点、下划线、短横线（1~20 位）")

    out_dir = build(version)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"发布目录: {out_dir}")
    for item in manifest["files"]:
        print(f"  {item['name']:<12} {item['size']:>7} B  {item['sha256'][:16]}...")
    print("分发时请确认 config.py / boot.py 未被包含（节点专属配置）。")


if __name__ == "__main__":
    main()
