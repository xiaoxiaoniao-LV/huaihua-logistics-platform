"""订单：创建预约（行锁 + 幂等 + outbox）、查询、状态机流转（CAS）。"""
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import idempotency
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Order, Resource, User
from ..schemas.order import OrderCreate, OrderOut
from ..services import order_state
from ..services.outbox import emit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


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
        Order.status.in_(order_state.ACTIVE_STATUSES),
        Order.start_time.isnot(None),
        Order.end_time.isnot(None),
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


def _invalidate_resource(resource_id: int) -> None:
    try:
        from .. import redis_client as rc
        rc.delete(f"resources:{resource_id}")
    except Exception:
        pass


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    x_idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = "order:create"
    if x_idempotency_key:
        cached = idempotency.begin(db, scope, x_idempotency_key, current.id)
        if cached is not None:
            return JSONResponse(content=cached["body"], status_code=cached["code"])

    try:
        # 行锁资源，避免并发下单同时通过冲突检查
        resource = (
            db.query(Resource)
            .filter(Resource.id == data.resource_id)
            .with_for_update()
            .first()
        )
        if resource is None:
            raise HTTPException(404, "资源不存在")
        if resource.status != "available":
            raise HTTPException(400, f"资源当前不可预约（状态：{resource.status}）")

        _check_resource_window(resource, data.start_time, data.end_time)
        _check_time_overlap(db, resource.id, data.start_time, data.end_time)

        # 按天计费，向上取整由 max(1, …) 保证至少一天
        days = max(1, (data.end_time - data.start_time).total_seconds() / 86400)
        price_per_day = float(resource.price or 0)
        total = Decimal(str(round(price_per_day * days, 2)))
        # 佣金率在下单时锁定，避免后续改费率影响老订单对账
        commission_rate = Decimal(str(round(settings.commission_rate, 4)))

        order = Order(
            resource_id=resource.id,
            supplier_id=resource.user_id,
            demander_id=current.id,
            start_time=data.start_time,
            end_time=data.end_time,
            total_price=total,
            commission_rate=commission_rate,
            commission=None,
            status="pending",
            payment_status="unpaid",
        )
        db.add(order)
        resource.status = "booked"
        db.flush()  # 取 order.id 供事件使用，事务仍未提交

        emit(
            db,
            "order",
            order.id,
            "order_created",
            {
                "order_id": order.id,
                "resource_id": resource.id,
                "total_price": float(total),
            },
        )
        emit(
            db,
            "resource",
            resource.id,
            "resource_updated",
            {"resource_id": resource.id, "status": resource.status},
        )
        db.commit()
        db.refresh(order)
    except Exception:
        if x_idempotency_key:
            idempotency.release(db, scope, x_idempotency_key)
        else:
            db.rollback()
        raise

    _invalidate_resource(order.resource_id)

    body = OrderOut.model_validate(order).model_dump(mode="json")
    if x_idempotency_key:
        idempotency.remember(db, scope, x_idempotency_key, 201, body)
    return body


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
    reason: str | None = Query(None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order).filter(Order.id == order_id).with_for_update().first()
    )
    if order is None:
        raise HTTPException(404, "订单不存在")

    # 先校验状态是否合法/可流转（400），再校验操作者权限（403）
    order_state.validate_transition(order.status, new_status)
    order_state.check_actor(order, current, new_status)
    order_state.transition(db, order, new_status, current, reason=reason)

    emit(
        db,
        "resource",
        order.resource_id,
        "resource_updated",
        {"resource_id": order.resource_id},
    )
    db.commit()
    db.refresh(order)

    _invalidate_resource(order.resource_id)
    return order
