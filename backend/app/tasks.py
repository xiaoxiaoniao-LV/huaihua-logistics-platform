"""后台任务：设备离线检测、outbox 投递、订单超时关闭。

逻辑抽成纯函数便于单测；`*_watchdog` / `outbox_worker` 只是定时调用。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import IoTData, IoTDevice

logger = logging.getLogger(__name__)

WATCHDOG_INTERVAL_SECONDS = 30
OUTBOX_INTERVAL_SECONDS = 1
ORDER_TIMEOUT_INTERVAL_SECONDS = 300
ORDER_TIMEOUT_HOURS = 48


def mark_offline_devices(
    db: Session,
    now: datetime | None = None,
    offline_seconds: int | None = None,
) -> list[str]:
    """把超过阈值未上报的在线设备标记为离线，返回被标记的设备编码。"""
    now = now or datetime.now()
    seconds = offline_seconds if offline_seconds is not None else settings.device_offline_seconds
    cutoff = now - timedelta(seconds=seconds)

    devices = db.query(IoTDevice).filter(IoTDevice.status == "online").all()
    changed: list[str] = []
    for dev in devices:
        data_seen = (
            db.query(func.max(IoTData.recorded_at))
            .filter(IoTData.device_id == dev.id)
            .scalar()
        )
        # 窄表遥测写入 last_seen_at，旧固定列上报写 IoTData，取两者较新者
        candidates = [ts for ts in (dev.last_seen_at, data_seen) if ts is not None]
        last_seen = max(candidates) if candidates else None
        if last_seen is None or last_seen < cutoff:
            dev.status = "offline"
            dev.quality = "stale"
            changed.append(dev.device_code)

    if changed:
        db.commit()
        logger.info("[watchdog] 设备离线：%s", ", ".join(changed))
    return changed


async def device_watchdog() -> None:
    """常驻协程：定期执行离线检测。"""
    from .database import SessionLocal

    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            mark_offline_devices(db)
        except Exception:
            logger.warning("[watchdog] 离线检测失败", exc_info=True)
        finally:
            db.close()


async def outbox_worker() -> None:
    """常驻协程：把 outbox 中待投递事件推送到 WebSocket。"""
    from .database import SessionLocal
    from .services.outbox import dispatch_pending

    while True:
        await asyncio.sleep(OUTBOX_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            dispatch_pending(db)
        except Exception:
            logger.warning("[outbox] 投递循环失败", exc_info=True)
        finally:
            db.close()


def expire_orders_task(db: Session, hours: int = ORDER_TIMEOUT_HOURS) -> list[int]:
    """纯函数：关闭超时未确认订单（便于单测与手动触发）。"""
    from .services.order_state import expire_stale_orders

    return expire_stale_orders(db, hours=hours)


async def order_timeout_watchdog() -> None:
    """常驻协程：48h 未确认订单自动关闭并释放资源。"""
    from .database import SessionLocal

    while True:
        await asyncio.sleep(ORDER_TIMEOUT_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            expire_orders_task(db)
        except Exception:
            logger.warning("[order-timeout] 超时关闭失败", exc_info=True)
        finally:
            db.close()
