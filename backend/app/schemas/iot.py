"""IoT 数据相关校验模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IoTDataReport(BaseModel):
    device_code: str
    temperature: float | None = None
    humidity: float | None = None
    longitude: float | None = None
    latitude: float | None = None


class IoTDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    temperature: float | None = None
    humidity: float | None = None
    longitude: float | None = None
    latitude: float | None = None
    recorded_at: datetime
