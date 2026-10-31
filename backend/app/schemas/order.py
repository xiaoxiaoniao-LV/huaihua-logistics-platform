"""订单相关校验模型。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class OrderCreate(BaseModel):
    resource_id: int
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def _check_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time 必须晚于 start_time")
        return self


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    supplier_id: int
    demander_id: int
    start_time: datetime
    end_time: datetime
    total_price: Decimal
    commission_rate: Decimal
    commission: Decimal | None = None
    status: str
    created_at: datetime
