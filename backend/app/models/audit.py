"""审计日志表。"""
from sqlalchemy import BigInteger, Column, DateTime, String, func

from ..database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    username = Column(String(50))
    action = Column(String(50), index=True)  # resource_review / user_update / alert_resolve ...
    target_type = Column(String(50))
    target_id = Column(BigInteger, nullable=True)
    detail = Column(String(255))
    ip = Column(String(45))
    created_at = Column(DateTime, server_default=func.now(), index=True)
