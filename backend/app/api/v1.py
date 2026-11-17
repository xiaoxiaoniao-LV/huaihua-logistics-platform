"""API v1 聚合入口：所有域路由在此挂载，main.py 只依赖这一处。"""
from fastapi import APIRouter

from ..routers import (
    audit,
    auth,
    devices,
    iot,
    match,
    orders,
    payments,
    resources,
    reviews,
    settlements,
    stats,
    twin,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resources.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(settlements.router)
api_router.include_router(match.router)
api_router.include_router(iot.router)
api_router.include_router(devices.router)
api_router.include_router(twin.router)
api_router.include_router(reviews.router)
api_router.include_router(stats.router)
api_router.include_router(audit.router)
