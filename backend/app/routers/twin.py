"""数字孪生：空间树、孪生节点与设备点位绑定。

读接口供指挥大屏（screen 端，允许匿名只读）使用；
写接口仅运维管理员可用。节点状态由绑定设备的可用性与数据新鲜度聚合而来。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_screen_viewer, require_admin
from ..models import (
    Alert, DeviceEvent, DevicePoint, IoTDevice, Space, TwinBinding, TwinNode, User,
)
from ..schemas.twin import TwinBindingIn, TwinNodeIn
from ..services import telemetry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/twin", tags=["twin"])

_STATUS_RANK = {
    "online": 0, "unknown": 1, "offline": 2, "degraded": 3, "alarm": 4, "maintenance": 5,
}


def _binding_map(db: Session, node_ids: list[int]) -> dict[int, list[dict]]:
    """按节点聚合绑定点位的最新值。"""
    if not node_ids:
        return {}
    bindings = db.query(TwinBinding).filter(TwinBinding.twin_node_id.in_(node_ids)).all()
    device_ids = sorted({b.device_id for b in bindings})
    if not device_ids:
        return {}
    devices = {d.id: d for d in db.query(IoTDevice).filter(IoTDevice.id.in_(device_ids)).all()}
    points = {
        (p.device_id, p.point_key): p
        for p in db.query(DevicePoint).filter(DevicePoint.device_id.in_(device_ids)).all()
    }
    latest = telemetry.latest_rows(db, device_ids)

    out: dict[int, list[dict]] = {}
    for binding in bindings:
        device = devices.get(binding.device_id)
        point = points.get((binding.device_id, binding.point_key))
        if device is None or point is None:
            continue
        row = latest.get((binding.device_id, binding.point_key))
        out.setdefault(binding.twin_node_id, []).append(
            {
                "id": binding.id,
                "binding_type": binding.binding_type,
                "device_code": device.device_code,
                "device_name": device.name,
                "device_status": device.status or "unknown",
                "point_key": binding.point_key,
                "name": point.name,
                "unit": point.unit,
                "data_type": point.data_type,
                "value": telemetry.point_value(row, point),
                "quality": row.quality if row else "unknown",
                "ts": row.ts.isoformat() if row else None,
            }
        )
    return out


def _node_status(bindings: list[dict]) -> str:
    if not bindings:
        return "unknown"
    worst = "online"
    for item in bindings:
        state = item["device_status"]
        if state == "online" and item["quality"] in {"stale", "bad"}:
            state = "degraded"
        if _STATUS_RANK.get(state, 1) > _STATUS_RANK.get(worst, 0):
            worst = state
    return worst


def _rollup_status(items: dict[int, dict]) -> None:
    """容器节点（库区/库房）继承子节点的最坏状态，让大屏自上而下都能看出异常。"""
    def resolve(node: dict) -> str:
        states = [node["status"]] + [resolve(child) for child in node["children"]]
        worst = "unknown"
        found = False
        for state in states:
            if state == "unknown" and not found:
                continue
            if not found or _STATUS_RANK.get(state, 1) > _STATUS_RANK.get(worst, 0):
                worst, found = state, True
        node["status"] = worst if found else "unknown"
        return node["status"]

    for item in items.values():
        if item["parent_id"] is None:
            resolve(item)


@router.get("/spaces")
def space_tree(db: Session = Depends(get_db)):
    """空间树：园区 → 库区 → 库房 → 库门/月台 → 设备位。"""
    rows = db.query(Space).order_by(Space.sort, Space.id).all()
    items = {
        s.id: {
            "id": s.id, "code": s.code, "name": s.name, "kind": s.kind,
            "parent_id": s.parent_id, "capacity": s.capacity, "geo": s.geo,
            "sort": s.sort, "enabled": bool(s.enabled), "children": [],
        }
        for s in rows
    }
    roots: list[dict] = []
    for space in rows:
        item = items[space.id]
        parent = items.get(space.parent_id)
        (parent["children"] if parent else roots).append(item)
    return {"count": len(rows), "tree": roots}


def _build_tree(db: Session) -> dict:
    """孪生节点树 + 绑定值 + 状态汇总，供 tree 与 snapshot 复用。"""
    nodes = db.query(TwinNode).order_by(TwinNode.sort, TwinNode.id).all()
    bindings = _binding_map(db, [node.id for node in nodes])

    items: dict[int, dict] = {}
    for node in nodes:
        bound = bindings.get(node.id, [])
        items[node.id] = {
            "id": node.id, "node_key": node.node_key, "name": node.name,
            "node_type": node.node_type, "parent_id": node.parent_id,
            "space_id": node.space_id, "model_ref": node.model_ref,
            "transform": node.transform, "sort": node.sort,
            "status": _node_status(bound), "bindings": bound, "children": [],
        }

    roots: list[dict] = []
    for node in nodes:
        item = items[node.id]
        parent = items.get(node.parent_id)
        (parent["children"] if parent else roots).append(item)

    _rollup_status(items)

    summary = {key: 0 for key in _STATUS_RANK}
    for item in items.values():
        summary[item["status"]] = summary.get(item["status"], 0) + 1

    flat = [{k: v for k, v in item.items() if k != "children"} for item in items.values()]
    return {"count": len(nodes), "summary": summary, "tree": roots, "flat": flat}


@router.get("/tree")
def twin_tree(
    db: Session = Depends(get_db),
    _viewer: User | None = Depends(get_screen_viewer),
):
    """孪生节点树 + 每个节点绑定的实时值，供大屏四级下钻。"""
    return {"generated_at": datetime.now().isoformat(), **_build_tree(db)}


@router.get("/snapshot")
def twin_snapshot(
    alert_limit: int = Query(20, ge=1, le=100),
    event_limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _viewer: User | None = Depends(get_screen_viewer),
):
    """大屏一次性读模型：树 + 设备点位 + 活动告警 + 最近事件。

    指挥室只读端每个刷新周期只打这一个接口，避免多请求拼接造成画面跳变。
    """
    now = datetime.now()
    tree = _build_tree(db)

    devices = db.query(IoTDevice).order_by(IoTDevice.id).all()
    latest = telemetry.latest_rows(db, [d.id for d in devices])
    point_counts: dict[int, int] = {}
    for (device_id, _key) in latest:
        point_counts[device_id] = point_counts.get(device_id, 0) + 1

    device_rows = [
        {
            "device_code": d.device_code,
            "name": d.name,
            "device_type": d.device_type,
            "status": d.status or "unknown",
            "quality": d.quality or "unknown",
            "resource_id": d.resource_id or 0,
            "space_id": d.space_id,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "age_ms": telemetry._age_ms(d.last_seen_at, now),
            "point_count": point_counts.get(d.id, 0),
        }
        for d in devices
    ]
    device_status: dict[str, int] = {}
    for item in device_rows:
        device_status[item["status"]] = device_status.get(item["status"], 0) + 1

    alerts = (
        db.query(Alert)
        .filter(Alert.status == "active")
        .order_by(Alert.created_at.desc())
        .limit(alert_limit)
        .all()
    )
    device_by_id = {d.id: d for d in devices}
    alert_rows = [
        {
            "id": a.id, "type": a.type, "level": a.level, "message": a.message,
            "device_code": device_by_id[a.device_id].device_code if a.device_id in device_by_id else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]

    events = db.query(DeviceEvent).order_by(DeviceEvent.ts.desc()).limit(event_limit).all()
    event_rows = [
        {
            "id": e.id,
            "device_code": device_by_id[e.device_id].device_code if e.device_id in device_by_id else None,
            "event_type": e.event_type, "severity": e.severity, "message": e.message,
            "ts": e.ts.isoformat() if e.ts else None,
            "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        }
        for e in events
    ]

    return {
        "generated_at": now.isoformat(),
        **tree,
        "devices": {
            "total": len(device_rows),
            "by_status": device_status,
            "items": device_rows,
        },
        "alerts": {"count": len(alert_rows), "items": alert_rows},
        "events": {"count": len(event_rows), "items": event_rows},
    }


@router.get("/nodes/{node_key}")
def get_node(node_key: str, db: Session = Depends(get_db)):
    node = db.query(TwinNode).filter(TwinNode.node_key == node_key).first()
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "孪生节点不存在")
    bound = _binding_map(db, [node.id]).get(node.id, [])
    return {
        "id": node.id, "node_key": node.node_key, "name": node.name,
        "node_type": node.node_type, "parent_id": node.parent_id,
        "space_id": node.space_id, "model_ref": node.model_ref,
        "transform": node.transform, "sort": node.sort,
        "status": _node_status(bound), "bindings": bound,
    }


@router.post("/nodes")
def upsert_node(
    data: TwinNodeIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """按 node_key 新增或更新孪生节点（幂等配置接口）。"""
    node = db.query(TwinNode).filter(TwinNode.node_key == data.node_key).first()
    created = node is None
    if created:
        node = TwinNode(node_key=data.node_key, name=data.name, node_type=data.node_type)
        db.add(node)
        db.flush()

    if data.parent_id is not None:
        if data.parent_id == node.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "节点不能以自身为父节点")
        parent = db.get(TwinNode, data.parent_id)
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "父节点不存在")
        cursor = parent
        while cursor is not None:
            if cursor.id == node.id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "父子关系成环")
            cursor = db.get(TwinNode, cursor.parent_id) if cursor.parent_id else None

    if data.space_id is not None and db.get(Space, data.space_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "空间不存在")

    node.name = data.name
    node.node_type = data.node_type
    node.parent_id = data.parent_id
    node.space_id = data.space_id
    node.model_ref = data.model_ref
    node.transform = data.transform
    node.sort = data.sort
    db.commit()
    db.refresh(node)
    logger.info("[twin] 节点 %s 已%s（操作人 %s）", node.node_key, "创建" if created else "更新", admin.username)
    return {"created": created, "id": node.id, "node_key": node.node_key}


@router.post("/bindings")
def bind_point(
    data: TwinBindingIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把设备点位绑定到孪生节点；重复绑定视为更新绑定类型。"""
    node = db.query(TwinNode).filter(TwinNode.node_key == data.node_key).first()
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "孪生节点不存在")
    device = db.query(IoTDevice).filter(IoTDevice.device_code == data.device_code).first()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    try:
        telemetry.resolve_points(db, device, [data.point_key])
    except telemetry.UnknownPointsError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    binding = (
        db.query(TwinBinding)
        .filter(
            TwinBinding.twin_node_id == node.id,
            TwinBinding.device_id == device.id,
            TwinBinding.point_key == data.point_key,
        )
        .first()
    )
    created = binding is None
    if created:
        binding = TwinBinding(
            twin_node_id=node.id,
            device_id=device.id,
            point_key=data.point_key,
            binding_type=data.binding_type,
        )
        db.add(binding)
    else:
        binding.binding_type = data.binding_type
    db.commit()
    db.refresh(binding)
    logger.info(
        "[twin] 绑定 %s.%s -> %s（%s，操作人 %s）",
        device.device_code, data.point_key, node.node_key,
        "新增" if created else "更新", admin.username,
    )
    return {"created": created, "id": binding.id, "node_key": node.node_key,
            "device_code": device.device_code, "point_key": binding.point_key,
            "binding_type": binding.binding_type}


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_binding(
    binding_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    binding = db.get(TwinBinding, binding_id)
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "绑定不存在")
    db.delete(binding)
    db.commit()
