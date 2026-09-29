"""
@file backend/app/agent_engine/state/manager.py
@description Durable State Persistence Manager.

Responsible for checkpointing AgentRun models to disk (durable_runs.json). 
Guarantees that process crashes do not lose context, allowing seamless recovery 
and resumption of iterations exactly where they left off (Phase 5).
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
from app.agent_engine.models import AgentRun, AgentRunStatus

STATE_FILE = "agent_runs.json"

class AgentStateManager:
    @classmethod
    def save_state(cls, run_id: str, state: Dict[str, Any]):
        data = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        data[run_id] = state
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def load_state(cls, run_id: str) -> Optional[Dict[str, Any]]:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            return data.get(run_id)
        return None

    @classmethod
    def save_agent_run(cls, run: AgentRun):
        data = {}
        if os.path.exists("durable_runs.json"):
            with open("durable_runs.json", "r") as f:
                data = json.load(f)
        
        # Serialize
        serialized = run.dict()
        if "created_at" in serialized:
            serialized["created_at"] = serialized["created_at"].isoformat()
        if "updated_at" in serialized:
            serialized["updated_at"] = serialized["updated_at"].isoformat()
            
        data[run.run_id] = serialized
        with open("durable_runs.json", "w") as f:
            json.dump(data, f)

    @classmethod
    def load_agent_run(cls, run_id: str) -> Optional[AgentRun]:
        if os.path.exists("durable_runs.json"):
            with open("durable_runs.json", "r") as f:
                data = json.load(f)
            raw = data.get(run_id)
            if raw:
                # Deserialize
                if "created_at" in raw:
                    raw["created_at"] = datetime.fromisoformat(raw["created_at"])
                if "updated_at" in raw:
                    raw["updated_at"] = datetime.fromisoformat(raw["updated_at"])
                return AgentRun(**raw)
        return None
