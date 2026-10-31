"""订单表：需求方对资源的预约。"""
from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, String, func

from ..database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False, index=True)
    supplier_id = Column(BigInteger, nullable=False)
    demander_id = Column(BigInteger, nullable=False)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    total_price = Column(DECIMAL(12, 2))
    commission_rate = Column(DECIMAL(5, 4), nullable=False, default=0.1000)  # 下单时锁定的佣金率，避免后续改费率影响老订单
    commission = Column(DECIMAL(12, 2), nullable=True)                       # finished 时结算写入，cancelled 时为 null
    status = Column(String(20), nullable=False, default="pending")  # pending/confirmed/ongoing/finished/cancelled
    created_at = Column(DateTime, server_default=func.now())
