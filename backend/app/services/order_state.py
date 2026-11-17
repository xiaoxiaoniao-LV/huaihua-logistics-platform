"""订单履约状态机。

状态：inquiry(pending) → confirmed → ongoing → finished → settled
旁支：rejected / cancelled / expired（48h 未确认）

所有流转走乐观锁 CAS（version），并发下只有一个请求能成功；
副作用（释放资源、结算佣金、写结算单）与状态变更在同一事务内完成。
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Order, Resource, Settlement
from .outbox import emit

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"pending", "confirmed", "ongoing"}

# 允许的流转（pending 兼容旧数据，等价于 inquiry）
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "rejected", "cancelled", "expired"},
    "inquiry": {"confirmed", "rejected", "cancelled", "expired"},
    "confirmed": {"ongoing", "cancelled"},
    "ongoing": {"finished", "cancelled"},
    "finished": {"settled"},
    "settled": set(),
    "rejected": set(),
    "cancelled": set(),
    "expired": set(),
}

# 各流转允许的操作者角色（订单双方 + 管理员）
STATUS_ACTORS: dict[str, set[str]] = {
    "confirmed": {"supplier", "admin"},
    "rejected": {"supplier", "admin"},
    "ongoing": {"supplier", "admin"},
    "finished": {"supplier", "admin"},
    "settled": {"admin"},
    "cancelled": {"demander", "supplier", "admin"},
    "expired": {"admin"},
}


def validate_transition(old: str, new: str) -> None:
    allowed = TRANSITIONS.get(old)
    if allowed is None:
        raise HTTPException(409, f"订单状态异常：{old}")
    if new not in allowed:
        raise HTTPException(
            400, f"不允许的状态流转：{old} → {new}（允许：{sorted(allowed) or '无'}）"
        )


def check_actor(order: Order, user, new_status: str) -> None:
    """校验操作者身份：订单参与方或管理员，且角色允许该流转。"""
    if user.role != "admin" and user.id not in (order.demander_id, order.supplier_id):
        raise HTTPException(403, "无权操作此订单")
    if user.role not in STATUS_ACTORS.get(new_status, set()):
        raise HTTPException(403, f"当前角色无权将订单置为 {new_status}")


def _release_resource(db: Session, order: Order) -> None:
    """释放资源占用：仅当没有其他未终结订单时才回到 available。"""
    res = (
        db.query(Resource)
        .filter(Resource.id == order.resource_id)
        .with_for_update()
        .first()
    )
    if res is None or res.status != "booked":
        return
    others = (
        db.query(Order)
        .filter(
            Order.resource_id == order.resource_id,
            Order.status.in_(ACTIVE_STATUSES),
            Order.id != order.id,
        )
        .count()
    )
    if others == 0:
        res.status = "available"


def ensure_settlement(db: Session, order: Order) -> Settlement:
    """为已完成订单生成结算单（幂等：order_id 唯一）。"""
    existing = db.query(Settlement).filter(Settlement.order_id == order.id).first()
    if existing is not None:
        return existing
    amount = Decimal(str(order.total_price or 0))
    rate = Decimal(str(order.commission_rate or 0))
    commission = Decimal(str(order.commission or 0))
    if commission == 0:
        commission = (amount * rate).quantize(Decimal("0.01"))
        order.commission = commission
    settlement = Settlement(
        order_id=order.id,
        supplier_id=order.supplier_id,
        amount=amount,
        commission_rate=rate,
        commission=commission,
        payable_to_supplier=(amount - commission).quantize(Decimal("0.01")),
        status="pending",
    )
    db.add(settlement)
    return settlement


def transition(
    db: Session,
    order: Order,
    new_status: str,
    actor,
    reason: str | None = None,
) -> Order:
    """CAS 更新订单状态并执行副作用（不 commit，由调用方提交事务）。"""
    validate_transition(order.status, new_status)

    old_status = order.status
    updated = (
        db.query(Order)
        .filter(Order.id == order.id, Order.version == order.version)
        .update(
            {
                Order.status: new_status,
                Order.version: order.version + 1,
                Order.cancel_reason: reason,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        raise HTTPException(409, "订单已被其他请求修改，请刷新后重试")

    db.expire(order)
    db.refresh(order)

    if new_status in {"cancelled", "rejected", "expired", "finished"}:
        _release_resource(db, order)

    if new_status == "finished":
        ensure_settlement(db, order)

    emit(
        db,
        "order",
        order.id,
        "order_status_changed",
        {
            "order_id": order.id,
            "old_status": old_status,
            "new_status": new_status,
            "resource_id": order.resource_id,
        },
    )
    return order


def expire_stale_orders(
    db: Session, now: datetime | None = None, hours: int = 48
) -> list[int]:
    """超时未确认订单置为 expired 并释放资源，返回被处理的订单 id。"""
    now = now or datetime.now()
    cutoff = now - timedelta(hours=hours)
    stale = (
        db.query(Order)
        .filter(Order.status.in_({"pending", "inquiry"}), Order.created_at < cutoff)
        .all()
    )
    expired: list[int] = []
    for order in stale:
        try:
            transition(db, order, "expired", actor=None, reason=f"{hours} 小时未确认，自动关闭")
            expired.append(order.id)
        except HTTPException as e:
            logger.warning("[order-timeout] 订单 %s 取消失败：%s", order.id, e.detail)
    if expired:
        db.commit()
        logger.info("[order-timeout] 已过期订单：%s", expired)
    return expired
