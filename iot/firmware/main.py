"""ESP32 + DHT22 冷链温湿度采集节点（MicroPython）。

功能：
1. 上电连接 WiFi（断线自动重连）
2. 每 INTERVAL 秒读一次 DHT22，组装与后端约定一致的消息
3. 通过 MQTT 发布到 iot/{DEVICE_CODE}/data（推荐）
4. MQTT 失败时自动降级为 HTTP POST /api/iot/data（需 DEVICE_TOKEN）
5. 订阅 iot/{DEVICE_CODE}/cmd，收到 ota 指令后回执新版本（真实 OTA 需补充固件下载与写入）

烧录前请修改下方「用户配置」区的 WiFi、服务器地址与设备编码。
依赖固件：MicroPython v1.22+（esp32 通用版），umqtt.simple 已内置。
"""

import json
import time

import dht
import network
from machine import Pin

try:
    from umqtt.simple import MQTTClient
except ImportError:  # 部分固件需要自行上传 umqtt/simple.py
    MQTTClient = None

try:
    import urequests
except ImportError:
    urequests = None

# ==================== 用户配置 ====================
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"

MQTT_HOST = "192.168.1.100"   # 部署平台所在主机 IP
MQTT_PORT = 1884              # docker-compose 默认映射的 MQTT 端口
HTTP_BASE = "http://192.168.1.100:8080"  # 经 Nginx 暴露的 API 地址
DEVICE_TOKEN = "改成 .env 中的 DEVICE_INGEST_TOKEN"  # HTTP 降级上报用，可留空

DEVICE_CODE = "CW-01"         # 必须与平台「设备管理」中的设备编码一致
DEVICE_TYPE = "esp32+dht22"
FIRMWARE_VERSION = "1.0.0"    # 平台 OTA 升级指令的目标版本会与此比对
INTERVAL = 10                 # 上报间隔（秒）
DHT_PIN = 4                   # DHT22 DATA 引脚
LED_PIN = 2                   # 板载 LED，联网成功后常亮
# ==================================================

led = Pin(LED_PIN, Pin.OUT)
sensor = dht.DHT22(Pin(DHT_PIN))
mqtt_cli = None


def log(*args):
    print("[node]", *args)


def report_ota(target_version, success=True, message="模拟升级完成"):
    """向上报升级结果。真实 OTA 应在写入新固件并重启后调用一次。"""
    global FIRMWARE_VERSION
    if success:
        FIRMWARE_VERSION = target_version
    if urequests is None:
        return False
    headers = {"Content-Type": "application/json"}
    if DEVICE_TOKEN:
        headers["X-Device-Token"] = DEVICE_TOKEN
    body = {
        "device_code": DEVICE_CODE,
        "target_version": target_version,
        "success": success,
        "message": message,
    }
    try:
        resp = urequests.post(HTTP_BASE + "/api/devices/ota/report",
                              data=json.dumps(body), headers=headers)
        log("OTA 回执 →", resp.status_code)
        resp.close()
        return resp.status_code == 200
    except Exception as e:
        log("OTA 回执失败:", e)
        return False


def on_mqtt_msg(topic, msg):
    """处理平台下发的指令：目前只支持 ota。"""
    try:
        topic = topic.decode() if isinstance(topic, bytes) else topic
        cmd = json.loads(msg.decode() if isinstance(msg, bytes) else msg)
    except Exception as e:
        log("指令解析失败:", e)
        return
    log("收到指令", topic, cmd)
    if cmd.get("action") == "ota":
        target = cmd.get("target_version")
        # 真实实现：下载固件包 → 校验 → 写入 → 重启；此处以回执模拟
        report_ota(target, True, "firmware stub applied")


def wifi_connect(timeout=20):
    """连接 WiFi，返回是否成功。"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    log("连接 WiFi:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(timeout * 2):
        if wlan.isconnected():
            log("WiFi 已连接:", wlan.ifconfig()[0])
            return True
        time.sleep(0.5)
    log("WiFi 连接超时")
    return False


def mqtt_connect():
    """建立 MQTT 连接，失败返回 None。"""
    global mqtt_cli
    if MQTTClient is None:
        return None
    try:
        cli = MQTTClient("esp32-" + DEVICE_CODE, MQTT_HOST, port=MQTT_PORT, keepalive=60)
        cli.set_callback(on_mqtt_msg)
        cli.connect()
        cli.subscribe("iot/{}/cmd".format(DEVICE_CODE))
        mqtt_cli = cli
        log("MQTT 已连接", MQTT_HOST, MQTT_PORT)
        return cli
    except Exception as e:
        log("MQTT 连接失败:", e)
        mqtt_cli = None
        return None


def read_sensor():
    """读取温湿度，失败返回 None。"""
    try:
        sensor.measure()
        return round(sensor.temperature(), 1), round(sensor.humidity(), 1)
    except Exception as e:
        log("传感器读取失败:", e)
        return None


def publish_mqtt(payload):
    global mqtt_cli
    if mqtt_cli is None and mqtt_connect() is None:
        return False
    topic = "iot/{}/data".format(DEVICE_CODE)
    try:
        mqtt_cli.publish(topic, json.dumps(payload))
        log("MQTT →", topic, payload)
        return True
    except Exception as e:
        log("MQTT 发布失败:", e)
        try:
            mqtt_cli.disconnect()
        except Exception:
            pass
        mqtt_cli = None
        return False


def publish_http(payload):
    """MQTT 不可用时的 HTTP 降级上报。"""
    if urequests is None:
        return False
    headers = {"Content-Type": "application/json"}
    if DEVICE_TOKEN:
        headers["X-Device-Token"] = DEVICE_TOKEN
    try:
        resp = urequests.post(HTTP_BASE + "/api/iot/data",
                              data=json.dumps(payload), headers=headers)
        ok = resp.status_code == 201
        log("HTTP →", resp.status_code)
        resp.close()
        return ok
    except Exception as e:
        log("HTTP 上报失败:", e)
        return False


def main():
    while not wifi_connect():
        led.value(0)
        time.sleep(5)

    led.value(1)
    mqtt_connect()

    while True:
        if not network.WLAN(network.STA_IF).isconnected():
            led.value(0)
            while not wifi_connect():
                time.sleep(5)
            led.value(1)
            mqtt_connect()

        data = read_sensor()
        if data is None:
            time.sleep(INTERVAL)
            continue

        temperature, humidity = data
        payload = {
            "device_code": DEVICE_CODE,
            "temperature": temperature,
            "humidity": humidity,
            "firmware_version": FIRMWARE_VERSION,
        }
        # 有 GPS 模块时可在此追加 longitude / latitude
        if not publish_mqtt(payload):
            publish_http(payload)
        # 处理平台下发的 OTA 指令（check_msg 会触发 on_mqtt_msg）
        if mqtt_cli is not None:
            try:
                mqtt_cli.check_msg()
            except Exception as e:
                log("接收指令失败:", e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
