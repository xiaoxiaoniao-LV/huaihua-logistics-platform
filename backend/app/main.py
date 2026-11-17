"""FastAPI 应用入口。"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保模型注册到 Base.metadata
from .api.v1 import api_router
from .config import settings
from .routers import ws
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
    # 设备离线检测 / outbox 投递 / 订单超时关闭 三个常驻协程
    from .tasks import device_watchdog, order_timeout_watchdog, outbox_worker
    watchdog = asyncio.create_task(device_watchdog())
    outbox = asyncio.create_task(outbox_worker())
    order_timeout = asyncio.create_task(order_timeout_watchdog())
    try:
        yield
    finally:
        for task in (watchdog, outbox, order_timeout):
            task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    from . import mqtt_client, redis_client

    return {
        "status": "ok",
        "app": settings.app_name,
        # 供前端状态芯片显示真实依赖状态，避免硬编码绿灯
        "redis": redis_client.ping(),
        "mqtt": mqtt_client.is_connected(),
        "iot_mode": "lab-prototype",  # 实验室真实传感器组网（ESP32×3）+ 港区规模虚拟
    }
