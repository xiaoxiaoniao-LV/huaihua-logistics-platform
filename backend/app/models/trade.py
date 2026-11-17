"""结算与支付事件。

履约状态机（orders.status）与支付状态（orders.payment_status）正交：
线下合同走 manual 支付记录，支付宝沙箱走异步通知，二者都落 payment_events；
结算单在订单 finished 时生成，与支付解耦，避免「未付款不能开工」的死锁。
"""
from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, JSON, String, UniqueConstraint, func

from ..database import Base


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_txn_id", name="uq_payment_provider_txn"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(30), nullable=False)        # alipay_sandbox / manual
    provider_txn_id = Column(String(100), nullable=False)
    event_type = Column(String(30), nullable=False)      # paid / refunded / closed
    amount = Column(DECIMAL(12, 2), nullable=True)
    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (UniqueConstraint("order_id", name="uq_settlement_order"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False)
    supplier_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(DECIMAL(12, 2), nullable=False)               # 订单总额
    commission_rate = Column(DECIMAL(5, 4), nullable=False, default=0.1000)
    commission = Column(DECIMAL(12, 2), nullable=False, default=0)
    payable_to_supplier = Column(DECIMAL(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending/confirmed/paid/void
    remark = Column(String(255))
    settled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
