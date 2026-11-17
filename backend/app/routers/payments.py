"""支付：下单获取收银台、sandbox 模拟支付、支付宝异步通知。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Order, User
from ..services import payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

_TERMINAL = {"cancelled", "rejected", "expired"}


def _load_order(db: Session, order_id: int, user: User) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")
    if user.role != "admin" and user.id not in (order.demander_id, order.supplier_id):
        raise HTTPException(403, "无权操作此订单")
    if order.status in _TERMINAL:
        raise HTTPException(400, f"订单已终结（{order.status}），不可支付")
    return order


@router.post("/{order_id}/intent")
def create_intent(
    order_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _load_order(db, order_id, current)
    if order.payment_status == "paid":
        return {"already_paid": True, "order_id": order.id}
    try:
        trade = payment.create_trade(order)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"already_paid": False, "order_id": order.id, **trade}


@router.get("/mock-checkout")
def mock_checkout(
    order_id: int = Query(...),
    trade_no: str = Query(...),
    db: Session = Depends(get_db),
):
    """sandbox 模拟收银台：打开即视为支付成功。生产环境关闭。"""
    if settings.payment_mode != "sandbox":
        raise HTTPException(404, "模拟收银台未启用")
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")
    payment.apply_event(
        db,
        order,
        payment.PROVIDER_ALIPAY,
        trade_no,
        "paid",
        float(order.total_price or 0),
        {"mock": True},
    )
    db.commit()
    db.refresh(order)
    return {
        "order_id": order.id,
        "payment_status": order.payment_status,
        "trade_no": trade_no,
        "next": "/orders",
    }


@router.post("/notify/alipay")
def alipay_notify(payload: dict, db: Session = Depends(get_db)):
    """支付宝异步通知（sandbox 简化版，生产需 RSA2 验签）。"""
    ok, msg = payment.handle_alipay_notify(db, payload)
    if ok:
        db.commit()
    else:
        db.rollback()
        logger.warning("[payment] 通知处理失败：%s", msg)
    return {"code": "10000" if ok else "40004", "msg": msg}
