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
    firmware_version: str = "1.0.0"
    # 以下为聚合字段，由路由层填充
    resource_name: str | None = None
    last_seen: datetime | None = None
    last_temperature: float | None = None
    last_humidity: float | None = None


class OTARequest(BaseModel):
    target_version: str = Field(min_length=1, max_length=20)
    device_ids: list[int] | None = None  # 为空表示全部设备


class OTAReport(BaseModel):
    device_code: str = Field(min_length=1, max_length=50)
    target_version: str = Field(min_length=1, max_length=20)
    success: bool = True
    message: str | None = None


class OTATaskOut(BaseModel):
    id: int
    device_id: int
    device_code: str | None = None
    from_version: str | None = None
    target_version: str
    status: str
    message: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class ImportErrorItem(BaseModel):
    row: int
    device_code: str | None = None
    reason: str


class ImportResult(BaseModel):
    created: int
    skipped: int
    failed: int
    errors: list[ImportErrorItem] = Field(default_factory=list)


class DeviceTelemetryPoint(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    longitude: float | None = None
    latitude: float | None = None
    recorded_at: datetime
