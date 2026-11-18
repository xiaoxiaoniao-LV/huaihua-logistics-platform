"""IoT 模拟器：定时发布 MQTT 数据，给后端联调用。
用法：python simulator.py
环境变量：
  MQTT_HOST（默认 localhost）、MQTT_PORT（默认 1883）
  API_BASE（默认 http://localhost:8080，OTA 回执用）
  DEVICE_TOKEN（默认空，需与后端 DEVICE_INGEST_TOKEN 一致）
  FIRMWARE_VERSION（默认 1.0.0，模拟设备当前固件版本）
发布的 topic：iot/{device_code}/data
订阅的 topic：iot/{device_code}/cmd（平台下发 OTA 指令）
"""
import json, os, random, threading, time, urllib.request

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
API_BASE = os.environ.get("API_BASE", "http://localhost:8080").rstrip("/")
DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "")
INTERVAL = float(os.environ.get("PUBLISH_INTERVAL", "3"))

DEVICE_CODES = [
    c.strip()
    for c in os.environ.get("DEVICE_CODES", "").split(",")
    if c.strip()
] or [f"CW-{i:02d}" for i in range(1, 37)]
versions = {
    code: os.environ.get("FIRMWARE_VERSION", "1.0.0") for code in DEVICE_CODES
}


def report_ota(code: str, target: str) -> None:
    """模拟升级耗时后向后端回执，真实设备由固件自行上报。"""
    time.sleep(1.2)
    versions[code] = target
    body = json.dumps({
        "device_code": code,
        "target_version": target,
        "success": True,
        "message": "模拟器升级完成",
    }).encode()
    req = urllib.request.Request(
        API_BASE + "/api/v1/devices/ota/report",
        data=body,
        headers={"Content-Type": "application/json", "X-Device-Token": DEVICE_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  [ota] {code} → {target} 回执 {resp.status}")
    except Exception as e:
        print(f"  [ota] {code} 回执失败: {e}")


def on_message(_cli, _userdata, msg):
    if not msg.topic.endswith("/cmd"):
        return
    try:
        cmd = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return
    if cmd.get("action") != "ota":
        return
    code = msg.topic.split("/")[1]
    target = cmd.get("target_version")
    print(f"  [ota] {code} 收到升级指令 → {target}，模拟升级中...")
    # 放后台线程，避免阻塞 paho 网络循环
    threading.Thread(target=report_ota, args=(code, target), daemon=True).start()


def on_connect(cli, _userdata, _flags, reason_code, _properties):
    print(f"[simulator] connected (rc={reason_code})")
    cli.subscribe("iot/+/cmd")


cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulator")
cli.on_connect = on_connect
cli.on_message = on_message
cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
print(f"[simulator] connected to {MQTT_HOST}:{MQTT_PORT}")

cli.loop_start()

base = {
    code: {
        "temp": round(-18.0 + ((idx % 5) - 2) * 0.4, 1),
        "hum": round(62.0 + (idx % 7) * 2.0, 1),
    }
    for idx, code in enumerate(DEVICE_CODES)
}

i = 0
try:
    while True:
        hot = []
        for code in DEVICE_CODES:
            b = base[code]
            # 千分之二概率制造一次越温，用于演示告警
            if random.random() < 0.002:
                t = round(random.uniform(-2, 4), 1)
                hot.append(code)
            else:
                t = round(b["temp"] + random.uniform(-0.8, 0.8), 1)
            h = round(b["hum"] + random.uniform(-4, 4), 1)
            payload = {
                "device_code": code,
                "temperature": t,
                "humidity": h,
                "longitude": 110.0 + random.random(),
                "latitude": 27.5 + random.random(),
                "firmware_version": versions[code],
            }
            cli.publish(f"iot/{code}/data", json.dumps(payload))
        i += 1
        print(
            f"  [{time.strftime('%H:%M:%S')}] 上报 {len(DEVICE_CODES)} 台设备"
            + (f"，越温 {','.join(hot)}" if hot else "")
        )
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print("\n[simulator] stopped")
    cli.loop_stop()
    cli.disconnect()
