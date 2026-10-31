"""用户相关校验模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 允许的角色
ROLES = {"supplier", "demander", "admin"}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = "demander"  # supplier / demander / admin
    company_name: str | None = None
    contact: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """至少 8 位，且同时包含字母和数字。"""
        if not any(c.isalpha() for c in v):
            raise ValueError("密码必须包含字母")
        if not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含数字")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"角色必须是 {sorted(ROLES)} 之一")
        return v


class UserUpdate(BaseModel):
    """当前用户自助修改资料。"""
    company_name: str | None = None
    contact: str | None = None


class PasswordChange(BaseModel):
    """修改密码：需提供旧密码，新密码满足强度要求。"""
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("新密码必须包含字母")
        if not any(c.isdigit() for c in v):
            raise ValueError("新密码必须包含数字")
        return v


class UserAdminUpdate(BaseModel):
    """管理员修改用户：角色、启用状态、企业资料。"""
    role: str | None = None
    is_active: bool | None = None
    company_name: str | None = None
    contact: str | None = None

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ROLES:
            raise ValueError(f"角色必须是 {sorted(ROLES)} 之一")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    company_name: str | None = None
    contact: str | None = None
    credit_score: int
    is_active: bool = True
    created_at: datetime
