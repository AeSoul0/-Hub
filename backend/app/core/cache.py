"""
@file backend/app/core/cache.py
@description Implements cache.py. Core components: CacheService.

This module manages the internal business logic for CacheService.
It provides specialized functionality to handle: get_pool, get_client, get, set, delete, check_rate_limit.
"""
import json
import time
from typing import Any, Dict, Optional, Tuple
import redis.asyncio as redis

from app.core.config import settings
from app.core.event_bus import in_process


class LocalCache:
    """
    The few Redis commands CacheService uses, inside this process: the
    desktop app has no Redis (ADR-020). Keys expire lazily, when read.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[Any, Optional[float]]] = {}

    def _live(self, key: str) -> Optional[Any]:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at <= time.monotonic():
            del self._data[key]
            return None
        return value

    async def get(self, key: str) -> Optional[Any]:
        return self._live(key)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        self._data[key] = (value, time.monotonic() + ex if ex else None)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        current = int(self._live(key) or 0) + 1
        _, expires_at = self._data.get(key, (None, None))
        self._data[key] = (current, expires_at)
        return current

    async def expire(self, key: str, seconds: int) -> None:
        if self._live(key) is not None:
            self._data[key] = (self._data[key][0], time.monotonic() + seconds)


class CacheService:
    """
    Represents the CacheService entity and its core operations.
    """
    """
    Distributed Caching Layer (M4).
    Manages Redis connections for Session caching, Rate Limiting, and LLM Response caching.
    """
    _pool: Optional[redis.ConnectionPool] = None
    _local: Optional[LocalCache] = None

    @classmethod
    def get_pool(cls) -> redis.ConnectionPool:
        """
        Executes get_pool logic.
        """
        # Initialize the Redis connection pool if it doesn't exist
        # Initialize the Redis connection pool if it doesn't exist
        if cls._pool is None:
            cls._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL, decode_responses=True
            )
        return cls._pool

    @classmethod
    async def get_client(cls) -> Any:
        """
        Executes get_client logic.
        """
        if in_process():
            if cls._local is None:
                cls._local = LocalCache()
            return cls._local

        # Retrieve a new Redis client instance from the connection pool
        # Retrieve a new Redis client instance from the connection pool
        return redis.Redis(connection_pool=cls.get_pool())

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """
        Executes get logic.
        """
        # Fetch data from Redis and attempt to parse it as JSON
        # Fetch data from Redis and attempt to parse it as JSON
        client = await cls.get_client()
        data = await client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return None

    @classmethod
    async def set(cls, key: str, value: Any, expire_seconds: int = 3600):
        """
        Executes set logic.
        """
        # Serialize dictionaries or lists to JSON strings and store in Redis with expiration
        # Serialize dictionaries or lists to JSON strings and store in Redis with expiration
        client = await cls.get_client()
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await client.set(key, value, ex=expire_seconds)

    @classmethod
    async def delete(cls, key: str):
        """
        Executes delete logic.
        """
        # Remove a specific key from the Redis cache
        # Remove a specific key from the Redis cache
        client = await cls.get_client()
        await client.delete(key)

    @classmethod
    async def check_rate_limit(cls, identifier: str, limit: int, window_seconds: int) -> bool:
        """
        Executes check_rate_limit logic.
        """
        """
        Token bucket / sliding window rate limiting.
        Returns True if request is allowed, False if rate limited.
        """
        client = await cls.get_client()
        key = f"rate_limit:{identifier}"
        
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
            
        if current > limit:
            return False
        return True
