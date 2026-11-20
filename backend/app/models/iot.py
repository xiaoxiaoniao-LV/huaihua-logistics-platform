"""物联网相关表：设备、数据、预警、告警阈值规则。"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, String, Text, func

from ..database import Base


class IoTDevice(Base):
    __tablename__ = "iot_devices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False, index=True)
    device_code = Column(String(50), unique=True, nullable=False)
    device_type = Column(String(30))
    name = Column(String(100), nullable=True)
    # 所属空间（spaces.id），用于孪生与大屏按空间聚合
    space_id = Column(BigInteger, nullable=True, index=True)
    # online / offline / degraded / alarm / maintenance / unknown
    status = Column(String(20), default="offline")
    # 数据质量：good / stale / bad，与 status 正交，避免「在线但数据过期」
    quality = Column(String(10), nullable=False, default="unknown")
    last_seen_at = Column(DateTime, nullable=True)
    firmware_version = Column(String(20), nullable=False, default="1.0.0")


class OTATask(Base):
    """固件升级任务：一台设备一次升级一条记录。"""

    __tablename__ = "ota_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    from_version = Column(String(20))
    target_version = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/running/success/failed
    message = Column(String(255))
    # 所属灰度批次；stage: canary（灰度）/ full（全量）/ rollback（回滚）
    batch_id = Column(String(32), nullable=True, index=True)
    stage = Column(String(10), nullable=False, default="full")
    created_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class OTABatch(Base):
    """一次固件发布批次：记录灰度范围与阶段，支持续发与整批回滚。"""

    __tablename__ = "ota_batches"

    id = Column(String(32), primary_key=True)
    target_version = Column(String(20), nullable=False)
    # 灰度范围：space_id 或 device_ids（JSON 数组）限定；均为空表示全部设备
    space_id = Column(BigInteger, nullable=True)
    device_ids = Column(Text, nullable=True)
    rollout_percent = Column(BigInteger, nullable=False, default=100)
    # canary / full / rollback
    stage = Column(String(10), nullable=False, default="full")
    # running / done / failed / rolled_back
    status = Column(String(20), nullable=False, default="running")
    # 回滚批次指向被回滚的原批次
    rollback_of = Column(String(32), nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


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
