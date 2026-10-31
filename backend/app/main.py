"""FastAPI 应用入口。"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保模型注册到 Base.metadata
from .config import settings
from .routers import audit, auth, devices, iot, match, orders, resources, reviews, stats, users, ws
from .ws_broadcast import hub

# 应用日志级别（uvicorn 只配了 uvicorn.* ，app.* 需单独开）
logging.getLogger("app").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 表结构由 Alembic 管理（部署时执行 `alembic upgrade head`），应用启动不再自动建表
    # 注入主事件循环，供跨线程的 hub.publish 投递任务
    hub.set_loop(asyncio.get_running_loop())
    # 启动 MQTT 订阅后台线程（连接 drone_emqx，已 healthy）
    from . import mqtt_client
    mqtt_client.start_mqtt(settings.mqtt_host, settings.mqtt_port)
    # 设备离线检测常驻协程
    from .tasks import device_watchdog
    watchdog = asyncio.create_task(device_watchdog())
    try:
        yield
    finally:
        watchdog.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resources.router)
app.include_router(orders.router)
app.include_router(match.router)
app.include_router(iot.router)
app.include_router(devices.router)
app.include_router(reviews.router)
app.include_router(stats.router)
app.include_router(audit.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
