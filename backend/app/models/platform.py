"""平台可靠性基建：事务外盒（outbox）与幂等键。

outbox：业务写库与事件投递同事务落库，由 worker 异步投递 WS/MQTT，
避免「数据库已提交但消息丢失」。
幂等键：下单、支付回调等写操作携带 Idempotency-Key，重复请求返回首次结果。
"""
from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, String, UniqueConstraint, func

from ..database import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type = Column(String(40), nullable=False)   # order/resource/device
    aggregate_id = Column(BigInteger, nullable=True)
    event_type = Column(String(60), nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending/published/failed
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    published_at = Column(DateTime, nullable=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "idem_key", name="uq_idem_scope_key"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scope = Column(String(40), nullable=False)
    idem_key = Column(String(100), nullable=False)
    user_id = Column(BigInteger, nullable=True)
    request_hash = Column(String(64))
    response_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="processing")  # processing/done
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
