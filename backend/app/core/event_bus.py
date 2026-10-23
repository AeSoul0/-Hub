"""
@file backend/app/core/event_bus.py
@description Realtime event bus on Redis Pub/Sub.

Two kinds of channel:
- `session:{id}`: everything about one login session (chat log lines, run
  states, approvals). The chat WebSocket and `/api/events` listen here.
- `workspace:{id}`: the control-plane events of every session of a workspace
  (run states, approval requested/decided, run resumed), so the Control
  Plane updates without polling. Approvals are already workspace-scoped.

Delivery is best effort: durable state lives in PostgreSQL.
"""
import asyncio
import json
import os

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def session_channel(session_id: str) -> str:
    return f"session:{session_id}"


def workspace_channel(workspace_id: str) -> str:
    return f"workspace:{workspace_id}"


class EventBus:
    """
    Fan-out of Redis Pub/Sub messages to in-process subscriber queues.
    """

    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self.listeners: dict[str, list[asyncio.Queue]] = {}
        self._listener_task = None

    async def _listen_to_redis(self):
        await self.pubsub.psubscribe("session:*", "workspace:*")
        async for message in self.pubsub.listen():
            if message["type"] == "pmessage":
                for queue in self.listeners.get(message["channel"], []):
                    await queue.put(message["data"])

    def _subscribe(self, channel: str) -> asyncio.Queue:
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._listen_to_redis())

        queue = asyncio.Queue()
        self.listeners.setdefault(channel, []).append(queue)
        return queue

    def _unsubscribe(self, channel: str, queue: asyncio.Queue):
        queues = self.listeners.get(channel)
        if queues is None:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            del self.listeners[channel]

    def subscribe(self, session_id: str) -> asyncio.Queue:
        return self._subscribe(session_channel(session_id))

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        self._unsubscribe(session_channel(session_id), queue)

    def subscribe_workspace(self, workspace_id: str) -> asyncio.Queue:
        return self._subscribe(workspace_channel(workspace_id))

    def unsubscribe_workspace(self, workspace_id: str, queue: asyncio.Queue):
        self._unsubscribe(workspace_channel(workspace_id), queue)

    async def publish(
        self,
        session_id: str,
        event_type: str,
        data: dict | str,
        workspace_id: str = "",
    ):
        """
        Publish to the session; with a workspace, also to the workspace
        channel the Control Plane listens on.
        """
        message = json.dumps({"type": event_type, "data": data})
        await self.redis.publish(session_channel(session_id), message)
        if workspace_id:
            await self.redis.publish(workspace_channel(workspace_id), message)


# Global event bus instance
event_bus = EventBus()
