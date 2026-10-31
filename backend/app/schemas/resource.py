"""资源相关校验模型。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ResourceBase(BaseModel):
    type: str
    name: str
    description: str | None = None
    location: str | None = None
    params: dict | None = None
    available_start: datetime | None = None
    available_end: datetime | None = None
    price: Decimal | None = None
    price_unit: str | None = None


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    location: str | None = None
    params: dict | None = None
    available_start: datetime | None = None
    available_end: datetime | None = None
    price: Decimal | None = None
    price_unit: str | None = None
    status: str | None = None


class ResourceOut(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    created_at: datetime


class ResourceReview(BaseModel):
    """管理员审核资源：通过则上架，驳回落为下架。"""
    approve: bool
    reason: str | None = None
