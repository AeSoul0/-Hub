"""
@file backend/app/core/event_bus.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import asyncio
import json
import os

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class EventBus:
    """
    Distributed EventBus using Redis Pub/Sub.
    """
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self.listeners: dict[str, list[asyncio.Queue]] = {}
        self._listener_task = None

    async def _listen_to_redis(self):
        await self.pubsub.psubscribe("session:*")
        async for message in self.pubsub.listen():
            if message["type"] == "pmessage":
                channel = message["channel"]
                session_id = channel.split(":", 1)[1]
                data = message["data"]
                
                if session_id in self.listeners:
                    for queue in self.listeners[session_id]:
                        await queue.put(data)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._listen_to_redis())
            
        if session_id not in self.listeners:
            self.listeners[session_id] = []
        queue = asyncio.Queue()
        self.listeners[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        if session_id in self.listeners:
            if queue in self.listeners[session_id]:
                self.listeners[session_id].remove(queue)
            if not self.listeners[session_id]:
                del self.listeners[session_id]

    async def publish(self, session_id: str, event_type: str, data: dict | str):
        message = json.dumps({"type": event_type, "data": data})
        await self.redis.publish(f"session:{session_id}", message)

# Global event bus instance
event_bus = EventBus()
