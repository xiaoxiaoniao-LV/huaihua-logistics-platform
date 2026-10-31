"""IoT 模拟器：定时发布 MQTT 数据，给后端联调用。
用法：python simulator.py
环境变量：MQTT_HOST（默认 localhost）、MQTT_PORT（默认 1883）
订阅的后端 topic：iot/{device_code}/data
"""
import json, os, random, time

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
INTERVAL = float(os.environ.get("PUBLISH_INTERVAL", "3"))

DEVICE_CODES = ["CW-01", "CW-02", "CW-03", "CW-04"]

cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulator")
cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
print(f"[simulator] connected to {MQTT_HOST}:{MQTT_PORT}")

cli.loop_start()

base = {
    "CW-01": {"temp": -18.0, "hum": 65.0},
    "CW-02": {"temp": -18.0, "hum": 65.0},
    "CW-03": {"temp": -18.0, "hum": 65.0},
    "CW-04": {"temp": -18.0, "hum": 65.0},
}

i = 0
try:
    while True:
        for code in DEVICE_CODES:
            b = base[code]
            # 每 50 条随机制造一次异常（高温告警）
            if i > 0 and i % 50 == 0 and random.random() < 0.5:
                t = round(random.uniform(-2, 4), 1)  # 越温区
            else:
                t = round(b["temp"] + random.uniform(-1.2, 1.2), 1)
            h = round(b["hum"] + random.uniform(-6, 6), 1)
            payload = {
                "device_code": code,
                "temperature": t,
                "humidity": h,
                "longitude": 110.0 + random.random(),
                "latitude": 27.5 + random.random(),
            }
            topic = f"iot/{code}/data"
            cli.publish(topic, json.dumps(payload))
            print(f"  [{time.strftime('%H:%M:%S')}] {topic} → {t}℃ / {h}%RH")
        i += 1
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print("\n[simulator] stopped")
    cli.loop_stop()
    cli.disconnect()
