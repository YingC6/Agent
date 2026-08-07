"""缓存服务"""

import json
from typing import Any
from loguru import logger
from redis import Redis
from redis.exceptions import RedisError
from ..config import get_settings

_cache_client: Redis | None = None


def get_cache_client() -> Redis | None:
    global _cache_client
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _cache_client is None:
        try:
            _cache_client = Redis.from_url(settings.redis_url, decode_responses=True)
            _cache_client.ping()
        except RedisError as exc:
            logger.warning(f"Redis不可用,将跳过缓存: {exc}")
            _cache_client = None
    return _cache_client


def cache_get(key: str) -> Any | None:
    client = get_cache_client()
    if not client:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value else None
    except Exception as exc:
        logger.warning(f"读取缓存失败: {exc}")
        return None


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    client = get_cache_client()
    if not client:
        return
    try:
        client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as exc:
        logger.warning(f"写入缓存失败: {exc}")


def rate_limit_check(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    client = get_cache_client()
    if not client:
        return True, 0
    try:
        current = client.incr(key)
        if current == 1:
            client.expire(key, window_seconds)
        ttl = client.ttl(key)
        return current <= limit, max(ttl, 0)
    except Exception as exc:
        logger.warning(f"限流检查失败: {exc}")
        return True, 0
