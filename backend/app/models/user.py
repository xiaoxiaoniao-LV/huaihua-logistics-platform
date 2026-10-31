"""用户表。"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, func, true

from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="demander")  # supplier / demander / admin
    company_name = Column(String(100))
    contact = Column(String(50))
    credit_score = Column(Integer, default=100)
    # 禁用账号：被禁用的用户无法通过鉴权
    is_active = Column(Boolean, nullable=False, server_default=true(), default=True)
    created_at = Column(DateTime, server_default=func.now())
