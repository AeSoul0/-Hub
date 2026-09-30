"""
@file backend/app/core/event_bus.py
@description Implements event_bus.py. Core components: EventBus.

This module manages the internal business logic for EventBus.
It provides specialized functionality to handle: _listen_to_redis, subscribe, unsubscribe, publish.
"""
import asyncio
import json
import os

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class EventBus:
    """
    Represents the EventBus entity and its core operations.
    """
    """
    Distributed EventBus using Redis Pub/Sub.
    """
    def __init__(self):
        """
        Executes __init__ logic.
        """
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self.listeners: dict[str, list[asyncio.Queue]] = {}
        self._listener_task = None

    async def _listen_to_redis(self):
        """
        Executes _listen_to_redis logic.
        """
        # Listen to Redis Pub/Sub channels matching the pattern 'session:*'
        # Listen to Redis Pub/Sub channels matching the pattern 'session:*'
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
        """
        Executes subscribe logic.
        """
        # Initialize background listener task if not already running
        # Initialize background listener task if not already running
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._listen_to_redis())
            
        if session_id not in self.listeners:
            self.listeners[session_id] = []
        queue = asyncio.Queue()
        self.listeners[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        """
        Executes unsubscribe logic.
        """
        # Remove a specific listener queue from the session's subscribers
        # Remove a specific listener queue from the session's subscribers
        if session_id in self.listeners:
            if queue in self.listeners[session_id]:
                self.listeners[session_id].remove(queue)
            if not self.listeners[session_id]:
                del self.listeners[session_id]

    async def publish(self, session_id: str, event_type: str, data: dict | str):
        """
        Executes publish logic.
        """
        # Serialize the event data and publish it to the session's Redis channel
        # Serialize the event data and publish it to the session's Redis channel
        message = json.dumps({"type": event_type, "data": data})
        await self.redis.publish(f"session:{session_id}", message)

# Global event bus instance
event_bus = EventBus()
