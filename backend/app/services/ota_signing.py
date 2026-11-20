"""固件清单签名（Ed25519）。

清单由 `iot/tools/make_release.py` 生成并签名，设备端（MicroPython）用固件内置公钥验签。
签名内容为规范化 JSON（键排序、无空格）：

    {"files":[{"name":"main.py","sha256":"...","size":123}],"version":"3.1.0"}

设备端 `iot/firmware/ed25519.py` 使用完全相同的规范化规则，两边改动必须同步。
"""
import base64
import binascii
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..config import settings


def _normalize_files(manifest: dict) -> list[dict]:
    files = []
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        files.append({
            "name": str(item.get("name", "")),
            "sha256": str(item.get("sha256", "")),
            "size": int(item.get("size") or 0),
        })
    files.sort(key=lambda f: f["name"])
    return files


def canonical_payload(manifest: dict) -> bytes:
    """签名/验签使用的规范化字节串（必须与固件端实现一致）。"""
    doc = {
        "files": _normalize_files(manifest),
        "version": str(manifest.get("version", "")),
    }
    return json.dumps(
        doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _decode_key_bytes(text: str, expect_len: int = 32) -> bytes:
    """解析 hex / base64 / 裸 base64 的密钥字节。"""
    raw = (text or "").strip()
    if len(raw) == expect_len * 2:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    padded = raw + "=" * (-len(raw) % 4)
    try:
        data = base64.b64decode(padded, validate=False)
    except (binascii.Error, ValueError):
        raise ValueError("密钥不是合法的 hex 或 base64")
    if len(data) != expect_len:
        raise ValueError(f"密钥长度应为 {expect_len} 字节，实际 {len(data)}")
    return data


def load_private_key(text: str) -> Ed25519PrivateKey:
    """支持 PEM（PKCS8）或 32 字节种子的 hex / base64。"""
    raw = (text or "").strip().replace("\\n", "\n")
    if not raw:
        raise ValueError("未配置 OTA_SIGNING_KEY")
    if "BEGIN" in raw:
        key = serialization.load_pem_private_key(raw.encode("utf-8"), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("私钥不是 Ed25519")
        return key
    return Ed25519PrivateKey.from_private_bytes(_decode_key_bytes(raw))


def load_public_key(text: str) -> Ed25519PublicKey:
    raw = (text or "").strip().replace("\\n", "\n")
    if not raw:
        raise ValueError("未配置 OTA_PUBLIC_KEY")
    if "BEGIN" in raw:
        key = serialization.load_pem_public_key(raw.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("公钥不是 Ed25519")
        return key
    return Ed25519PublicKey.from_public_bytes(_decode_key_bytes(raw))


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    """私钥派生公钥，输出裸 base64（可直接写入 .env / 固件 config.py）。"""
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def sign_manifest(manifest: dict, private_key_text: str) -> str:
    """返回清单签名（base64）。调用方负责把签名写回 manifest。"""
    key = load_private_key(private_key_text)
    signature = key.sign(canonical_payload(manifest))
    return base64.b64encode(signature).decode("ascii")


def verify_manifest(manifest: dict, public_key_text: str | None = None) -> tuple[bool, str]:
    """校验清单签名，返回 (是否通过, 原因)。未配置公钥时视为不通过。"""
    signature_b64 = str(manifest.get("signature") or "").strip()
    if not signature_b64:
        return False, "清单缺少 signature 字段"
    alg = str(manifest.get("signature_alg") or "ed25519").lower()
    if alg != "ed25519":
        return False, f"不支持的签名算法 {alg}"
    try:
        key = load_public_key(public_key_text or settings.ota_public_key)
    except ValueError as e:
        return False, str(e)
    try:
        signature = base64.b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
    except (binascii.Error, ValueError):
        return False, "签名不是合法的 base64"
    try:
        key.verify(signature, canonical_payload(manifest))
    except InvalidSignature:
        return False, "签名不匹配（清单可能被篡改）"
    return True, "ok"
