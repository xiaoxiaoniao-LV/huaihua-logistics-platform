"""订单表：需求方对资源的预约。"""
from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Integer, String, func

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
    # 履约状态机：inquiry → confirmed → ongoing → finished → settled
    # 旁支：rejected / cancelled / expired；保留 pending 兼容旧数据
    status = Column(String(20), nullable=False, default="pending")
    # 支付状态与履约正交：unpaid / paid / refunding / refunded / waived
    payment_status = Column(String(20), nullable=False, default="unpaid")
    cancel_reason = Column(String(255))
    # 乐观锁版本号，状态机 CAS 更新使用
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
