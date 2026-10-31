"""资源：发布、查询、更新、下架。带 Redis Cache-Aside 缓存层。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Resource, User
from ..schemas.resource import ResourceCreate, ResourceOut, ResourceReview, ResourceUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resources", tags=["resources"])

# 缓存 TTL（秒）——资源列表变动频繁，用短 TTL
_TTL_LIST = 15
_TTL_DETAIL = 10


def _rc():
    """懒加载 redis_client，避免循环 import。"""
    try:
        from .. import redis_client
        return redis_client
    except Exception as e:
        logger.warning("[resources] redis_client 不可用: %s", e)
        return None


def _invalidate_all_resources():
    """资源写操作后，清掉所有 resources:* 缓存项（SCAN 迭代，不阻塞 Redis）。"""
    rc = _rc()
    if rc is None:
        return
    n = rc.delete_by_pattern("resources:*")
    if n:
        logger.info("[resources] 已失效 %d 条缓存项", n)


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    data: ResourceCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resource = Resource(user_id=current.id, **data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    _invalidate_all_resources()
    return resource


@router.get("", response_model=list[ResourceOut])
def list_resources(
    response: Response,
    resource_type: str | None = Query(None, alias="type"),
    status_filter: str | None = Query(None, alias="status"),
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # --- Cache-Aside ---
    cache_key = (
        f"resources:list:{resource_type or '__'}:{status_filter or '__'}:"
        f"{keyword or '__'}:{page}:{page_size}"
    )
    rc = _rc()
    if rc is not None:
        cached = rc.get_json(cache_key)
        if isinstance(cached, dict) and "items" in cached:
            logger.debug("[resources] cache hit %s", cache_key)
            response.headers["X-Total-Count"] = str(cached.get("total", 0))
            return cached["items"]

    query = db.query(Resource)
    if resource_type:
        query = query.filter(Resource.type == resource_type)
    if status_filter:
        query = query.filter(Resource.status == status_filter)
    if keyword:
        query = query.filter(Resource.name.contains(keyword))

    total = query.count()
    rows = (
        query.order_by(Resource.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    out = [ResourceOut.model_validate(r).model_dump(mode="json") for r in rows]

    response.headers["X-Total-Count"] = str(total)
    if rc is not None:
        rc.set_json(cache_key, {"total": total, "items": out}, ttl=_TTL_LIST)
    return out


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    cache_key = f"resources:{resource_id}"
    rc = _rc()
    if rc is not None:
        cached = rc.get_json(cache_key)
        if cached is not None:
            return cached

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    out = ResourceOut.model_validate(resource).model_dump(mode="json")
    if rc is not None:
        rc.set_json(cache_key, out, ttl=_TTL_DETAIL)
    return out


@router.put("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if resource.user_id != current.id and current.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作他人资源")

    payload = data.model_dump(exclude_unset=True)
    # 待审核资源必须由管理员审核通过后才能上架，防止绕过审核
    if (
        payload.get("status") == "available"
        and resource.status == "pending"
        and current.role != "admin"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "资源待审核，需管理员审核通过后才能上架")

    for key, value in payload.items():
        setattr(resource, key, value)
    db.commit()
    db.refresh(resource)

    # 写后删缓存
    rc = _rc()
    if rc is not None:
        rc.delete(f"resources:{resource_id}")
        _invalidate_all_resources()

    return resource


@router.post("/{resource_id}/review", response_model=ResourceOut)
def review_resource(
    resource_id: int,
    data: ResourceReview,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员审核待审核资源：通过→上架，驳回→下架。"""
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if resource.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "只有待审核资源可以审核")

    resource.status = "available" if data.approve else "offline"
    db.commit()
    db.refresh(resource)
    _invalidate_all_resources()
    log_audit(
        db, admin, "resource_review",
        target_type="resource", target_id=resource.id,
        detail=f"审核{'通过' if data.approve else '驳回'}（{data.reason or '-'}）",
        ip=request.client.host if request.client else None,
    )

    logger.info(
        "[resources] 审核资源 %s -> %s（审核人 %s，理由：%s）",
        resource.id, resource.status, admin.username, data.reason or "-",
    )
    try:
        from .. import ws_broadcast
        ws_broadcast.publish({
            "type": "resource_updated",
            "resource_id": resource.id,
            "status": resource.status,
        })
    except Exception:
        logger.warning("[resources] 审核后 WS 推送失败", exc_info=True)

    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if resource.user_id != current.id and current.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作他人资源")

    db.delete(resource)
    db.commit()
    _invalidate_all_resources()
