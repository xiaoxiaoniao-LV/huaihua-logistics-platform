"""文件级 OTA（MicroPython）。

流程：
  1. GET /api/v1/devices/ota/manifest/<version>  拉取清单（name + size + sha256）
  1.5 用固件内置 Ed25519 公钥校验清单签名（防止中间人替换版本/哈希）
  2. GET /api/v1/devices/ota/file/<version>/<name>  逐文件下载并校验
  3. 覆盖写入 .py 文件（config.py / boot.py 例外，永不被覆盖）
  4. 写 version.txt 标记当前版本，回执 /api/v1/devices/ota/report，重启生效

设计约束：
- 只替换代码文件，节点身份、引脚、WiFi、令牌都在 config.py 里，OTA 不碰；
- 下载先写 <name>.new，校验通过后再替换，避免半包变砖；
- 任一环节失败都上报 failed 并保留旧文件，设备继续按旧版本运行。

依赖：urequests（HTTP）、hashlib（校验，缺失时跳过哈希只比对大小）、ed25519（清单验签）。
"""

import binascii
import gc
import json
import os
import time

import machine

import config as cfg
import ed25519

try:
    import urequests
except ImportError:
    urequests = None

try:
    import hashlib
except ImportError:
    hashlib = None

# 节点专属配置与启动脚本：任何情况下都不参与分发
_EXCLUDED = ("config.py", "boot.py", "version.txt")


def log(*args):
    if cfg.DEBUG:
        print("[%s][ota]" % cfg.DEVICE_CODE, *args)


def _headers():
    headers = {}
    if cfg.DEVICE_TOKEN:
        headers["X-Device-Token"] = cfg.DEVICE_TOKEN
    return headers


def _get(path):
    """返回 (status_code, body_bytes)；网络异常抛 RuntimeError。"""
    if urequests is None:
        raise RuntimeError("固件缺少 urequests")
    try:
        resp = urequests.get(cfg.HTTP_BASE + path, headers=_headers())
    except Exception as e:
        raise RuntimeError(str(e))
    try:
        body = resp.content
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return resp.status_code, body


def _fetch_manifest(version):
    code, body = _get("/api/v1/devices/ota/manifest/" + version)
    if code != 200:
        raise RuntimeError("清单 HTTP %s" % code)
    data = json.loads(body)
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list) or not files:
        raise RuntimeError("清单为空")
    return data


def _b64(text):
    return binascii.a2b_base64(text)


def _verify_manifest(manifest):
    """验签失败抛 RuntimeError；未配置公钥时按 OTA_ALLOW_UNSIGNED 决定是否放行。"""
    signature = manifest.get("signature")
    if not signature:
        if cfg.OTA_ALLOW_UNSIGNED:
            log("警告：清单未签名，已按 OTA_ALLOW_UNSIGNED 放行")
            return
        raise RuntimeError("清单缺少签名")

    if not cfg.OTA_PUBLIC_KEY:
        raise RuntimeError("设备未配置 OTA_PUBLIC_KEY，无法验签")
    alg = str(manifest.get("signature_alg") or "ed25519").lower()
    if alg != "ed25519":
        raise RuntimeError("不支持的签名算法 %s" % alg)

    try:
        public = _b64(cfg.OTA_PUBLIC_KEY)
        sig = _b64(signature)
    except Exception:
        raise RuntimeError("公钥或签名不是合法 base64")

    if not ed25519.verify(public, sig, ed25519.canonical_payload(manifest)):
        raise RuntimeError("清单验签失败（可能被篡改）")
    log("清单验签通过")


def _safe_name(name):
    if not name or not name.endswith(".py"):
        return False
    if name in _EXCLUDED or name.startswith("."):
        return False
    for ch in ("/", "\\", ".."):
        if ch in name:
            return False
    return True


def _sha256(data):
    if hashlib is None:
        return None
    digest = hashlib.sha256(data).digest()
    return "".join(["%02x" % b for b in digest])


def _download(version, name):
    code, body = _get("/api/v1/devices/ota/file/%s/%s" % (version, name))
    if code != 200:
        raise RuntimeError("HTTP %s" % code)
    return body


def _write(name, data):
    """先写临时文件再替换，替换时先删旧文件（littlefs 的 rename 不覆盖同名文件）。"""
    tmp = name + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        os.remove(name)
    except OSError:
        pass
    os.rename(tmp, name)


def _report(version, ok, message):
    if urequests is None:
        return
    body = json.dumps({
        "device_code": cfg.DEVICE_CODE,
        "target_version": version,
        "success": bool(ok),
        "message": (message or "")[:200],
    })
    try:
        resp = urequests.post(
            cfg.HTTP_BASE + "/api/v1/devices/ota/report", data=body, headers=_headers()
        )
        try:
            resp.close()
        except Exception:
            pass
    except Exception as e:
        log("回执上报失败:", e)


def _fail(version, message):
    log("OTA 失败:", message)
    _report(version, False, message)
    return False, message


def perform(target_version):
    """执行一次升级；成功则重启（不返回），失败返回 (False, message)。"""
    version = (target_version or "").strip()
    if not version:
        return _fail("", "目标版本为空")

    log("开始升级 →", version)
    try:
        manifest = _fetch_manifest(version)
        _verify_manifest(manifest)
    except Exception as e:
        return _fail(version, "拉取/校验清单失败: %s" % e)

    files = manifest["files"]
    for item in files:
        name = str(item.get("name", ""))
        if not _safe_name(name):
            return _fail(version, "文件名不合法: %s" % name)
        try:
            data = _download(version, name)
        except Exception as e:
            return _fail(version, "%s 下载失败: %s" % (name, e))

        size = item.get("size")
        if size is not None and len(data) != int(size):
            return _fail(version, "%s 大小不符" % name)
        expect = item.get("sha256")
        if expect:
            actual = _sha256(data)
            if actual is not None and actual != expect:
                return _fail(version, "%s 哈希不符" % name)

        try:
            _write(name, data)
        except Exception as e:
            return _fail(version, "%s 写入失败: %s" % (name, e))
        log("已更新", name, len(data), "字节")
        del data
        gc.collect()

    try:
        with open(cfg.OTA_VERSION_FILE, "w") as f:
            f.write(version)
    except Exception as e:
        return _fail(version, "写版本标记失败: %s" % e)

    _report(version, True, "ok")
    log("升级完成，2 秒后重启")
    time.sleep(2)
    machine.reset()
    return True, "reboot"
