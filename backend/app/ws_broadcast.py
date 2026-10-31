"""WebSocket 广播中心：全局单例，业务模块 publish()，WS 连接通过 /ws/realtime 订阅。

设计要点：
- publish() 可被任意线程调用（MQTT 后台线程、HTTP 路由线程），
  内部根据当前线程是否为主 loop 线程，选择 ensure_future 或 run_coroutine_threadsafe。
- subscribers 的增删用 threading.Lock 保护（跨线程安全）。
- 主 loop 引用 + 主线程 ID 在 FastAPI startup 时注入（set_loop）。
"""
import asyncio
import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class BroadcastHub:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_thread_id: int | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """FastAPI startup 时注入主事件循环 + 主线程 ID。"""
        self._loop = loop
        self._main_thread_id = threading.get_ident()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            self._subscribers.discard(q)

    async def _publish_async(self, event: dict[str, Any]):
        try:
            payload = json.dumps(event, ensure_ascii=False)
            dead: list[asyncio.Queue] = []
            with self._lock:
                subs = list(self._subscribers)
            for q in subs:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(q)
            if dead:
                with self._lock:
                    for q in dead:
                        self._subscribers.discard(q)
        except Exception:
            logger.exception("[hub] _publish_async 失败")

    def publish(self, event: dict[str, Any]):
        """同步入口：任何模块/线程都能调用。"""
        if self._loop is None:
            return
        if threading.get_ident() == self._main_thread_id:
            # 主 loop 线程：直接 ensure_future
            asyncio.ensure_future(self._publish_async(event))
        else:
            # 其他线程（MQTT / HTTP 线程池）：跨线程投递
            fut = asyncio.run_coroutine_threadsafe(self._publish_async(event), self._loop)
            fut.add_done_callback(lambda f: f.exception() and logger.warning("[hub] 投递异常: %s", f.exception()))


hub = BroadcastHub()

# 模块级便捷入口：业务代码可直接 `ws_broadcast.publish(event)`，无需 import hub
publish = hub.publish
