"""物联网相关表：设备、数据、预警、告警阈值规则。"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, String, func

from ..database import Base


class IoTDevice(Base):
    __tablename__ = "iot_devices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False, index=True)
    device_code = Column(String(50), unique=True, nullable=False)
    device_type = Column(String(30))
    status = Column(String(20), default="offline")  # online / offline


class IoTData(Base):
    __tablename__ = "iot_data"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    longitude = Column(Float)
    latitude = Column(Float)
    recorded_at = Column(DateTime, server_default=func.now(), index=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    type = Column(String(30))
    level = Column(String(20), default="info")  # info / warn / critical
    message = Column(String(255))
    status = Column(String(20), default="active")  # active / resolved
    created_at = Column(DateTime, server_default=func.now())


class AlertRule(Base):
    """告警阈值规则：resource_id=0 表示全局默认，其余为单个资源的覆盖规则。"""

    __tablename__ = "alert_rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False, unique=True, default=0)
    temp_min = Column(Float, nullable=False, default=-30.0)
    temp_max = Column(Float, nullable=False, default=-5.0)
    humidity_max = Column(Float, nullable=False, default=90.0)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
