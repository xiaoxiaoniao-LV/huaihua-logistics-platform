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
    twin_points: dict[str, float] = {}
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
            version = payload.get("firmware_version")
            if version and dev.firmware_version != version:
                dev.firmware_version = version
            row = IoTData(
                device_id=dev.id,
                temperature=payload.get("temperature"),
                humidity=payload.get("humidity"),
                longitude=payload.get("longitude"),
                latitude=payload.get("latitude"),
            )
            db.add(row)

            # 同步写窄表遥测，让数字孪生绑定的点位有实时值
            if payload.get("temperature") is not None:
                twin_points["temp_in"] = float(payload["temperature"])
            if payload.get("humidity") is not None:
                twin_points["hum_in"] = float(payload["humidity"])
            if twin_points:
                from .schemas.telemetry import TelemetryEnvelope
                from .services import telemetry as telemetry_service

                telemetry_service.ingest_envelope(
                    db,
                    TelemetryEnvelope(
                        device_code=device_code,
                        quality="good",
                        firmware_version=version,
                        points=twin_points,
                    ),
                )
            db.commit()
            from .metrics import IOT_MESSAGES
            IOT_MESSAGES.inc()
        finally:
            db.close()
    except Exception as e:
        print(f"[mqtt] db error: {e}")

    # 窄表遥测 WS 推送：孪生舞台按点位增量刷新，不必等 20s 轮询
    if twin_points:
        try:
            hub.publish({
                "type": "telemetry",
                "device_code": device_code,
                "status": "online",
                "quality": "good",
                "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "points": {k: {"value_num": v} for k, v in twin_points.items()},
            })
        except Exception as e:
            print(f"[mqtt] ws telemetry error: {e}")


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


def is_connected() -> bool:
    """健康检查用：MQTT 是否已连上 broker。"""
    try:
        return _client is not None and bool(_client.is_connected())
    except Exception:
        return False


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
