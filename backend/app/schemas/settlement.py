"""结算单输出模型。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    supplier_id: int
    amount: Decimal
    commission_rate: Decimal
    commission: Decimal
    payable_to_supplier: Decimal
    status: str
    remark: str | None = None
    settled_at: datetime | None = None
    created_at: datetime
