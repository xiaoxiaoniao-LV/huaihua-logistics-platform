"""认证：注册、登录、修改密码、刷新令牌。

登录失败限流：同一用户名连续失败超过阈值（默认 5 次）后锁定一段时间（默认 15 分钟），
防止暴力破解。限流依赖 Redis，Redis 不可用时自动降级为不限流（不阻断正常登录）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import redis_client, security
from ..audit import log_audit
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas.token import LoginRequest, RefreshRequest, TokenPair
from ..schemas.user import PasswordChange, UserCreate, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOGIN_FAIL_KEY = "login:fail:{username}"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _login_locked(username: str) -> bool:
    """判断该用户名当前是否处于锁定状态。Redis 不可用时返回 False（不限流）。"""
    count = redis_client.get_int(_LOGIN_FAIL_KEY.format(username=username))
    return count is not None and count >= settings.login_max_attempts


def _record_login_failure(username: str) -> None:
    redis_client.incr_ttl(_LOGIN_FAIL_KEY.format(username=username), settings.login_lock_seconds)


def _clear_login_failure(username: str) -> None:
    redis_client.delete(_LOGIN_FAIL_KEY.format(username=username))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")

    # 管理员角色不开放自助注册：仅当系统内还没有任何管理员时允许首个管理员引导创建
    if data.role == "admin":
        has_admin = db.query(User).filter(User.role == "admin").first() is not None
        if has_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员账号需由现有管理员分配")

    user = User(
        username=data.username,
        password_hash=security.hash_password(data.password),
        role=data.role,
        company_name=data.company_name,
        contact=data.contact,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    if _login_locked(data.username):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"登录失败次数过多，请 {settings.login_lock_seconds // 60} 分钟后再试",
        )

    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not security.verify_password(data.password, user.password_hash):
        _record_login_failure(data.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")

    _clear_login_failure(data.username)
    log_audit(db, user, "login", detail="登录成功", ip=_client_ip(request))

    access = security.create_access_token(str(user.id), {"role": user.role})
    refresh = security.create_refresh_token(str(user.id), {"role": user.role})
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """用 refresh token 换取新的 access + refresh token（无感续期）。"""
    try:
        payload = security.decode_access_token(data.refresh_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "刷新令牌无效或已过期")

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌类型错误")

    user_id = payload.get("sub")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已被禁用")

    access = security.create_access_token(str(user.id), {"role": user.role})
    refresh = security.create_refresh_token(str(user.id), {"role": user.role})
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/change-password", response_model=UserOut)
def change_password(
    data: PasswordChange,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not security.verify_password(data.old_password, current.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "旧密码不正确")
    if data.new_password == data.old_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与旧密码相同")

    current.password_hash = security.hash_password(data.new_password)
    db.commit()
    db.refresh(current)
    log_audit(db, current, "change_password", detail="修改密码")
    return current
