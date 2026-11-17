"""遥测接入链路：点位字典、批量落库、状态语义、告警去抖。

设计要点
- 窄表存储：一行一个点位，新增传感器只注册点位，不改表结构。
- 幂等：唯一键 (device_id, point_key, ts) 天然去重，断网补传可安全重放。
- 去抖：连续 N 个采样同向越限才产生告警，恢复后自动关闭，避免抖动刷屏。
- 状态正交：status 表示设备可用性，quality 表示数据新鲜度，二者独立。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..models import Alert, DeviceEvent, DevicePoint, IoTDevice, Telemetry

logger = logging.getLogger(__name__)

ALARM_DEBOUNCE_SAMPLES = 3   # 连续多少次越限才真正告警
ALARM_DEDUP_MINUTES = 10     # 同类型告警最短重复间隔
MAX_POINTS_PER_REPORT = 50

# 点位字典：point_key -> (名称, 单位, 数据类型, 精度, 告警下限, 告警上限)
# 阈值为冷链通用默认值，可按设备/资源在 DevicePoint 上覆盖。
POINT_CATALOG: dict[str, tuple[str, str, str, int, float | None, float | None]] = {
    "temp_in": ("库内温度", "℃", "number", 1, -30.0, -5.0),
    "temp_deep": ("深层温度", "℃", "number", 1, -30.0, -5.0),
    "temp_supply": ("送风温度", "℃", "number", 1, -30.0, -5.0),
    "hum_in": ("库内湿度", "%RH", "number", 1, 0.0, 90.0),
    "door": ("门磁", "", "bool", 0, None, None),
    "current_a": ("电流", "A", "number", 2, 0.0, 16.0),
    "power_w": ("功率", "W", "number", 1, 0.0, 8000.0),
    "battery": ("电量", "%", "number", 0, 20.0, 100.0),
    "co2": ("二氧化碳", "ppm", "number", 0, 0.0, 1000.0),
    "rssi": ("信号强度", "dBm", "number", 0, -95.0, 0.0),
    "vibration": ("振动", "g", "number", 3, 0.0, 2.0),
}
_CATALOG_SORT = {key: idx for idx, key in enumerate(POINT_CATALOG)}

_QUALITY = {"good", "stale", "bad"}


class UnknownPointsError(ValueError):
    """上报了未注册且不在内置字典中的点位。"""

    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        super().__init__("未注册的点位：" + ", ".join(self.keys))


class InvalidPointValueError(ValueError):
    """点位取值无法按声明的数据类型解析。"""

    def __init__(self, key: str, raw):
        self.key = key
        super().__init__(f"点位 {key} 的取值非法：{raw!r}")


def normalize_ts(ts: datetime | None) -> datetime:
    """统一到本地时间、秒级精度，与 MySQL DATETIME 的存储粒度一致。"""
    if ts is None:
        return datetime.now().replace(microsecond=0)
    if ts.tzinfo is not None:
        ts = ts.astimezone().replace(tzinfo=None)
    return ts.replace(microsecond=0)


def ensure_device(
    db: Session,
    device_code: str,
    firmware_version: str | None = None,
) -> IoTDevice:
    """按编码取设备，不存在则自动建档（演示阶段允许自注册）。"""
    dev = db.query(IoTDevice).filter(IoTDevice.device_code == device_code).first()
    if dev is None:
        dev = IoTDevice(
            resource_id=0,
            device_code=device_code,
            device_type="esp32",
            status="unknown",
            quality="unknown",
            firmware_version=firmware_version or "1.0.0",
        )
        db.add(dev)
        db.flush()
    elif firmware_version and dev.firmware_version != firmware_version:
        dev.firmware_version = firmware_version
    return dev


def resolve_points(
    db: Session, device: IoTDevice, keys: list[str]
) -> dict[str, DevicePoint]:
    """把上报点位映射到点位字典；内置字典中的点位自动注册。"""
    existing = {
        p.point_key: p
        for p in db.query(DevicePoint).filter(DevicePoint.device_id == device.id).all()
    }
    unknown: list[str] = []
    for key in keys:
        if key in existing:
            continue
        spec = POINT_CATALOG.get(key)
        if spec is None:
            unknown.append(key)
            continue
        name, unit, data_type, precision, min_value, max_value = spec
        point = DevicePoint(
            device_id=device.id,
            point_key=key,
            name=name,
            unit=unit,
            data_type=data_type,
            precision=precision,
            min_value=min_value,
            max_value=max_value,
            writable=False,
            sort=_CATALOG_SORT.get(key, 99),
        )
        db.add(point)
        existing[key] = point
    if unknown:
        raise UnknownPointsError(unknown)
    return existing


def _coerce(point: DevicePoint, raw) -> tuple[float | None, str | None]:
    """按点位数据类型归一化取值，返回 (数值, 文本)。"""
    if point.data_type == "bool":
        if isinstance(raw, bool):
            flag = raw
        elif isinstance(raw, (int, float)):
            flag = bool(raw)
        else:
            flag = str(raw).strip().lower() in {"1", "true", "on", "open", "yes", "opened"}
        return (1.0 if flag else 0.0), ("open" if flag else "closed")
    if point.data_type == "text":
        return None, str(raw)[:64]
    try:
        return float(raw), None
    except (TypeError, ValueError):
        raise InvalidPointValueError(point.point_key, raw)


def _breach_direction(point: DevicePoint, value: float) -> str | None:
    if point.max_value is not None and value > point.max_value:
        return "high"
    if point.min_value is not None and value < point.min_value:
        return "low"
    return None


def _is_same_breach(point: DevicePoint, value: float | None, direction: str) -> bool:
    if value is None:
        return False
    if direction == "high":
        return point.max_value is not None and value > point.max_value
    return point.min_value is not None and value < point.min_value


def _recover(db: Session, device: IoTDevice, point_key: str, now: datetime) -> dict | None:
    """数值回到正常区间：关闭未恢复的告警事件与活动告警。"""
    events = (
        db.query(DeviceEvent)
        .filter(
            DeviceEvent.device_id == device.id,
            DeviceEvent.event_type.in_([f"alarm_{point_key}_high", f"alarm_{point_key}_low"]),
            DeviceEvent.resolved_at.is_(None),
        )
        .all()
    )
    for event in events:
        event.resolved_at = now
    alerts = (
        db.query(Alert)
        .filter(
            Alert.device_id == device.id,
            Alert.type.in_([f"{point_key}_high", f"{point_key}_low"]),
            Alert.status == "active",
        )
        .all()
    )
    for alert in alerts:
        alert.status = "resolved"
    if not events and not alerts:
        return None
    return {
        "kind": "recovered",
        "device_code": device.device_code,
        "point_key": point_key,
        "resolved_events": len(events),
        "resolved_alerts": len(alerts),
        "message": f"{point_key} 已恢复正常区间",
    }


def _raise_alarm(
    db: Session,
    device: IoTDevice,
    point: DevicePoint,
    direction: str,
    value: float,
    now: datetime,
) -> dict | None:
    """去抖达标后生成告警；同点位同方向未恢复时只保留一条。"""
    event_type = f"alarm_{point.point_key}_{direction}"
    active = (
        db.query(DeviceEvent)
        .filter(
            DeviceEvent.device_id == device.id,
            DeviceEvent.event_type == event_type,
            DeviceEvent.resolved_at.is_(None),
        )
        .first()
    )
    if active is not None:
        return None

    limit = point.max_value if direction == "high" else point.min_value
    unit = point.unit or ""
    relation = "高于上限" if direction == "high" else "低于下限"
    message = f"{point.name} {value}{unit} {relation} {limit}{unit}"
    severity = "critical" if point.point_key.startswith("temp") else "warn"

    db.add(
        DeviceEvent(
            device_id=device.id,
            event_type=event_type,
            severity=severity,
            message=message[:255],
            payload={
                "point_key": point.point_key,
                "value": value,
                "direction": direction,
                "limit": limit,
            },
        )
    )

    alert_type = f"{point.point_key}_{direction}"
    since = now - timedelta(minutes=ALARM_DEDUP_MINUTES)
    recent = (
        db.query(Alert)
        .filter(
            Alert.device_id == device.id,
            Alert.type == alert_type,
            Alert.status == "active",
            Alert.created_at >= since,
        )
        .first()
    )
    if recent is None:
        db.add(
            Alert(
                device_id=device.id,
                type=alert_type,
                level=severity,
                message=message[:255],
                status="active",
            )
        )

    return {
        "kind": "alarm",
        "device_code": device.device_code,
        "point_key": point.point_key,
        "direction": direction,
        "value": value,
        "limit": limit,
        "level": severity,
        "message": message,
    }


def _check_threshold(
    db: Session, device: IoTDevice, point: DevicePoint, value: float, now: datetime
) -> dict | None:
    """越限去抖：连续 N 个采样同向越限才告警；回到区间内自动恢复。"""
    if point.min_value is None and point.max_value is None:
        return None

    direction = _breach_direction(point, value)
    if direction is None:
        return _recover(db, device, point.point_key, now)

    samples = (
        db.query(Telemetry.value_num)
        .filter(
            Telemetry.device_id == device.id,
            Telemetry.point_key == point.point_key,
        )
        .order_by(Telemetry.ts.desc())
        .limit(ALARM_DEBOUNCE_SAMPLES)
        .all()
    )
    if len(samples) < ALARM_DEBOUNCE_SAMPLES:
        return None
    if not all(_is_same_breach(point, row[0], direction) for row in samples):
        return None
    return _raise_alarm(db, device, point, direction, value, now)


def _check_door(
    db: Session, device: IoTDevice, point: DevicePoint, ts: datetime
) -> dict | None:
    """门磁变位即记事件：开启/关闭各一条，用于进出库与失温溯源。"""
    rows = (
        db.query(Telemetry)
        .filter(
            Telemetry.device_id == device.id,
            Telemetry.point_key == point.point_key,
        )
        .order_by(Telemetry.ts.desc())
        .limit(2)
        .all()
    )
    if len(rows) < 2:
        return None
    current, previous = rows[0], rows[1]
    if current.value_num == previous.value_num:
        return None
    is_open = bool(current.value_num)
    message = f"{point.name or '门磁'}{'开启' if is_open else '关闭'}"
    db.add(
        DeviceEvent(
            device_id=device.id,
            event_type="door_open" if is_open else "door_close",
            severity="warn" if is_open else "info",
            message=message,
            payload={"point_key": point.point_key, "ts": ts.isoformat()},
        )
    )
    return {
        "kind": "door",
        "device_code": device.device_code,
        "point_key": point.point_key,
        "open": is_open,
        "message": message,
    }


def _derive_status(db: Session, device: IoTDevice, quality: str) -> str:
    if device.status == "maintenance":
        return "maintenance"
    if quality == "bad":
        return "degraded"
    active_alarm = (
        db.query(DeviceEvent.id)
        .filter(
            DeviceEvent.device_id == device.id,
            DeviceEvent.event_type.like("alarm%"),
            DeviceEvent.resolved_at.is_(None),
        )
        .first()
    )
    return "alarm" if active_alarm else "online"


def ingest_envelope(db: Session, envelope, now: datetime | None = None) -> dict:
    """单条 envelope 落库（不 commit），返回本次摘要。"""
    now = now or datetime.now()
    ts = normalize_ts(envelope.ts)
    device = ensure_device(db, envelope.device_code, envelope.firmware_version)
    keys = list(envelope.points.keys())
    if len(keys) > MAX_POINTS_PER_REPORT:
        raise InvalidPointValueError("*", f"单条上报最多 {MAX_POINTS_PER_REPORT} 个点位")
    points = resolve_points(db, device, keys)

    existing = {
        row[0]
        for row in db.query(Telemetry.point_key)
        .filter(
            Telemetry.device_id == device.id,
            Telemetry.ts == ts,
            Telemetry.point_key.in_(keys),
        )
        .all()
    }

    written: dict[str, tuple[float | None, str | None]] = {}
    for key in keys:
        raw = envelope.points[key]
        if raw is None or key in existing:
            continue
        value_num, value_text = _coerce(points[key], raw)
        db.add(
            Telemetry(
                device_id=device.id,
                point_key=key,
                ts=ts,
                value_num=value_num,
                value_text=value_text,
                quality=envelope.quality,
                seq=envelope.seq,
            )
        )
        written[key] = (value_num, value_text)

    duplicates = sum(1 for key in keys if envelope.points[key] is not None and key in existing)
    if written:
        db.flush()  # 让去抖查询看到本次采样

    events: list[dict] = []
    for key, (value_num, _text) in written.items():
        point = points[key]
        event = (
            _check_door(db, device, point, ts)
            if point.data_type == "bool"
            else _check_threshold(db, device, point, value_num, now)
            if value_num is not None
            else None
        )
        if event:
            events.append(event)

    quality = envelope.quality if envelope.quality in _QUALITY else "good"
    if device.last_seen_at is None or ts > device.last_seen_at:
        device.last_seen_at = ts
    device.quality = quality
    db.flush()  # 让本轮的告警/恢复事件对状态推导可见（会话关闭了 autoflush）
    device.status = _derive_status(db, device, quality)

    return {
        "device_code": device.device_code,
        "status": device.status,
        "quality": device.quality,
        "last_seen_at": device.last_seen_at.isoformat(),
        "accepted": len(written),
        "duplicates": duplicates,
        "points": {
            key: {"value_num": num, "value_text": text}
            for key, (num, text) in written.items()
        },
        "events": events,
    }


def ingest_batch(db: Session, envelopes: list, now: datetime | None = None) -> dict:
    """批量接入（同一事务内），支持同一设备多条补传数据。"""
    now = now or datetime.now()
    devices = [ingest_envelope(db, env, now) for env in envelopes]
    return {
        "received_at": now.isoformat(),
        "accepted": sum(d["accepted"] for d in devices),
        "duplicates": sum(d["duplicates"] for d in devices),
        "devices": devices,
    }


def latest_rows(db: Session, device_ids: list[int]) -> dict[tuple[int, str], Telemetry]:
    """每台设备每个点位的最新一条遥测。"""
    if not device_ids:
        return {}
    sub = (
        db.query(
            Telemetry.device_id.label("device_id"),
            Telemetry.point_key.label("point_key"),
            func.max(Telemetry.ts).label("ts"),
        )
        .filter(Telemetry.device_id.in_(device_ids))
        .group_by(Telemetry.device_id, Telemetry.point_key)
        .subquery()
    )
    rows = (
        db.query(Telemetry)
        .join(
            sub,
            and_(
                Telemetry.device_id == sub.c.device_id,
                Telemetry.point_key == sub.c.point_key,
                Telemetry.ts == sub.c.ts,
            ),
        )
        .all()
    )
    return {(row.device_id, row.point_key): row for row in rows}


def point_value(row: Telemetry | None, point: DevicePoint):
    """把遥测行转成前端可直接展示的值。"""
    if row is None:
        return None
    if point.data_type == "bool":
        return bool(row.value_num) if row.value_num is not None else None
    if point.data_type == "text":
        return row.value_text
    if row.value_num is None:
        return None
    return round(row.value_num, point.precision)


def _age_ms(ts: datetime | None, now: datetime) -> int | None:
    if ts is None:
        return None
    return max(0, int((now - ts).total_seconds() * 1000))


def device_snapshot(db: Session, device: IoTDevice, now: datetime | None = None) -> dict:
    """设备面板读模型：点位字典 + 最新值 + 数据新鲜度。"""
    now = now or datetime.now()
    points = (
        db.query(DevicePoint)
        .filter(DevicePoint.device_id == device.id)
        .order_by(DevicePoint.sort, DevicePoint.id)
        .all()
    )
    latest = latest_rows(db, [device.id])
    items = []
    for point in points:
        row = latest.get((device.id, point.point_key))
        items.append(
            {
                "point_key": point.point_key,
                "name": point.name,
                "unit": point.unit,
                "data_type": point.data_type,
                "precision": point.precision,
                "min_value": point.min_value,
                "max_value": point.max_value,
                "writable": point.writable,
                "sort": point.sort,
                "value": point_value(row, point),
                "quality": row.quality if row else "unknown",
                "ts": row.ts.isoformat() if row else None,
                "age_ms": _age_ms(row.ts, now) if row else None,
            }
        )
    return {
        "device_code": device.device_code,
        "name": device.name,
        "resource_id": device.resource_id or 0,
        "space_id": device.space_id,
        "status": device.status or "unknown",
        "quality": device.quality or "unknown",
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "age_ms": _age_ms(device.last_seen_at, now),
        "points": items,
    }


def series(
    db: Session,
    device: IoTDevice,
    point_key: str,
    limit: int = 120,
    since: datetime | None = None,
) -> list[dict]:
    """点位历史序列，按时间正序返回，便于直接画折线。"""
    query = db.query(Telemetry).filter(
        Telemetry.device_id == device.id, Telemetry.point_key == point_key
    )
    if since is not None:
        query = query.filter(Telemetry.ts >= since)
    rows = query.order_by(Telemetry.ts.desc()).limit(limit).all()
    return [
        {
            "ts": row.ts.isoformat(),
            "value_num": row.value_num,
            "value_text": row.value_text,
            "quality": row.quality,
        }
        for row in reversed(rows)
    ]


def publish_ingest(result: dict) -> None:
    """把本次接入结果推给大屏/工作台（尽力而为，不影响写库结果）。"""
    try:
        from .. import ws_broadcast
    except Exception:  # pragma: no cover - 循环导入保护
        return
    for device in result.get("devices", []):
        try:
            ws_broadcast.publish(
                {
                    "type": "telemetry",
                    "device_code": device["device_code"],
                    "status": device["status"],
                    "quality": device["quality"],
                    "last_seen_at": device["last_seen_at"],
                    "points": device["points"],
                }
            )
            for event in device.get("events", []):
                ws_broadcast.publish({"type": "twin_event", **event})
        except Exception:
            logger.debug("[telemetry] WebSocket 推送失败", exc_info=True)
