"""WebSocket 路由：/ws/realtime —— 前端订阅所有实时事件。

鉴权策略：大屏是只读公共看板，允许匿名订阅；
若携带 `?token=`，则必须有效且账号未被禁用，否则拒绝连接。
"""
import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .. import security
from ..database import SessionLocal
from ..models import User
from ..ws_broadcast import hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


def _check_token(token: str) -> bool:
    try:
        payload = security.decode_access_token(token)
        uid = int(payload.get("sub"))
    except Exception:
        return False
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        return user is not None and bool(user.is_active)
    finally:
        db.close()


@router.websocket("/ws/realtime")
async def realtime(ws: WebSocket, token: str | None = Query(None)):
    if token and not _check_token(token):
        logger.warning("[ws] 令牌无效，拒绝订阅")
        await ws.close(code=1008)
        return

    await ws.accept()
    q = await hub.subscribe()
    # 欢迎包
    await ws.send_json({"type": "hello", "msg": "connected", "ts": asyncio.get_event_loop().time()})
    try:
        while True:
            msg = await q.get()
            await ws.send_text(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("[ws] 连接异常: %s", e)
    finally:
        await hub.unsubscribe(q)
