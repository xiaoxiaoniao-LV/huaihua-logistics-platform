"""认证相关校验模型。"""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


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
