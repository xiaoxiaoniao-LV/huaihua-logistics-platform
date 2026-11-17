"""幂等键：写操作携带 Idempotency-Key，重复请求返回首次结果。

用法（路由内）：
    cached = idempotency.begin(db, "order:create", key, current.id)
    if cached is not None:
        return JSONResponse(content=cached["body"], status_code=cached["code"])
    try:
        ... 业务 ...
        idempotency.remember(db, "order:create", key, 201, body)
    except Exception:
        idempotency.release(db, "order:create", key)
        raise
"""
import logging

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import IdempotencyKey

logger = logging.getLogger(__name__)


def begin(db: Session, scope: str, key: str, user_id: int | None) -> dict | None:
    """登记幂等键。返回首次请求的缓存结果；处理中则 409；首次则返回 None。"""
    rec = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.scope == scope, IdempotencyKey.idem_key == key)
        .first()
    )
    if rec is not None:
        if rec.status == "done":
            return {"code": rec.response_code or 200, "body": rec.response_body}
        raise HTTPException(409, "相同请求正在处理中，请稍后重试")

    db.add(
        IdempotencyKey(
            scope=scope, idem_key=key, user_id=user_id, status="processing"
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # 并发请求抢先插入
        db.rollback()
        raise HTTPException(409, "相同请求正在处理中，请稍后重试")
    return None


def remember(
    db: Session, scope: str, key: str, code: int, body: dict | None
) -> None:
    """记录首次请求结果，后续重复请求直接回放。"""
    rec = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.scope == scope, IdempotencyKey.idem_key == key)
        .first()
    )
    if rec is None:
        return
    rec.status = "done"
    rec.response_code = code
    rec.response_body = body
    db.commit()


def release(db: Session, scope: str, key: str) -> None:
    """业务失败时释放占位，允许客户端用同一 key 重试。"""
    db.rollback()
    db.query(IdempotencyKey).filter(
        IdempotencyKey.scope == scope,
        IdempotencyKey.idem_key == key,
        IdempotencyKey.status == "processing",
    ).delete()
    db.commit()
