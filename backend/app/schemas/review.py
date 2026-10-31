"""评价校验模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    order_id: int
    rating: int = Field(ge=1, le=5, description="1-5 星")
    content: str | None = Field(default=None, max_length=500)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    from_user_id: int
    to_user_id: int
    rating: int
    content: str | None = None
    created_at: datetime
    # 聚合字段
    from_username: str | None = None


class UserRatingSummary(BaseModel):
    user_id: int
    count: int
    average: float
    credit_score: int
    reviews: list[ReviewOut]
