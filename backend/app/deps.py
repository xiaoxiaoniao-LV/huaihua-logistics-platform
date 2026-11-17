"""鉴权依赖。

四个终端各自一套守卫，权限由后端判定，不依赖前端路由隔离：

- get_admin_user    运营后台（client=admin）
- get_supplier_user 供给工作台（client=supplier）
- get_app_user      需求端（client=app）
- get_screen_viewer 指挥大屏（client=screen，允许匿名只读）

管理员账号可跨端操作，便于统一运维。
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import security
from .database import get_db
from .models import User

bearer_scheme = HTTPBearer(auto_error=False)


def _authenticate(
    credentials: HTTPAuthorizationCredentials | None, db: Session
) -> tuple[User, dict]:
    """解析令牌并加载用户，失败抛 401/403。"""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    try:
        payload = security.decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌类型错误")

    user_id = payload.get("sub")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")
    return user, payload


def _require_client(payload: dict, allowed: set[str]) -> None:
    if payload.get("client", "admin") not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该终端无权访问此接口")


def _require_role(user: User, allowed: set[str]) -> None:
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "当前角色无权访问此接口")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """任意已登录用户。"""
    user, _ = _authenticate(credentials, db)
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录：未带令牌或令牌无效时返回 None，不中断请求。"""
    if credentials is None:
        return None
    try:
        user, _ = _authenticate(credentials, db)
    except HTTPException:
        return None
    return user


def get_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """运营后台：client=admin 且角色为 admin。"""
    user, payload = _authenticate(credentials, db)
    _require_client(payload, {"admin"})
    _require_role(user, {"admin"})
    return user


def get_supplier_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """供给工作台：client=supplier，角色为 supplier 或 admin。"""
    user, payload = _authenticate(credentials, db)
    _require_client(payload, {"supplier", "admin"})
    _require_role(user, {"supplier", "admin"})
    return user


def get_app_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """需求端：client=app，角色为 demander 或 admin。"""
    user, payload = _authenticate(credentials, db)
    _require_client(payload, {"app", "admin"})
    _require_role(user, {"demander", "admin"})
    return user


def get_screen_viewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """指挥大屏：只读看板，允许匿名；带令牌时必须是 screen 或 admin。"""
    if credentials is None:
        return None
    user, payload = _authenticate(credentials, db)
    _require_client(payload, {"screen", "admin"})
    return user


def require_admin(current: User = Depends(get_current_user)) -> User:
    """兼容旧调用：仅管理员可访问（不校验 client）。"""
    if current.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return current
