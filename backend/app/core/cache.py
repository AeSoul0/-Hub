"""
@file backend/app/core/cache.py
@description Implements cache.py. Core components: CacheService.

This module manages the internal business logic for CacheService.
It provides specialized functionality to handle: get_pool, get_client, get, set, delete, check_rate_limit.
"""
import json
from typing import Any, Optional
import redis.asyncio as redis

from app.core.config import settings

class CacheService:
    """
    Represents the CacheService entity and its core operations.
    """
    """
    Distributed Caching Layer (M4).
    Manages Redis connections for Session caching, Rate Limiting, and LLM Response caching.
    """
    _pool: Optional[redis.ConnectionPool] = None

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
    async def get_client(cls) -> redis.Redis:
        """
        Executes get_client logic.
        """
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
