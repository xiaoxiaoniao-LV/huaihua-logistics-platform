"""评价表：订单完成后的双向评价。"""
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func

from ..database import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    from_user_id = Column(BigInteger, nullable=False)
    to_user_id = Column(BigInteger, nullable=False)
    rating = Column(Integer, default=5)  # 1-5
    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
