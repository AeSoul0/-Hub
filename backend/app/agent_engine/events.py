"""
@file backend/app/agent_engine/events.py
@description Observability and Agent Flight Recorder.

Implements the deterministic event logger for Phase 9. 
Records detailed run traces (orchestrator, tool gateways, checker) to disk 
so entire execution loops can be reconstructed exactly as they happened.
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Updated RunEvent schema based on Phase 9 requirements
class RunEvent(BaseModel):
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

FLIGHT_RECORDER_FILE = "flight_recorder.jsonl"

class EventDispatcher:
    """
    Phase 9 Agent Flight Recorder.
    Writes structured events to a JSONL log for full run reconstructability.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventDispatcher, cls).__new__(cls)
        return cls._instance

    def dispatch(self, 
                 event_type: str, 
                 run_id: str, 
                 session_id: str,
                 workspace_id: str,
                 **kwargs) -> RunEvent:
                 
        event = RunEvent(
            event_type=event_type,
            run_id=run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            **kwargs
        )
        
        # Append to jsonl flight recorder
        with open(FLIGHT_RECORDER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.dict()) + "\n")
            
        return event

    def get_events_for_run(self, run_id: str) -> List[RunEvent]:
        events = []
        if os.path.exists(FLIGHT_RECORDER_FILE):
            with open(FLIGHT_RECORDER_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    if data.get("run_id") == run_id:
                        events.append(RunEvent(**data))
        return events
