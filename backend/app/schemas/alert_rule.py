"""告警阈值规则校验模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlertRuleUpdate(BaseModel):
    """更新规则；缺省字段表示沿用已有值。"""

    temp_min: float | None = Field(None, description="温度下限（℃），低于该值告警")
    temp_max: float | None = Field(None, description="温度上限（℃），高于该值告警")
    humidity_max: float | None = Field(None, description="湿度上限（%RH）")
    enabled: bool | None = None

    @model_validator(mode="after")
    def _check_range(self):
        lo = self.temp_min
        hi = self.temp_max
        if lo is not None and hi is not None and lo >= hi:
            raise ValueError("温度下限必须小于上限")
        return self


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    temp_min: float
    temp_max: float
    humidity_max: float
    enabled: bool
    updated_at: datetime | None = None
    # 聚合字段，由路由层填充
    resource_name: str | None = None
