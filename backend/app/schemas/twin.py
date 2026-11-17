"""数字孪生：节点与绑定的校验模型。"""
import re

from pydantic import BaseModel, Field, field_validator

_NODE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
NODE_TYPES = {"site", "building", "floor", "room", "zone", "rack", "device"}
BINDING_TYPES = {"telemetry", "status", "anchor"}


class TwinNodeIn(BaseModel):
    node_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    node_type: str = Field(default="room")
    parent_id: int | None = None
    space_id: int | None = None
    model_ref: str | None = Field(default=None, max_length=200)
    transform: dict | None = None
    sort: int = Field(default=0, ge=0, le=9999)

    @field_validator("node_key")
    @classmethod
    def _check_key(cls, value: str) -> str:
        if not _NODE_KEY_RE.match(value):
            raise ValueError("node_key 仅允许字母/数字/-_.:，且以字母或数字开头")
        return value

    @field_validator("node_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in NODE_TYPES:
            raise ValueError(f"node_type 必须是 {sorted(NODE_TYPES)} 之一")
        return value


class TwinBindingIn(BaseModel):
    node_key: str = Field(min_length=1, max_length=80)
    device_code: str = Field(min_length=1, max_length=50)
    point_key: str = Field(min_length=1, max_length=50)
    binding_type: str = Field(default="telemetry")

    @field_validator("binding_type")
    @classmethod
    def _check_binding(cls, value: str) -> str:
        if value not in BINDING_TYPES:
            raise ValueError(f"binding_type 必须是 {sorted(BINDING_TYPES)} 之一")
        return value
