"""AI 撮合推荐，带 Redis 缓存（按登录用户区分个性化结果）。"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_admin_user, get_optional_user
from ..models import User
from ..schemas.match import MatchWeightsIn, MatchWeightsOut
from ..services.matching import (
    DEFAULT_WEIGHTS, DIMENSION_LABELS, load_weights, recommend, save_weights,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/match", tags=["match"])

# 撮合结果随价格变动，TTL 30s
_TTL = 30


def _rc():
    try:
        from .. import redis_client
        return redis_client
    except Exception as e:
        logger.warning("[match] redis_client 不可用: %s", e)
        return None


@router.get("/recommend")
def recommend_resources(
    resource_type: str | None = Query(None, alias="type"),
    max_price: float | None = None,
    top_n: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current: User | None = Depends(get_optional_user),
):
    uid = current.id if current else None
    cache_key = (
        f"match:recommend:{resource_type or '__'}:"
        f"{max_price if max_price is not None else '__'}:{top_n}:{uid or '__'}"
    )
    rc = _rc()
    if rc is not None:
        cached = rc.get_json(cache_key)
        if cached is not None:
            logger.debug("[match] cache hit %s", cache_key)
            return cached

    results = recommend(
        db,
        resource_type=resource_type,
        max_price=max_price,
        top_n=top_n,
        user_id=uid,
    )
    payload = {"count": len(results), "results": results}

    if rc is not None:
        rc.set_json(cache_key, payload, ttl=_TTL)
    return payload


@router.get("/weights", response_model=MatchWeightsOut)
def get_weights(
    db: Session = Depends(get_db),
    current: User = Depends(get_admin_user),
):
    """当前撮合权重与维度中文名（管理员可读，便于前端做权重面板）。"""
    return MatchWeightsOut(
        weights=load_weights(db),
        labels=DIMENSION_LABELS,
        defaults=DEFAULT_WEIGHTS,
    )


@router.put("/weights", response_model=MatchWeightsOut)
def update_weights(
    payload: MatchWeightsIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_admin_user),
):
    """调整撮合权重；改完立即清空推荐缓存，下一次请求按新权重排序。"""
    weights = save_weights(db, payload.weights, user_id=current.id)
    rc = _rc()
    if rc is not None:
        rc.delete_by_pattern("match:recommend:*")
    return MatchWeightsOut(
        weights=weights,
        labels=DIMENSION_LABELS,
        defaults=DEFAULT_WEIGHTS,
    )
