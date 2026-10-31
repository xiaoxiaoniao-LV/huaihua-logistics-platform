"""MQTT 订阅后台线程：订阅 iot/+/data，收到后入库 + broadcast。"""
import json
import threading
import time

import paho.mqtt.client as mqtt

from .models import IoTDevice, IoTData
from .ws_broadcast import hub

_client: mqtt.Client | None = None
_thread: threading.Thread | None = None


def _on_message(_cli, _userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return

    # topic: iot/{device_code}/data
    parts = msg.topic.split("/")
    if len(parts) >= 3:
        device_code = parts[1]
    else:
        device_code = payload.get("device_code", "unknown")

    # 入库（用自己的 Session，因为在独立线程）
    resource_id = 0
    try:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            dev = db.query(IoTDevice).filter(IoTDevice.device_code == device_code).first()
            if dev is None:
                dev = IoTDevice(
                    resource_id=0, device_code=device_code, device_type="esp32", status="online"
                )
                db.add(dev)
                db.commit()
                db.refresh(dev)
            # 在 session 关闭前取出，避免 detach 后访问属性报错
            resource_id = dev.resource_id or 0
            row = IoTData(
                device_id=dev.id,
                temperature=payload.get("temperature"),
                humidity=payload.get("humidity"),
                longitude=payload.get("longitude"),
                latitude=payload.get("latitude"),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[mqtt] db error: {e}")

    # Redis 最新值缓存（与 HTTP 接口保持一致）
    try:
        from .redis_client import set_json
        set_json(
            f"iot:latest:{device_code}",
            {
                "device_code": device_code,
                "temperature": payload.get("temperature"),
                "humidity": payload.get("humidity"),
                "longitude": payload.get("longitude"),
                "latitude": payload.get("latitude"),
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ttl=5,
        )
    except Exception as e:
        print(f"[mqtt] redis error: {e}")

    # WebSocket 推送：type 统一为 iot_data（前端订阅此类型）
    try:
        hub.publish({
            "type": "iot_data",
            "device_code": device_code,
            "resource_id": resource_id,
            "temperature": payload.get("temperature"),
            "humidity": payload.get("humidity"),
            "longitude": payload.get("longitude"),
            "latitude": payload.get("latitude"),
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    except Exception as e:
        print(f"[mqtt] ws error: {e}")


def _on_connect(_cli, _userdata, _flags, reason_code, _properties):
    print(f"[mqtt] connected (rc={reason_code}), subscribing iot/+/data")
    _cli.subscribe("iot/+/data")


def start_mqtt(host: str = "localhost", port: int = 1883):
    """启动 MQTT 订阅后台线程（幂等）。"""
    global _client, _thread
    if _thread and _thread.is_alive():
        return

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hhlg-backend")
    cli.on_connect = _on_connect
    cli.on_message = _on_message

    def _run():
        # 带重试循环，EMQX 刚起时可能连不上
        while True:
            try:
                print(f"[mqtt] try connect {host}:{port} ...")
                cli.connect(host, port, keepalive=60)
                cli.loop_forever()
            except Exception as e:
                print(f"[mqtt] connect failed: {e}; retry in 5s")
                time.sleep(5)

    _thread = threading.Thread(target=_run, daemon=True, name="mqtt-subscriber")
    _thread.start()
    _client = cli


def publish(topic: str, payload: dict):
    """向 MQTT 发消息（给模拟器调用）。"""
    global _client
    if _client is None:
        return False
    try:
        _client.publish(topic, json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        return False
