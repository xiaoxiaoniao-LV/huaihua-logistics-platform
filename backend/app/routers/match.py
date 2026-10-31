"""AI 撮合推荐，带 Redis 缓存。"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.matching import recommend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/match", tags=["match"])

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
):
    cache_key = f"match:recommend:{resource_type or '__'}:{max_price if max_price is not None else '__'}:{top_n}"
    rc = _rc()
    if rc is not None:
        cached = rc.get_json(cache_key)
        if cached is not None:
            logger.debug("[match] cache hit %s", cache_key)
            return cached

    results = recommend(db, resource_type=resource_type, max_price=max_price, top_n=top_n)
    payload = {"count": len(results), "results": results}

    if rc is not None:
        rc.set_json(cache_key, payload, ttl=_TTL)
    return payload
