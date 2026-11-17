"""认证相关校验模型。"""
from pydantic import BaseModel, field_validator

# 允许的调用方终端
CLIENTS = {"admin", "supplier", "app", "screen"}


class LoginRequest(BaseModel):
    username: str
    password: str
    # 登录来源终端：决定令牌中的 client 声明，后端据此做域鉴权
    client: str = "admin"

    @field_validator("client")
    @classmethod
    def client_valid(cls, v: str) -> str:
        if v not in CLIENTS:
            raise ValueError(f"client 必须是 {sorted(CLIENTS)} 之一")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPair(BaseModel):
    """登录成功返回：access token + refresh token，用于无感续期。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
