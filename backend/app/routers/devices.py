"""设备管理：注册、查询、绑定资源、上下线、遥测历史。

设备与资源是多对一关系：一个资源（冷链箱/仓库）可挂多个传感器，
设备表通过 resource_id 关联；resource_id=0 表示尚未绑定。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import IoTData, IoTDevice, Resource, User
from ..schemas.device import DeviceCreate, DeviceOut, DeviceUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _ensure_can_manage(current: User, dev: IoTDevice, db: Session) -> None:
    """管理员可管理全部设备；普通用户只能管理自己资源上绑定的设备。"""
    if current.role == "admin":
        return
    if dev.resource_id:
        res = db.get(Resource, dev.resource_id)
        if res is not None and res.user_id == current.id:
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权管理该设备")


def _last_point(db: Session, device_id: int) -> IoTData | None:
    return (
        db.query(IoTData)
        .filter(IoTData.device_id == device_id)
        .order_by(IoTData.recorded_at.desc())
        .first()
    )


def _to_out(db: Session, dev: IoTDevice) -> DeviceOut:
    resource = db.get(Resource, dev.resource_id) if dev.resource_id else None
    last = _last_point(db, dev.id)
    return DeviceOut(
        id=dev.id,
        device_code=dev.device_code,
        device_type=dev.device_type,
        resource_id=dev.resource_id or 0,
        status=dev.status or "offline",
        resource_name=resource.name if resource else None,
        last_seen=last.recorded_at if last else None,
        last_temperature=last.temperature if last else None,
        last_humidity=last.humidity if last else None,
    )


@router.get("", response_model=list[DeviceOut])
def list_devices(
    resource_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    q = db.query(IoTDevice)
    if resource_id is not None:
        q = q.filter(IoTDevice.resource_id == resource_id)
    if status_filter:
        q = q.filter(IoTDevice.status == status_filter)
    return [_to_out(db, d) for d in q.order_by(IoTDevice.id).all()]


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(
    data: DeviceCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if db.query(IoTDevice).filter(IoTDevice.device_code == data.device_code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "设备编码已存在")
    if data.resource_id:
        if db.get(Resource, data.resource_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "要绑定的资源不存在")

    dev = IoTDevice(
        device_code=data.device_code,
        device_type=data.device_type,
        resource_id=data.resource_id or 0,
        status="offline",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return _to_out(db, dev)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    data: DeviceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    _ensure_can_manage(current, dev, db)

    payload = data.model_dump(exclude_unset=True)
    if "resource_id" in payload and payload["resource_id"]:
        if db.get(Resource, payload["resource_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "要绑定的资源不存在")
    if "status" in payload and payload["status"] not in ("online", "offline"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "状态只能是 online / offline")

    for key, value in payload.items():
        setattr(dev, key, value)
    db.commit()
    db.refresh(dev)
    return _to_out(db, dev)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    _ensure_can_manage(current, dev, db)
    db.delete(dev)
    db.commit()


@router.get("/{device_id}/telemetry")
def device_telemetry(
    device_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    rows = (
        db.query(IoTData)
        .filter(IoTData.device_id == device_id)
        .order_by(IoTData.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "device_code": dev.device_code,
        "resource_id": dev.resource_id,
        "count": len(rows),
        "data": [
            {
                "temperature": r.temperature,
                "humidity": r.humidity,
                "longitude": r.longitude,
                "latitude": r.latitude,
                "recorded_at": r.recorded_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/auto-bind")
def auto_bind(
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把尚未绑定的设备按顺序绑定到可用冷链箱资源上（演示/初始化用）。"""
    unbound = (
        db.query(IoTDevice)
        .filter(IoTDevice.resource_id == 0)
        .order_by(IoTDevice.id)
        .all()
    )
    if not unbound:
        return {"bound": 0, "detail": "没有待绑定的设备"}

    taken = {
        d.resource_id
        for d in db.query(IoTDevice).filter(IoTDevice.resource_id != 0).all()
    }
    free_resources = [
        r
        for r in db.query(Resource)
        .filter(Resource.type == "cold_box")
        .order_by(Resource.id)
        .all()
        if r.id not in taken
    ]

    bound = 0
    for dev, res in zip(unbound, free_resources):
        dev.resource_id = res.id
        bound += 1
    db.commit()
    logger.info("[devices] auto-bind 完成，绑定 %d 台设备", bound)
    return {"bound": bound, "detail": f"已绑定 {bound} 台设备"}
