"""支付服务：支付宝沙箱旁路。

设计：支付与履约解耦，支付失败/未支付不影响线下合同履约；
所有支付事件落 `payment_events`，以 (provider, provider_txn_id) 唯一约束去重，
重复通知只生效一次。真实支付宝对接时，只需在此实现下单与验签，路由层不变。
"""
import logging
import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Order, PaymentEvent
from .outbox import emit

logger = logging.getLogger(__name__)

PROVIDER_ALIPAY = "alipay_sandbox"
PROVIDER_MANUAL = "manual"

# 支付宝交易状态 → 平台事件
_STATUS_MAP = {
    "TRADE_SUCCESS": "paid",
    "TRADE_FINISHED": "paid",
    "TRADE_CLOSED": "closed",
    "REFUND_SUCCESS": "refunded",
}


def create_trade(order: Order) -> dict:
    """创建支付单。sandbox 模式返回本机模拟收银台地址。"""
    if settings.payment_mode == "off":
        raise RuntimeError("支付通道未启用，请走线下合同结算")
    trade_no = f"SBX{order.id}-{int(time.time() * 1000)}"
    return {
        "provider": PROVIDER_ALIPAY,
        "trade_no": trade_no,
        "amount": float(order.total_price or 0),
        "pay_url": f"/api/v1/payments/mock-checkout?order_id={order.id}&trade_no={trade_no}",
    }


def _order_id_from_trade_no(trade_no: str) -> int | None:
    """sandbox 交易号形如 SBX12-1700000000000，从中解出订单 id。"""
    if not trade_no.startswith("SBX"):
        return None
    try:
        return int(trade_no[3:].split("-", 1)[0])
    except (ValueError, IndexError):
        return None


def apply_event(
    db: Session,
    order: Order,
    provider: str,
    provider_txn_id: str,
    event_type: str,
    amount: float | None = None,
    raw: dict | None = None,
) -> bool:
    """登记支付事件并同步订单支付状态。返回 False 表示重复通知。

    不 commit，由调用方控制事务。
    """
    db.add(
        PaymentEvent(
            order_id=order.id,
            provider=provider,
            provider_txn_id=provider_txn_id,
            event_type=event_type,
            amount=amount,
            raw=raw,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("[payment] 重复通知已忽略：%s/%s", provider, provider_txn_id)
        return False

    if event_type == "paid" and order.payment_status != "paid":
        order.payment_status = "paid"
        emit(
            db,
            "order",
            order.id,
            "order_paid",
            {"order_id": order.id, "amount": float(order.total_price or 0)},
        )
    elif event_type == "refunded" and order.payment_status != "refunded":
        order.payment_status = "refunded"
        emit(db, "order", order.id, "order_refunded", {"order_id": order.id})
    return True


def handle_alipay_notify(db: Session, payload: dict) -> tuple[bool, str]:
    """处理支付宝异步通知（sandbox 简化版）。

    生产环境需在此用 alipay_app_id + 应用私钥做 RSA2 验签；
    未配置 app_id 时仅接受本机 sandbox 模拟通知。
    """
    trade_no = str(payload.get("trade_no") or "")
    trade_status = str(payload.get("trade_status") or "")
    event_type = _STATUS_MAP.get(trade_status)
    if event_type is None:
        return False, f"不支持的交易状态：{trade_status}"

    order_id = payload.get("order_id") or _order_id_from_trade_no(trade_no)
    if not order_id:
        return False, "无法从通知中解析订单号"
    order = db.get(Order, int(order_id))
    if order is None:
        return False, "订单不存在"

    amount = payload.get("total_amount")
    ok = apply_event(
        db,
        order,
        PROVIDER_ALIPAY,
        trade_no or f"MOCK-{order.id}-{int(time.time() * 1000)}",
        event_type,
        float(amount) if amount is not None else float(order.total_price or 0),
        payload,
    )
    return ok, "success"
