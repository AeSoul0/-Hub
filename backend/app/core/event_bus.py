import asyncio
import json

class EventBus:
    def __init__(self):
        # A dictionary mapping session_id to a list of queues
        self.listeners: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
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
        if session_id in self.listeners:
            message = json.dumps({"type": event_type, "data": data})
            # Put the message in all queues for the session
            for queue in self.listeners[session_id]:
                await queue.put(message)

# Global event bus instance
event_bus = EventBus()
