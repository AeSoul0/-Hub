"""
@file backend/app/agent_engine/state/manager.py
@description Implements manager.py. Core components: AgentStateManager.

This module manages the internal business logic for AgentStateManager.
It provides specialized functionality to handle: save_state, load_state, save_agent_run, load_agent_run.
"""
import json
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.db import SessionLocal
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.agent_engine.models import AgentRun, AgentRunStatus

class AgentStateManager:
    """
    Represents the AgentStateManager entity and its core operations.
    """
    @classmethod
    def save_state(cls, run_id: str, state: Dict[str, Any]):
        """
        Executes save_state logic.
        """
        with SessionLocal() as db:
            record = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).first()
            if record:
                # We store 'state' as result if it's the final dict, or somewhere else.
                # In this architecture, state is merged with AgentRun
                pass # Usually handled by save_agent_run

    @classmethod
    def load_state(cls, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Executes load_state logic.
        """
        return None

    @classmethod
    def save_agent_run(cls, run: AgentRun):
        """
        Executes save_agent_run logic.
        """
        with SessionLocal() as db:
            record = db.query(DbAgentRun).filter(DbAgentRun.id == run.run_id).first()
            if not record:
                record = DbAgentRun(
                    id=run.run_id,
                    session_id=run.session_id,
                    principal_id="system", # fallback
                    role=run.role,
                    input_data=json.dumps(run.input_data) if isinstance(run.input_data, dict) else str(run.input_data),
                    status=run.status.value,
                    result=json.dumps(run.result) if run.result else None,
                    error=run.error
                )
                db.add(record)
            else:
                record.status = run.status.value
                record.result = json.dumps(run.result) if run.result else None
                record.error = run.error
            db.commit()

    @classmethod
    def load_agent_run(cls, run_id: str) -> Optional[AgentRun]:
        """
        Executes load_agent_run logic.
        """
        with SessionLocal() as db:
            record = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).first()
            if record:
                return AgentRun(
                    run_id=record.id,
                    session_id=record.session_id,
                    role=record.role,
                    input_data=json.loads(record.input_data) if record.input_data.startswith("{") else record.input_data,
                    status=AgentRunStatus(record.status),
                    result=json.loads(record.result) if record.result else None,
                    error=record.error,
                    created_at=record.created_at,
                    updated_at=record.updated_at
                )
        return None
