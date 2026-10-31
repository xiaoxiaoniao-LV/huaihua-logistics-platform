"""设备管理校验模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    device_code: str = Field(min_length=1, max_length=50)
    device_type: str | None = None
    resource_id: int = 0


class DeviceUpdate(BaseModel):
    resource_id: int | None = None
    device_type: str | None = None
    status: str | None = None  # online / offline


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_code: str
    device_type: str | None = None
    resource_id: int
    status: str
    # 以下为聚合字段，由路由层填充
    resource_name: str | None = None
    last_seen: datetime | None = None
    last_temperature: float | None = None
    last_humidity: float | None = None


class DeviceTelemetryPoint(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    longitude: float | None = None
    latitude: float | None = None
    recorded_at: datetime
