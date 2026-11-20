"""支付服务：支付宝沙箱旁路。

设计：支付与履约解耦，支付失败/未支付不影响线下合同履约；
所有支付事件落 `payment_events`，以 (provider, provider_txn_id) 唯一约束去重，
重复通知只生效一次。真实支付宝对接时，只需在此实现下单与验签，路由层不变。
"""
import base64
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
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


def _sign_content(payload: dict) -> str:
    """按支付宝规则拼接待验签串：剔除 sign/sign_type，按键名升序，值保持原文。"""
    items = [
        f"{k}={v}"
        for k, v in payload.items()
        if k not in ("sign", "sign_type") and v is not None and v != ""
    ]
    return "&".join(sorted(items))


def _load_alipay_public_key(text: str):
    """兼容 PEM 与支付宝后台拷贝的裸 base64 公钥。"""
    text = text.strip().replace("\\n", "\n")
    if "BEGIN PUBLIC KEY" not in text:
        body = "".join(text.split())
        text = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
            + "\n-----END PUBLIC KEY-----"
        )
    return load_pem_public_key(text.encode("utf-8"))


def verify_alipay_sign(payload: dict) -> tuple[bool, str]:
    """校验支付宝异步通知的 RSA2(SHA256withRSA) 签名。"""
    sign = str(payload.get("sign") or "")
    if not sign:
        return False, "缺少签名"
    key_text = settings.alipay_public_key.strip()
    if not key_text:
        return False, "未配置支付宝公钥"
    try:
        public_key = _load_alipay_public_key(key_text)
        public_key.verify(
            base64.b64decode(sign),
            _sign_content(payload).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature:
        return False, "签名校验失败"
    except Exception:  # 公钥格式错误、base64 非法等，详情仅记日志不返回给调用方
        logger.warning("[payment] 支付宝验签异常", exc_info=True)
        return False, "验签异常"
    return True, "ok"


def _parse_order_id(payload: dict, trade_no: str) -> int | None:
    raw = payload.get("order_id") or payload.get("out_trade_no")
    if raw is not None and str(raw).strip():
        try:
            return int(str(raw).strip())
        except ValueError:
            pass
    return _order_id_from_trade_no(trade_no)


def handle_alipay_notify(db: Session, payload: dict) -> tuple[bool, str]:
    """处理支付宝异步通知。

    配置 `ALIPAY_PUBLIC_KEY` 后强制 RSA2 验签，并校验 app_id / seller_id / 金额；
    未配置公钥时只允许 sandbox 模式（本机模拟通知），避免生产裸奔。
    """
    if settings.alipay_public_key:
        ok, msg = verify_alipay_sign(payload)
        if not ok:
            return False, msg
        if settings.alipay_app_id and str(payload.get("app_id") or "") != settings.alipay_app_id:
            return False, "app_id 与配置不一致"
        if settings.alipay_seller_id and str(payload.get("seller_id") or "") != settings.alipay_seller_id:
            return False, "seller_id 与配置不一致"
    elif settings.payment_mode != "sandbox":
        return False, "未配置支付宝公钥，拒绝处理异步通知"

    trade_no = str(payload.get("trade_no") or "")
    trade_status = str(payload.get("trade_status") or "")
    event_type = _STATUS_MAP.get(trade_status)
    if event_type is None:
        return False, f"不支持的交易状态：{trade_status}"

    order_id = _parse_order_id(payload, trade_no)
    if not order_id:
        return False, "无法从通知中解析订单号"
    order = db.get(Order, int(order_id))
    if order is None:
        return False, "订单不存在"

    amount = payload.get("total_amount")
    if amount is not None and order.total_price is not None:
        try:
            if abs(float(amount) - float(order.total_price)) > 0.01:
                return False, "通知金额与订单金额不一致"
        except (TypeError, ValueError):
            return False, "通知金额格式非法"

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
