"""资源表：供给方发布的闲置资源（冷链箱位/仓储/运力/设备）。"""
from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, JSON, String, Text, func

from ..database import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)  # 供给方
    type = Column(String(20), nullable=False)  # warehouse / cold_box / vehicle / equipment
    name = Column(String(100), nullable=False)
    description = Column(Text)
    location = Column(String(100))
    params = Column(JSON)  # 参数：温区、尺寸等
    available_start = Column(DateTime)
    available_end = Column(DateTime)
    price = Column(DECIMAL(12, 2))
    price_unit = Column(String(20))
    status = Column(String(20), nullable=False, default="pending")  # pending/available/booked/offline
    created_at = Column(DateTime, server_default=func.now())
