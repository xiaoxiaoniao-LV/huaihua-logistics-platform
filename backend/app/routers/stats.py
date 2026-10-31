"""运营统计：总览指标、最近 N 天趋势、按资源类型的经营情况（仅管理员）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Alert, IoTDevice, Order, Resource, Review, User

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _count_by(rows) -> dict[str, int]:
    return {str(k): int(v) for k, v in rows}


@router.get("/overview")
def overview(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    resource_status = _count_by(
        db.query(Resource.status, func.count(Resource.id)).group_by(Resource.status).all()
    )
    order_status = _count_by(
        db.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    )
    user_role = _count_by(
        db.query(User.role, func.count(User.id)).group_by(User.role).all()
    )
    device_status = _count_by(
        db.query(IoTDevice.status, func.count(IoTDevice.id)).group_by(IoTDevice.status).all()
    )
    alert_status = _count_by(
        db.query(Alert.status, func.count(Alert.id)).group_by(Alert.status).all()
    )

    finished_amount = float(
        db.query(func.coalesce(func.sum(Order.total_price), 0))
        .filter(Order.status == "finished")
        .scalar()
        or 0
    )
    commission_total = float(
        db.query(func.coalesce(func.sum(Order.commission), 0))
        .filter(Order.status == "finished")
        .scalar()
        or 0
    )
    finished_count = int(order_status.get("finished", 0))
    avg_rating = db.query(func.avg(Review.rating)).scalar()

    return {
        "resources": {
            "total": sum(resource_status.values()),
            "by_status": resource_status,
            "available": resource_status.get("available", 0),
            "booked": resource_status.get("booked", 0),
            "pending": resource_status.get("pending", 0),
        },
        "orders": {
            "total": sum(order_status.values()),
            "by_status": order_status,
            "finished": finished_count,
            "cancelled": order_status.get("cancelled", 0),
        },
        "revenue": {
            "finished_amount": round(finished_amount, 2),
            "commission": round(commission_total, 2),
            "avg_order_value": round(finished_amount / finished_count, 2) if finished_count else 0.0,
        },
        "users": {"total": sum(user_role.values()), "by_role": user_role},
        "devices": {
            "total": sum(device_status.values()),
            "online": device_status.get("online", 0),
            "offline": device_status.get("offline", 0),
        },
        "alerts": {
            "total": sum(alert_status.values()),
            "active": alert_status.get("active", 0),
            "resolved": alert_status.get("resolved", 0),
        },
        "reviews": {"avg_rating": round(float(avg_rating), 2) if avg_rating is not None else 0.0},
    }


@router.get("/trend")
def trend(
    days: int = Query(7, ge=1, le=90),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """最近 N 天：每日新建订单数、成交额、佣金、新增告警数。"""
    today = datetime.now().date()
    start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())

    order_rows = (
        db.query(
            func.date(Order.created_at).label("d"),
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0),
            func.coalesce(func.sum(Order.commission), 0),
        )
        .filter(Order.created_at >= start)
        .group_by(func.date(Order.created_at))
        .all()
    )
    alert_rows = (
        db.query(func.date(Alert.created_at).label("d"), func.count(Alert.id))
        .filter(Alert.created_at >= start)
        .group_by(func.date(Alert.created_at))
        .all()
    )

    orders_by_day = {str(r[0]): r for r in order_rows}
    alerts_by_day = {str(r[0]): int(r[1]) for r in alert_rows}

    out = []
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        row = orders_by_day.get(day)
        out.append({
            "date": day,
            "orders": int(row[1]) if row else 0,
            "amount": round(float(row[2]), 2) if row else 0.0,
            "commission": round(float(row[3]), 2) if row else 0.0,
            "alerts": alerts_by_day.get(day, 0),
        })
    return {"days": days, "items": out}


@router.get("/resources")
def resource_stats(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """按资源类型统计供给量、占用率与累计成交额。"""
    rows = (
        db.query(Resource.type, Resource.status, func.count(Resource.id))
        .group_by(Resource.type, Resource.status)
        .all()
    )
    type_names = {"warehouse": "仓库", "cold_box": "冷链箱", "vehicle": "运力", "equipment": "设备"}

    stats: dict[str, dict] = {}
    for rtype, rstatus, count in rows:
        item = stats.setdefault(rtype, {
            "type": rtype, "name": type_names.get(rtype, rtype),
            "total": 0, "available": 0, "booked": 0, "pending": 0, "offline": 0,
            "finished_amount": 0.0, "utilization": 0.0,
        })
        item["total"] += int(count)
        if rstatus in item:
            item[rstatus] += int(count)

    amount_rows = (
        db.query(Resource.type, func.coalesce(func.sum(Order.total_price), 0))
        .join(Order, Order.resource_id == Resource.id)
        .filter(Order.status == "finished")
        .group_by(Resource.type)
        .all()
    )
    for rtype, amount in amount_rows:
        if rtype in stats:
            stats[rtype]["finished_amount"] = round(float(amount), 2)

    for item in stats.values():
        item["utilization"] = round(item["booked"] / item["total"], 3) if item["total"] else 0.0

    return {"items": sorted(stats.values(), key=lambda x: x["total"], reverse=True)}
