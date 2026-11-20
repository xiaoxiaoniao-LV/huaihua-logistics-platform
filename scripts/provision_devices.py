"""设备预配：入库绑定 → 生成节点 config.py → 固件签名发布。

到这一步，软件侧全部自动化完成，剩下的只有「买硬件、接线、刷机」。
默认预配三节点：CW-01（冷库）、TR-01（运输）、GW-01（网关）。

用法：
    python scripts/provision_devices.py
    python scripts/provision_devices.py --wifi-ssid HHLG-Lab --wifi-password 12345678
    python scripts/provision_devices.py --release 3.1.0
    python scripts/provision_devices.py --nodes CW-02,TR-02 --dry-run

产物：iot/firmware/nodes/<DEVICE_CODE>/config.py（已加入 .gitignore）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _flow import (  # noqa: E402
    ROOT,
    FlowError,
    compose,
    docker_ready,
    http_json,
    lan_ip,
    read_env,
    wait_health,
    write_env,
)

FIRMWARE_DIR = ROOT / "iot" / "firmware"
CONFIG_TEMPLATE = FIRMWARE_DIR / "config.py"
NODES_DIR = FIRMWARE_DIR / "nodes"
MAKE_RELEASE = ROOT / "iot" / "tools" / "make_release.py"

ROLE_BY_PREFIX = {"CW": "cold", "TR": "trans", "GW": "gateway"}
DEVICE_TYPE_BY_ROLE = {"cold": "temp_humidity", "trans": "temp_humidity", "gateway": "gateway"}

HARDWARE_GATE = """\
================ 硬件采购闸门 ================
软件侧已全部就绪：起栈、演示数据、无硬件验收、设备预配、固件签名发布。
继续推进只剩「买硬件 + 接线 + 刷机」：

必买（本期 BOM）：
  3 × ESP32 DevKit V1（MicroPython v1.22+）
  2 × DHT22 / AM2302 温湿度模块
  2 × 常闭型簧片门磁
  1 × MPU6050 六轴 IMU（运输节点振动）
  1 × INA219 电流/功率模块（运输节点）
  2 套面包板 + 杜邦线，3 × 5V/1A USB 电源

现场部署（多机/港区试点时再买）：
  工控机或服务器（≥4 核 8G，装 Docker）、UPS、4G/专线路由、交换机

二期可选（本期不买）：NEO-6M GPS、0.96" OLED、BH1750、LoRa SX1278。
接线与刷机步骤见 iot/firmware/README.md 第二~三节；
完整流水线说明见 docs/部署运维说明.md 第十四节。
==============================================
"""


def set_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)} = .*$")
    if not pattern.search(text):
        raise FlowError(f"config.py 模板缺少配置项 {key}")
    return pattern.sub(f"{key} = {value}", text, count=1)


def as_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def login(api: str, username: str, password: str) -> str:
    status, data = http_json(
        api, "POST", "/api/v1/auth/login", {"username": username, "password": password}
    )
    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        raise FlowError(
            f"管理员登录失败 HTTP {status}：{data}；请先执行 python scripts/bootstrap.py"
        )
    return data["access_token"]


def find_resources(api: str) -> list[dict]:
    status, data = http_json(api, "GET", "/api/v1/resources?page=1&page_size=200")
    if status != 200 or not isinstance(data, list):
        return []
    return data


def ensure_device(api: str, token: str, code: str, role: str, resource_id: int) -> dict:
    status, devices = http_json(api, "GET", "/api/v1/devices")
    if status != 200 or not isinstance(devices, list):
        raise FlowError(f"读取设备列表失败 HTTP {status}：{devices}")
    current = next((d for d in devices if d.get("device_code") == code), None)
    if current is None:
        status, data = http_json(
            api, "POST", "/api/v1/devices",
            {"device_code": code, "device_type": DEVICE_TYPE_BY_ROLE[role], "resource_id": resource_id},
            token=token,
        )
        if status not in (200, 201):
            raise FlowError(f"创建设备 {code} 失败 HTTP {status}：{data}")
        print(f"[device] 已创建设备 {code}（{role}，resource_id={resource_id}）")
        return data
    if resource_id and current.get("resource_id") != resource_id:
        status, data = http_json(
            api, "PUT", f"/api/v1/devices/{current['id']}", {"resource_id": resource_id}, token=token
        )
        if status != 200:
            raise FlowError(f"绑定设备 {code} 到资源 {resource_id} 失败 HTTP {status}：{data}")
        print(f"[device] 已绑定 {code} → 资源 {resource_id}")
        return data
    print(f"[device] {code} 已存在（resource_id={current.get('resource_id')}）")
    return current


def build_release(version: str, sign_key: str | None) -> str | None:
    cmd = [sys.executable, str(MAKE_RELEASE), version]
    if sign_key:
        cmd += ["--sign-key", sign_key]
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise FlowError(f"固件发布失败：\n{proc.stdout}\n{proc.stderr}")
    print(proc.stdout.strip())
    manifest_path = FIRMWARE_DIR / "releases" / version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("public_key")


def write_node_configs(
    nodes: list[tuple[str, str]],
    env: dict[str, str],
    args: argparse.Namespace,
    public_key: str | None,
) -> None:
    template = CONFIG_TEMPLATE.read_text(encoding="utf-8")
    http_base = args.http_base or f"http://{lan_ip()}:{env.get('HHLG_WEB_PORT', '8080')}"
    mqtt_host = args.mqtt_host or lan_ip()
    mqtt_port = args.mqtt_port or int(env.get("HHLG_MQTT_PORT", "1884"))
    device_token = env.get("DEVICE_INGEST_TOKEN", "")

    for code, role in nodes:
        text = template
        text = set_value(text, "ROLE", as_str(role))
        text = set_value(text, "DEVICE_CODE", as_str(code))
        text = set_value(text, "HTTP_BASE", as_str(http_base))
        text = set_value(text, "DEVICE_TOKEN", as_str(device_token))
        text = set_value(text, "FIRMWARE_VERSION", as_str(args.firmware_version))
        text = set_value(text, "MQTT_HOST", as_str(mqtt_host))
        text = set_value(text, "MQTT_PORT", str(int(mqtt_port)))
        if args.wifi_ssid:
            text = set_value(text, "WIFI_SSID", as_str(args.wifi_ssid))
        if args.wifi_password:
            text = set_value(text, "WIFI_PASSWORD", as_str(args.wifi_password))
        if args.with_trans_sensors and role == "trans":
            text = set_value(text, "ENABLE_MPU6050", "True")
            text = set_value(text, "ENABLE_INA219", "True")
        if public_key:
            text = set_value(text, "OTA_PUBLIC_KEY", as_str(public_key))
            text = set_value(text, "OTA_ALLOW_UNSIGNED", "False")

        out_dir = NODES_DIR / code
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "config.py"
        out_file.write_text(text, encoding="utf-8")
        print(f"[config] {out_file.relative_to(ROOT)}（ROLE={role}，HTTP_BASE={http_base}）")

    if not args.wifi_ssid or not args.wifi_password:
        print("[config] 未提供 --wifi-ssid/--wifi-password，节点配置里仍是占位值，刷机前请补上")


def main() -> int:
    env = read_env()
    parser = argparse.ArgumentParser(description="设备预配与固件发布")
    parser.add_argument(
        "--api", default=f"http://127.0.0.1:{env.get('HHLG_API_PORT', '8010')}"
    )
    parser.add_argument("--admin-user", default="demo_admin")
    parser.add_argument("--admin-password", default="Demo@123456")
    parser.add_argument("--nodes", default="CW-01,TR-01,GW-01", help="逗号分隔的设备编码")
    parser.add_argument("--wifi-ssid", default="")
    parser.add_argument("--wifi-password", default="")
    parser.add_argument("--http-base", default="", help="默认 http://<本机局域网IP>:8080")
    parser.add_argument("--mqtt-host", default="", help="默认本机局域网 IP")
    parser.add_argument("--mqtt-port", type=int, default=0, help="默认 .env 的 HHLG_MQTT_PORT")
    parser.add_argument("--firmware-version", default="3.0.0")
    parser.add_argument("--with-trans-sensors", action="store_true", help="运输节点启用 MPU6050/INA219")
    parser.add_argument("--release", default="", help="生成并签名该版本的固件发布包")
    parser.add_argument("--sign-key", default="", help="Ed25519 私钥种子，默认读 .env 的 OTA_SIGNING_KEY")
    parser.add_argument("--no-restart", action="store_true", help="发布后不重启 backend")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写平台与文件")
    args = parser.parse_args()

    try:
        nodes: list[tuple[str, str]] = []
        for raw in args.nodes.split(","):
            code = raw.strip().upper()
            if not code:
                continue
            role = ROLE_BY_PREFIX.get(code.split("-")[0])
            if role is None:
                raise FlowError(f"无法从 {code} 推断角色（前缀应为 CW/TR/GW）")
            nodes.append((code, role))

        if args.dry_run:
            print("[dry-run] 计划预配：" + ", ".join(f"{c}({r})" for c, r in nodes))
            print("[dry-run] 不登录平台、不写 config.py、不生成发布包")
            print(HARDWARE_GATE)
            return 0

        token = login(args.api, args.admin_user, args.admin_password)
        resources = find_resources(args.api)
        for code, role in nodes:
            resource_id = 0
            if role != "gateway":
                matched = next(
                    (r for r in resources if code in str(r.get("name", ""))), None
                )
                if matched is not None:
                    resource_id = int(matched["id"])
                else:
                    print(f"[device] 未找到名称含 {code} 的资源，设备先不绑定（resource_id=0）")
            ensure_device(args.api, token, code, role, resource_id)

        public_key: str | None = None
        if args.release:
            key = args.sign_key or env.get("OTA_SIGNING_KEY", "")
            if not key:
                print("[release] 未找到签名私钥，将生成未签名发布包（仅调试可用）")
            public_key = build_release(args.release, key or None)
            if public_key:
                write_env({"OTA_PUBLIC_KEY": public_key, "OTA_REQUIRE_SIGNATURE": "true"})
                print("[release] 公钥已写入 .env，并开启 OTA_REQUIRE_SIGNATURE=true")
                if args.no_restart:
                    print("[release] 已跳过重启，请手动执行 docker compose up -d backend")
                elif docker_ready():
                    compose(["up", "-d", "backend"], capture=False)
                    wait_health(args.api, timeout=180)
                    print("[release] backend 已重启并加载新公钥")
                else:
                    print("[release] 未检测到 docker compose，请手动重启 backend 使公钥生效")

        write_node_configs(nodes, env, args, public_key)

        print("\n下一步（买回硬件后）：")
        print("  1. 按 iot/firmware/README.md 接线，烧录 MicroPython v1.22+")
        print("  2. 把 iot/firmware/nodes/<编码>/config.py 与 main.py/ota.py/ed25519.py 拷到板子")
        print("  3. 上电后执行 python scripts/acceptance.py --device <编码> 复跑验收")
        print()
        print(HARDWARE_GATE)
        return 0
    except FlowError as exc:
        print(f"\n[失败] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
