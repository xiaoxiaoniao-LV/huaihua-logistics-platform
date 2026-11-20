"""支付：下单获取收银台、sandbox 模拟支付、支付宝异步通知。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
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
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """sandbox 模拟收银台：打开即视为支付成功。

    仅订单相关方（需求方/供给方/管理员）可触发，防止伪造 trade_no 越权支付他人订单。
    生产环境关闭（payment_mode != sandbox 时返回 404）。
    """
    if settings.payment_mode != "sandbox":
        raise HTTPException(404, "模拟收银台未启用")
    order = _load_order(db, order_id, current)
    if payment._order_id_from_trade_no(trade_no) != order_id:
        raise HTTPException(400, "交易号与订单不匹配")
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
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    """支付宝异步通知。

    支付宝真实回调为 form-urlencoded，需返回纯文本 success 才停止重试；
    本机联调/测试用 JSON，保持原有 JSON 响应便于断言。
    """
    content_type = request.headers.get("content-type", "")
    is_form = content_type.startswith("application/x-www-form-urlencoded")
    if is_form:
        payload = dict(await request.form())
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    ok, msg = payment.handle_alipay_notify(db, payload)
    if ok:
        db.commit()
    else:
        db.rollback()
        logger.warning("[payment] 通知处理失败：%s", msg)

    if is_form:
        return PlainTextResponse("success" if ok else "fail")
    return {"code": "10000" if ok else "40004", "msg": msg}
