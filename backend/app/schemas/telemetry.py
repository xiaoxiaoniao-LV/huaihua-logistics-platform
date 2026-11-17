"""遥测上报与点位字典的校验模型。"""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

POINT_KEY_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"
_POINT_KEY_RE = re.compile(POINT_KEY_PATTERN)
_QUALITIES = {"good", "stale", "bad"}


class TelemetryEnvelope(BaseModel):
    """单台设备一次上报：一台设备 + 多个点位 + 统一时间戳。"""

    device_code: str = Field(min_length=1, max_length=50)
    ts: datetime | None = Field(default=None, description="设备采集时间，ISO8601；缺省取服务端时间")
    seq: int | None = Field(default=None, ge=0, description="设备本地递增序号，用于补传排序")
    quality: str = Field(default="good", description="good / stale / bad")
    firmware_version: str | None = Field(default=None, max_length=20)
    points: dict[str, float | int | bool | str] = Field(
        description="点位键 -> 取值，如 {\"temp_in\": -18.5, \"door\": false}"
    )

    @field_validator("quality")
    @classmethod
    def _check_quality(cls, value: str) -> str:
        if value not in _QUALITIES:
            raise ValueError(f"quality 必须是 {sorted(_QUALITIES)} 之一")
        return value

    @field_validator("points")
    @classmethod
    def _check_points(cls, value: dict) -> dict:
        if not value:
            raise ValueError("points 不能为空")
        if len(value) > 50:
            raise ValueError("单条上报最多 50 个点位")
        for key in value:
            if not _POINT_KEY_RE.match(key):
                raise ValueError(f"非法点位键：{key}（小写字母开头，仅含小写字母/数字/下划线）")
        return value


class TelemetryBatch(BaseModel):
    """批量上报体，支持设备断网恢复后一次性补传。"""

    items: list[TelemetryEnvelope] = Field(min_length=1, max_length=200)


class DevicePointCreate(BaseModel):
    """运维手工注册自定义点位（内置字典之外的传感器）。"""

    point_key: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    unit: str = Field(default="", max_length=20)
    data_type: str = Field(default="number")
    precision: int = Field(default=1, ge=0, le=6)
    min_value: float | None = None
    max_value: float | None = None
    writable: bool = False
    sort: int = Field(default=99, ge=0, le=999)

    @field_validator("point_key")
    @classmethod
    def _check_point_key(cls, value: str) -> str:
        if not _POINT_KEY_RE.match(value):
            raise ValueError("点位键需以小写字母开头，仅含小写字母/数字/下划线")
        return value

    @field_validator("data_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in {"number", "bool", "text"}:
            raise ValueError("data_type 必须是 number / bool / text 之一")
        return value

    @field_validator("max_value")
    @classmethod
    def _check_range(cls, value: float | None, info):
        low = info.data.get("min_value")
        if value is not None and low is not None and value <= low:
            raise ValueError("max_value 必须大于 min_value")
        return value
