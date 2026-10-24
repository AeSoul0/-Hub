"""
@file backend/app/agent_engine/events.py
@description Implements events.py. Core components: RunEvent, EventDispatcher.

This module manages the internal business logic for RunEvent, EventDispatcher.
It provides specialized functionality to handle: __new__, dispatch, get_events_for_run.
"""
import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Every dispatched event is also pushed live (F1): the Nucleo shows the
# engine at work. Delivery is best effort and never slows a run.
LIVE_EVENT_TYPE = "engine.event"
LIVE_TIMEOUT_SECONDS = 0.5
_live_tasks: set = set()


def broadcast(event: "RunEvent") -> None:
    """
    Publish `event` to its session and workspace channels without waiting.

    Outside an event loop (a script, a sync test) there is nobody listening
    live, so nothing is sent.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def send() -> None:
        try:
            from app.core.event_bus import event_bus

            await asyncio.wait_for(
                event_bus.publish(
                    event.session_id,
                    LIVE_EVENT_TYPE,
                    event.model_dump(),
                    workspace_id=event.workspace_id,
                ),
                timeout=LIVE_TIMEOUT_SECONDS,
            )
        except Exception:
            pass

    task = loop.create_task(send())
    _live_tasks.add(task)
    task.add_done_callback(_live_tasks.discard)


# Updated RunEvent schema based on Phase 9 requirements
class RunEvent(BaseModel):
    """
    Represents the RunEvent entity and its core operations.
    """
    event_type: str
    run_id: str
    parent_run_id: Optional[str] = None
    session_id: str
    workspace_id: str
    task_id: Optional[str] = None
    attempt: Optional[int] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    latency: Optional[float] = None
    tokens: Optional[int] = None
    cost: Optional[float] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    role: Optional[str] = None
    tool: Optional[str] = None
    risk: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

FLIGHT_RECORDER_FILE = os.getenv("AEHUB_FLIGHT_RECORDER_PATH", "flight_recorder.jsonl")

class EventDispatcher:
    """
    Represents the EventDispatcher entity and its core operations.
    """
    """
    Phase 9 Agent Flight Recorder.
    Writes structured events to a JSONL log for full run reconstructability.
    """
    
    _instance = None
    
    def __new__(cls):
        """
        Executes __new__ logic.
        """
        if cls._instance is None:
            cls._instance = super(EventDispatcher, cls).__new__(cls)
        return cls._instance

    def dispatch(self, 
                 event_type: str, 
                 run_id: str, 
                 session_id: str,
                 workspace_id: str,
                 **kwargs) -> RunEvent:
                 
        """
        Executes dispatch logic.
        """
        event = RunEvent(
            event_type=event_type,
            run_id=run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            **kwargs
        )
        
        # Append to jsonl flight recorder
        with open(FLIGHT_RECORDER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump()) + "\n")

        broadcast(event)

        return event

    def get_events_for_run(self, run_id: str) -> List[RunEvent]:
        """
        Executes get_events_for_run logic.
        """
        events = []
        if os.path.exists(FLIGHT_RECORDER_FILE):
            with open(FLIGHT_RECORDER_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    if data.get("run_id") == run_id:
                        events.append(RunEvent(**data))
        return events
