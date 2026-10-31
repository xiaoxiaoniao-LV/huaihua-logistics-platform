"""后台任务：设备离线检测。

逻辑抽成纯函数 `mark_offline_devices`，便于单测；`device_watchdog` 只是定时调用它。
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
        last_seen = (
            db.query(func.max(IoTData.recorded_at))
            .filter(IoTData.device_id == dev.id)
            .scalar()
        )
        if last_seen is None or last_seen < cutoff:
            dev.status = "offline"
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
