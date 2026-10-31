"""IoT 数据上报 / 查询 / 预警。带 Redis 最新值缓存（TTL 5s）。"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Alert, AlertRule, IoTDevice, IoTData, Resource, User
from ..schemas.alert_rule import AlertRuleOut, AlertRuleUpdate
from ..schemas.iot import IoTDataReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/iot", tags=["iot"])

_TTL_LATEST = 5  # IoT 最新值，5s 过期
GLOBAL_RULE_ID = 0  # alert_rules.resource_id = 0 表示全局默认规则


def _default_rule_values() -> dict:
    """配置中的默认阈值，作为没有任何规则行时的兜底。"""
    return {
        "temp_min": settings.alert_temp_min,
        "temp_max": settings.alert_temp_max,
        "humidity_max": settings.alert_humidity_max,
    }


def _resolve_rule(db: Session, resource_id: int) -> dict:
    """按 资源级规则 → 全局规则 → 配置默认 的优先级取生效阈值。"""
    rule = None
    if resource_id:
        rule = db.query(AlertRule).filter(AlertRule.resource_id == resource_id).first()
    if rule is None:
        rule = db.query(AlertRule).filter(AlertRule.resource_id == GLOBAL_RULE_ID).first()
    if rule is None:
        return {**_default_rule_values(), "enabled": True}
    return {
        "temp_min": rule.temp_min,
        "temp_max": rule.temp_max,
        "humidity_max": rule.humidity_max,
        "enabled": bool(rule.enabled),
    }


def _rule_out(db: Session, rule: AlertRule) -> AlertRuleOut:
    out = AlertRuleOut.model_validate(rule)
    if rule.resource_id:
        res = db.get(Resource, rule.resource_id)
        out.resource_name = res.name if res else None
    else:
        out.resource_name = "全局默认"
    return out


def _rc():
    try:
        from .. import redis_client
        return redis_client
    except Exception as e:
        logger.warning("[iot] redis_client 不可用: %s", e)
        return None


def _ensure_device(db: Session, device_code: str) -> IoTDevice:
    """确保设备存在；不存在则自动建一条（演示阶段简化处理）。"""
    dev = db.query(IoTDevice).filter(IoTDevice.device_code == device_code).first()
    if dev is None:
        dev = IoTDevice(
            resource_id=0,  # 演示阶段先不关联；前端可忽略
            device_code=device_code,
            device_type="esp32",
            status="online",
        )
        db.add(dev)
        db.commit()
        db.refresh(dev)
    else:
        if dev.status != "online":
            dev.status = "online"
            db.commit()
    return dev


def _check_alerts(db: Session, dev: IoTDevice, payload: dict):
    """按生效阈值做简单预警判定。"""
    rule = _resolve_rule(db, dev.resource_id)
    if not rule["enabled"]:
        return
    temp_min, temp_max = float(rule["temp_min"]), float(rule["temp_max"])
    humidity_max = float(rule["humidity_max"])

    if payload.get("temperature") is not None:
        t = float(payload["temperature"])
        if t < temp_min:
            _create_alert(db, dev, "temperature_low", "critical",
                          f"温度 {t}℃ 低于下限 {temp_min}℃")
        elif t > temp_max:
            _create_alert(db, dev, "temperature_high", "critical",
                          f"温度 {t}℃ 高于上限 {temp_max}℃")
    if payload.get("humidity") is not None:
        h = float(payload["humidity"])
        if h > humidity_max:
            _create_alert(db, dev, "humidity_high", "warn",
                          f"湿度 {h}%RH 高于上限 {humidity_max}%RH")


def _create_alert(db: Session, dev: IoTDevice, atype: str, level: str, msg: str):
    # 10 分钟内同类型只记一次，避免刷爆
    since = datetime.now() - timedelta(minutes=10)
    recent = (
        db.query(Alert)
        .filter(Alert.device_id == dev.id, Alert.type == atype, Alert.created_at >= since)
        .first()
    )
    if recent:
        return
    a = Alert(device_id=dev.id, type=atype, level=level, message=msg, status="active")
    db.add(a)


def _verify_device_token(x_device_token: str | None = Header(None, alias="X-Device-Token")):
    """设备上报鉴权：配置了 device_ingest_token 时强制校验。"""
    expected = settings.device_ingest_token
    if not expected:
        return
    if x_device_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "设备令牌无效")


@router.post("/data", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_verify_device_token)])
def report_data(payload: IoTDataReport, db: Session = Depends(get_db)):
    dev = _ensure_device(db, payload.device_code)
    now = datetime.now()
    row = IoTData(
        device_id=dev.id,
        temperature=payload.temperature,
        humidity=payload.humidity,
        longitude=payload.longitude,
        latitude=payload.latitude,
    )
    db.add(row)
    if dev.resource_id:
        _check_alerts(db, dev, payload.model_dump())
    db.commit()

    # 1) WebSocket 推送
    try:
        from .. import ws_broadcast
        ws_broadcast.publish({
            "type": "iot_data",
            "device_code": payload.device_code,
            "resource_id": dev.resource_id,
            "temperature": payload.temperature,
            "humidity": payload.humidity,
            "recorded_at": now.isoformat(),
        })
    except Exception:
        pass

    # 2) Redis 最新值缓存（写后覆盖）
    rc = _rc()
    if rc is not None:
        try:
            rc.set_json(
                f"iot:latest:{payload.device_code}",
                {
                    "device_code": payload.device_code,
                    "temperature": payload.temperature,
                    "humidity": payload.humidity,
                    "longitude": payload.longitude,
                    "latitude": payload.latitude,
                    "recorded_at": now.isoformat(),
                },
                ttl=_TTL_LATEST,
            )
        except Exception as e:
            logger.warning("[iot] Redis 写最新值失败: %s", e)

    return {"status": "ok", "data_id": row.id}


@router.get("/data")
def query_data(
    device_code: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(IoTData).join(IoTDevice, IoTData.device_id == IoTDevice.id)
    if device_code:
        q = q.filter(IoTDevice.device_code == device_code)
    rows = q.order_by(IoTData.recorded_at.desc()).limit(limit).all()
    out = []
    devs_cache = {}
    for r in rows:
        did = r.device_id
        if did not in devs_cache:
            d = db.get(IoTDevice, did)
            devs_cache[did] = d
        d = devs_cache[did]
        out.append({
            "device_code": d.device_code if d else f"id{did}",
            "resource_id": (d.resource_id if d else 0) or 0,
            "temperature": r.temperature,
            "humidity": r.humidity,
            "longitude": r.longitude,
            "latitude": r.latitude,
            "recorded_at": r.recorded_at.isoformat(),
        })
    return {"count": len(rows), "data": out}


@router.get("/alerts")
def list_alerts(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Alert)
    if status_filter:
        q = q.filter(Alert.status == status_filter)
    rows = q.order_by(Alert.created_at.desc()).limit(limit).all()
    devs = {d.id: d for d in db.query(IoTDevice).all()}
    return {"count": len(rows), "alerts": [
        {
            "id": a.id, "type": a.type, "level": a.level,
            "message": a.message, "status": a.status,
            "device_id": a.device_id,
            "device_code": devs[a.device_id].device_code if a.device_id in devs else None,
            "resource_id": (devs[a.device_id].resource_id if a.device_id in devs else 0) or 0,
            "created_at": a.created_at.isoformat(),
        } for a in rows
    ]}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """运营人员确认告警已处理：状态置为 resolved，并推送前端实时移除。"""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "告警不存在")
    if alert.status != "resolved":
        alert.status = "resolved"
        db.commit()
        db.refresh(alert)
        logger.info("[iot] 告警 %s 已由 %s 标记为已解决", alert.id, current.username)
        log_audit(
            db, current, "alert_resolve",
            target_type="alert", target_id=alert.id,
            detail=alert.message,
            ip=request.client.host if request.client else None,
        )
        try:
            from .. import ws_broadcast
            ws_broadcast.publish({"type": "alert_resolved", "alert_id": alert.id})
        except Exception:
            pass
    return {"id": alert.id, "status": alert.status}


# ---------------- 告警阈值规则 ----------------

@router.get("/rules", response_model=list[AlertRuleOut])
def list_alert_rules(db: Session = Depends(get_db)):
    """返回全局默认规则（无记录时用配置兜底）+ 所有资源级覆盖规则。"""
    rows = db.query(AlertRule).order_by(AlertRule.resource_id).all()
    out = [_rule_out(db, r) for r in rows]
    if not any(r.resource_id == GLOBAL_RULE_ID for r in rows):
        out.insert(0, AlertRuleOut(
            id=0, resource_id=GLOBAL_RULE_ID, resource_name="全局默认",
            enabled=True, **_default_rule_values(),
        ))
    return out


@router.put("/rules/{resource_id}", response_model=AlertRuleOut)
def upsert_alert_rule(
    resource_id: int,
    data: AlertRuleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新增或更新规则；resource_id=0 表示全局默认。"""
    if resource_id and db.get(Resource, resource_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")

    rule = db.query(AlertRule).filter(AlertRule.resource_id == resource_id).first()
    if rule is None:
        base = _resolve_rule(db, resource_id)  # 继承全局/配置默认
        rule = AlertRule(
            resource_id=resource_id,
            temp_min=base["temp_min"], temp_max=base["temp_max"],
            humidity_max=base["humidity_max"], enabled=True,
        )
        db.add(rule)

    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(rule, key, value)

    if float(rule.temp_min) >= float(rule.temp_max):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "温度下限必须小于上限")

    db.commit()
    db.refresh(rule)
    logger.info(
        "[iot] 告警规则更新：resource=%s 温度[%s, %s] 湿度≤%s 启用=%s（操作人 %s）",
        resource_id, rule.temp_min, rule.temp_max, rule.humidity_max,
        rule.enabled, admin.username,
    )
    return _rule_out(db, rule)


@router.delete("/rules/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    resource_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = db.query(AlertRule).filter(AlertRule.resource_id == resource_id).first()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    db.delete(rule)
    db.commit()
