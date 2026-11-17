"""空间树：园区 → 库区 → 库房 → 库门/月台 → 设备位。

大屏与孪生共用同一套空间编码，避免两套坐标体系。
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, String, func, true

from ..database import Base


class Space(Base):
    __tablename__ = "spaces"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(BigInteger, nullable=True, index=True)
    # site / area / room / gate / dock / rack
    kind = Column(String(20), nullable=False, default="room")
    capacity = Column(JSON, nullable=True)        # 面积、库容、月台数等
    geo = Column(JSON, nullable=True)             # 经纬度、楼层、平面坐标
    sort = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, server_default=true(), default=True)
    created_at = Column(DateTime, server_default=func.now())
