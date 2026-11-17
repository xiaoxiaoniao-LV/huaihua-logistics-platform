"""遥测与设备事件。

Telemetry 为窄表（一行一个点位），便于任意设备扩展点位而不改表结构。
数据量增大后按天 RANGE 分区，读写统一走 `TelemetryRepository` 抽象。
"""
from sqlalchemy import BigInteger, Column, DateTime, Float, Index, JSON, String, UniqueConstraint, func

from ..database import Base


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint("device_id", "point_key", "ts", name="uq_telemetry_point_ts"),
        Index("ix_telemetry_device_ts", "device_id", "ts"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False)
    point_key = Column(String(50), nullable=False)
    ts = Column(DateTime, nullable=False)
    value_num = Column(Float, nullable=True)
    value_text = Column(String(64), nullable=True)
    quality = Column(String(10), nullable=False, default="good")  # good/stale/bad
    # 设备本地序号，用于断网补传时判断丢失与重复
    seq = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class DeviceEvent(Base):
    """设备事件：上下线、告警、越限、门磁、OTA 结果等。"""

    __tablename__ = "device_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    event_type = Column(String(30), nullable=False)   # online/offline/alarm/ota/...
    severity = Column(String(10), nullable=False, default="info")  # info/warn/critical
    message = Column(String(255))
    payload = Column(JSON, nullable=True)
    ts = Column(DateTime, server_default=func.now(), index=True)
    resolved_at = Column(DateTime, nullable=True)
