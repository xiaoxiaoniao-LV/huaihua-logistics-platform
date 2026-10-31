"""订单：创建预约（含时段冲突检查）、查询、状态流转（含佣金结算）。"""
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Order, Resource, User
from ..schemas.order import OrderCreate, OrderOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])

# 资源未终结订单的状态（需要参与冲突检查）
_ACTIVE_STATUS = {"pending", "confirmed", "ongoing"}


def _check_resource_window(resource: Resource, start_time, end_time):
    """检查新订单是否落在资源的可用窗口内。"""
    if resource.available_start and start_time < resource.available_start:
        raise HTTPException(400, f"下单开始时间早于资源可用起点 {resource.available_start}")
    if resource.available_end and end_time > resource.available_end:
        raise HTTPException(400, f"下单结束时间晚于资源可用终点 {resource.available_end}")


def _check_time_overlap(db: Session, resource_id: int, start_time, end_time, exclude_order_id: int | None = None):
    """同资源未终结订单的时段重叠检测。重叠条件：A.start < B.end AND A.end > B.start。"""
    query = db.query(Order).filter(
        Order.resource_id == resource_id,
        Order.status.in_(_ACTIVE_STATUS),
        Order.start_time.isnot(None),
        Order.end_time.isnot(None),
        # 重叠判定：新订单起点 < 已有订单终点 AND 新订单终点 > 已有订单起点
        end_time > Order.start_time,
        start_time < Order.end_time,
    )
    if exclude_order_id is not None:
        query = query.filter(Order.id != exclude_order_id)
    conflict = query.first()
    if conflict is not None:
        raise HTTPException(
            409,
            f"时段冲突：该资源已存在订单 #{conflict.id}（{conflict.start_time} ~ {conflict.end_time}，状态 {conflict.status}）",
        )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, data.resource_id)
    if resource is None:
        raise HTTPException(404, "资源不存在")
    if resource.status != "available":
        raise HTTPException(400, f"资源当前不可预约（状态：{resource.status}）")

    # 1) 资源可用窗口检查
    _check_resource_window(resource, data.start_time, data.end_time)

    # 2) 同资源未终结订单时段重叠检查
    _check_time_overlap(db, resource.id, data.start_time, data.end_time)

    # 3) 价格计算：按天（向上取整确保整天计费）
    days = max(1, (data.end_time - data.start_time).total_seconds() / 86400)
    price_per_day = float(resource.price or 0)
    total = Decimal(str(round(price_per_day * days, 2)))

    # 4) 佣金率在下单时锁定（避免后续改费率影响老订单对账）
    commission_rate = Decimal(str(round(settings.commission_rate, 4)))

    order = Order(
        resource_id=resource.id,
        supplier_id=resource.user_id,
        demander_id=current.id,
        start_time=data.start_time,
        end_time=data.end_time,
        total_price=total,
        commission_rate=commission_rate,
        commission=None,  # finished 时结算
        status="pending",
    )
    db.add(order)
    # 锁资源（简化策略：有已终结订单时保持 available，pending 视为预占）
    resource.status = "booked"
    db.commit()
    db.refresh(order)

    # 5) Redis 缓存失效（资源列表、单资源详情）
    try:
        from .. import redis_client as rc
        rc.delete(f"resources:{resource.id}")
    except Exception:
        pass

    # 6) WebSocket 推送
    try:
        from .. import ws_broadcast
        ws_broadcast.publish({"type": "order_created", "order_id": order.id, "resource_id": resource.id})
        ws_broadcast.publish({"type": "resource_updated", "resource_id": resource.id, "status": resource.status})
    except Exception:
        logger.warning("[orders] WS 推送失败", exc_info=True)

    return order


@router.get("", response_model=list[OrderOut])
def list_orders(
    response: Response,
    mine: str | None = Query(None),  # mine=demander 或 mine=supplier
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    q = db.query(Order)
    if mine == "demander":
        q = q.filter(Order.demander_id == current.id)
    elif mine == "supplier":
        q = q.filter(Order.supplier_id == current.id)
    elif current.role != "admin":
        # 非 admin 默认只看自己的
        q = q.filter(or_(Order.demander_id == current.id, Order.supplier_id == current.id))
    response.headers["X-Total-Count"] = str(q.count())
    return (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


@router.put("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    new_status: str = Query(...),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")
    if current.role != "admin" and order.demander_id != current.id and order.supplier_id != current.id:
        raise HTTPException(403, "无权操作此订单")

    allowed = {"pending", "confirmed", "ongoing", "finished", "cancelled"}
    if new_status not in allowed:
        raise HTTPException(400, f"无效状态，允许值：{allowed}")

    old_status = order.status
    order.status = new_status

    # --- 状态变迁副作用 ---
    # 取消/终结：释放资源
    release_statuses = {"cancelled", "finished"}
    if new_status in release_statuses and old_status not in release_statuses:
        res = db.get(Resource, order.resource_id)
        if res and res.status == "booked":
            # 只有没有其他未终结订单占用该资源时才释放回 available
            other_active = (
                db.query(Order)
                .filter(
                    Order.resource_id == order.resource_id,
                    Order.status.in_(_ACTIVE_STATUS - {"finished", "cancelled"}),
                    Order.id != order.id,
                )
                .count()
            )
            if other_active == 0:
                res.status = "available"

    # finished：结算佣金（按订单创建时锁定的费率）
    if new_status == "finished" and order.commission is None:
        order.commission = Decimal(
            str(round(float(order.total_price or 0) * float(order.commission_rate or 0), 2))
        )

    # cancelled：清空 commission（如果之前有写入）
    if new_status == "cancelled":
        order.commission = None

    db.commit()
    db.refresh(order)

    # Redis 缓存失效
    try:
        from .. import redis_client as rc
        rc.delete(f"resources:{order.resource_id}")
    except Exception:
        pass

    # WebSocket 推送
    try:
        from .. import ws_broadcast
        ws_broadcast.publish({"type": "order_status_changed", "order_id": order.id, "new_status": new_status})
        # 资源状态可能随订单变迁（booked ↔ available），通知前端刷新冷链箱颜色
        res = db.get(Resource, order.resource_id)
        if res:
            ws_broadcast.publish({"type": "resource_updated", "resource_id": res.id, "status": res.status})
    except Exception:
        logger.warning("[orders] WS 推送失败", exc_info=True)

    return order
