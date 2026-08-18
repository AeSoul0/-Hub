"""
@file backend/app/core/cache.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import json
from typing import Any, Optional
import redis.asyncio as redis

from app.core.config import settings

class CacheService:
    """
    Distributed Caching Layer (M4).
    Manages Redis connections for Session caching, Rate Limiting, and LLM Response caching.
    """
    _pool: Optional[redis.ConnectionPool] = None

    @classmethod
    def get_pool(cls) -> redis.ConnectionPool:
        if cls._pool is None:
            cls._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL, decode_responses=True
            )
        return cls._pool

    @classmethod
    async def get_client(cls) -> redis.Redis:
        return redis.Redis(connection_pool=cls.get_pool())

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
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
        client = await cls.get_client()
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await client.set(key, value, ex=expire_seconds)

    @classmethod
    async def delete(cls, key: str):
        client = await cls.get_client()
        await client.delete(key)

    @classmethod
    async def check_rate_limit(cls, identifier: str, limit: int, window_seconds: int) -> bool:
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
