"""Redis 连接池单例 + 缓存辅助工具。

复用 drone_redis（本机 6379），用 ConnectionPool 全局共享。
所有缓存 key 加上 `hlg:` 前缀（怀化陆港）避免和其他项目冲突。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
import redis as sync_redis

from .config import settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "hlg:"  # huaihua-logistics-platform 缩写，避免跨项目污染

# --- 连接池（全局单例，懒加载） ---
_sync_pool: sync_redis.ConnectionPool | None = None
_async_pool: aioredis.ConnectionPool | None = None


def get_sync_pool() -> sync_redis.ConnectionPool:
    """同步连接池（DB 路由里用，线程安全）。"""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = sync_redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=32,
            decode_responses=True,
        )
        logger.info("[redis] 同步连接池已初始化，url=%s", settings.redis_url)
    return _sync_pool


def get_sync() -> sync_redis.Redis:
    return sync_redis.Redis(connection_pool=get_sync_pool())


async def get_async_pool() -> aioredis.ConnectionPool:
    """异步连接池（WebSocket 广播等 async 场景）。"""
    global _async_pool
    if _async_pool is None:
        _async_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=32,
            decode_responses=True,
        )
        logger.info("[redis] 异步连接池已初始化，url=%s", settings.redis_url)
    return _async_pool


async def get_async() -> aioredis.Redis:
    pool = await get_async_pool()
    return aioredis.Redis(connection_pool=pool)


# --- 缓存工具函数 ---
def k(key: str) -> str:
    """统一加前缀。"""
    return f"{KEY_PREFIX}{key}"


def set_json(key: str, value: Any, ttl: int = 60) -> None:
    """写 JSON 缓存，ttl 秒。"""
    try:
        get_sync().set(k(key), json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.warning("[redis] set_json 失败 key=%s: %s", key, e)


def get_json(key: str) -> Any:
    """读 JSON 缓存，返回 None 表示 miss。"""
    try:
        raw = get_sync().get(k(key))
        return json.loads(raw) if raw is not None else None
    except Exception as e:
        logger.warning("[redis] get_json 失败 key=%s: %s", key, e)
        return None


def delete(key: str) -> None:
    try:
        get_sync().delete(k(key))
    except Exception as e:
        logger.warning("[redis] delete 失败 key=%s: %s", key, e)


def delete_by_pattern(pattern: str, batch_size: int = 100) -> int:
    """按模式删除 key，用 SCAN 迭代避免 KEYS 阻塞 Redis。返回删除数量。

    KEYS 是 O(N) 且会阻塞单线程 Redis；SCAN 每次只扫一小批，可增量迭代。
    """
    try:
        r = get_sync()
        full_pattern = k(pattern)
        deleted = 0
        batch: list[str] = []
        for key in r.scan_iter(match=full_pattern, count=batch_size):
            batch.append(key)
            if len(batch) >= batch_size:
                deleted += r.delete(*batch)
                batch.clear()
        if batch:
            deleted += r.delete(*batch)
        return deleted
    except Exception as e:
        logger.warning("[redis] delete_by_pattern 失败 pattern=%s: %s", pattern, e)
        return 0


def ping() -> bool:
    """健康检查用。"""
    try:
        return bool(get_sync().ping())
    except Exception:
        return False


def incr_ttl(key: str, ttl: int = 60) -> int | None:
    """对 key 自增并设置过期时间，返回自增后的值；Redis 不可用时返回 None。

    用于登录失败限流等需要原子计数的场景。首次调用会把 key 置 1 并设 TTL。
    """
    try:
        r = get_sync()
        full = k(key)
        pipe = r.pipeline()
        pipe.incr(full)
        pipe.expire(full, ttl)
        val = pipe.execute()[0]
        return int(val)
    except Exception as e:
        logger.warning("[redis] incr_ttl 失败 key=%s: %s", key, e)
        return None


def get_int(key: str) -> int | None:
    """读取整数值，key 不存在返回 0，Redis 不可用返回 None。"""
    try:
        raw = get_sync().get(k(key))
        return int(raw) if raw is not None else 0
    except Exception as e:
        logger.warning("[redis] get_int 失败 key=%s: %s", key, e)
        return None


# --- 缓存 key 约定 ---
# resources:list?type=xxx&status=xxx&keyword=xxx          （资源列表查询结果）
# resources:{id}                                           （单资源详情）
# match:recommend:type:max_price:top_n                     （撮合推荐结果）
# iot:latest:{device_code}                                 （最新一条 IoT 数据）
# iot:alert:latest                                         （最新告警，推 WebSocket 用）
# order:conflict:{resource_id}:{start_ts}:{end_ts}         （时段占位，防冲突）
