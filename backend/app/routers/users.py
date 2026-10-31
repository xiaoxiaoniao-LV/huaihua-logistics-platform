"""用户：查询 / 更新当前用户资料；管理员用户管理。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas.user import UserAdminUpdate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(current: User = Depends(get_current_user)):
    return current


@router.put("/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(current, key, value)
    db.commit()
    db.refresh(current)
    return current


@router.get("", response_model=list[UserOut])
def list_users(
    keyword: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if keyword:
        q = q.filter(User.username.contains(keyword))
    if role:
        q = q.filter(User.role == role)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    return q.order_by(User.id).limit(limit).all()


@router.put("/{user_id}", response_model=UserOut)
def admin_update_user(
    user_id: int,
    data: UserAdminUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")

    payload = data.model_dump(exclude_unset=True)
    # 不允许管理员禁用/降级自己，避免把自己锁死
    if user.id == admin.id:
        if payload.get("is_active") is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能禁用自己的账号")
        if payload.get("role") and payload["role"] != "admin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能降级自己的管理员角色")

    for key, value in payload.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)

    changes = []
    if "role" in payload:
        changes.append(f"角色→{payload['role']}")
    if "is_active" in payload:
        changes.append("禁用" if payload["is_active"] is False else "启用")
    log_audit(
        db, admin, "user_update",
        target_type="user", target_id=user.id,
        detail="，".join(changes) or "资料更新",
        ip=request.client.host if request.client else None,
    )
    return user
