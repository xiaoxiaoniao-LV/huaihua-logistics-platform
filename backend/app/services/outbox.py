"""事务外盒（Outbox）：业务写入与事件落库同事务，后台 worker 异步投递。"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import OutboxEvent

logger = logging.getLogger(__name__)


def emit(
    db: Session,
    aggregate_type: str,
    aggregate_id: int | None,
    event_type: str,
    payload: dict | None = None,
) -> OutboxEvent:
    """在当前事务内登记事件，不自行 commit。"""
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload or {},
        status="pending",
    )
    db.add(event)
    return event


def dispatch_pending(db: Session, limit: int = 100) -> int:
    """投递待发送事件到 WebSocket，返回成功条数。"""
    from ..ws_broadcast import publish

    events = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.id)
        .limit(limit)
        .all()
    )
    sent = 0
    for e in events:
        try:
            publish({"type": e.event_type, **(e.payload or {})})
            e.status = "published"
            e.published_at = datetime.now()
            sent += 1
        except Exception as exc:  # 投递失败保留 pending，下轮重试
            e.retry_count = (e.retry_count or 0) + 1
            e.last_error = str(exc)[:255]
            if e.retry_count >= 5:
                e.status = "failed"
            logger.warning("[outbox] 事件 %s 投递失败：%s", e.id, exc)
    if events:
        db.commit()
    return sent
