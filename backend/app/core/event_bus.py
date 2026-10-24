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

The desktop app (ADR-020) runs one process for one user and no Redis: with
AEHUB_EVENT_BUS=memory, or REDIS_URL=memory://, events go straight to the
subscriber queues of this process.
"""
import asyncio
import json
import os

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def in_process() -> bool:
    """
    True when events and cache stay inside this process (no Redis).
    """
    return (
        os.getenv("AEHUB_EVENT_BUS", "").strip().lower() == "memory"
        or os.getenv("REDIS_URL", "").startswith("memory://")
    )


def session_channel(session_id: str) -> str:
    return f"session:{session_id}"


def workspace_channel(workspace_id: str) -> str:
    return f"workspace:{workspace_id}"


class EventBus:
    """
    Fan-out of Redis Pub/Sub messages to in-process subscriber queues.
    """

    def __init__(self):
        self.local = in_process()
        self.redis = None if self.local else redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = None if self.local else self.redis.pubsub()
        self.listeners: dict[str, list[asyncio.Queue]] = {}
        self._listener_task = None

    async def _listen_to_redis(self):
        await self.pubsub.psubscribe("session:*", "workspace:*")
        async for message in self.pubsub.listen():
            if message["type"] == "pmessage":
                self._deliver(message["channel"], message["data"])

    def _deliver(self, channel: str, message: str) -> None:
        for queue in list(self.listeners.get(channel, [])):
            queue.put_nowait(message)

    def _subscribe(self, channel: str) -> asyncio.Queue:
        if not self.local and not self._listener_task:
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

        if self.local:
            self._deliver(session_channel(session_id), message)
            if workspace_id:
                self._deliver(workspace_channel(workspace_id), message)
            return

        await self.redis.publish(session_channel(session_id), message)
        if workspace_id:
            await self.redis.publish(workspace_channel(workspace_id), message)


# Global event bus instance
event_bus = EventBus()
