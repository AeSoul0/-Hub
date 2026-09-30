"""
@file backend/app/agent_engine/run.py
@description Agent run lifecycle management for the native Agent Engine.

This module owns creation and controlled state transitions for AgentRun instances.
It deliberately keeps orchestration state in the Pydantic runtime model and
delegates durable persistence to AgentStateManager when a database session is
configured.

The lifecycle implemented here is intentionally explicit:

    QUEUED -> RUNNING -> COMPLETED
                    -> FAILED
                    -> CANCELLED

Additional transitions used by the engine, such as approval and retry states,
remain available through the shared AgentRunStatus enum and may be persisted by
higher-level orchestration code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from app.agent_engine.models import AgentRun, AgentRunStatus
from app.agent_engine.state.manager import AgentStateManager


class RunManager:
    """
    Manage creation, mutation, and persistence of AgentRun instances.
    """

    def __init__(self, db_session=None) -> None:
        """
        Initialize the run manager.

        Args:
            db_session: Optional database/session handle retained for caller
                compatibility. Durable runtime persistence is handled through
                AgentStateManager so lifecycle semantics stay centralized.
        """
        self.db = db_session

    def create_run(
        self,
        session_id: str,
        workspace_id: str,
        parent_run_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        role: str = "agent",
        metadata: Optional[dict] = None,
    ) -> AgentRun:
        """
        Create a new queued AgentRun with a collision-resistant identifier.

        The run is not marked as running here. Execution workers are responsible
        for transitioning the run to RUNNING once the job has actually started.
        """
        if not session_id:
            raise ValueError("session_id is required")

        if not workspace_id:
            raise ValueError("workspace_id is required")

        run = AgentRun(
            run_id=f"run_{uuid4().hex}",
            parent_run_id=parent_run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            role=role,
            status=AgentRunStatus.QUEUED,
            metadata=dict(metadata or {}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        return self._persist(run)

    def start_run(self, run: AgentRun) -> AgentRun:
        """
        Transition a queued/retrying run into the running state.
        """
        self._require_transition(
            run.status,
            {AgentRunStatus.QUEUED, AgentRunStatus.RETRYING},
            AgentRunStatus.RUNNING,
        )

        run.status = AgentRunStatus.RUNNING
        return self._touch_and_persist(run)

    def complete_run(self, run: AgentRun, result=None) -> AgentRun:
        """
        Mark a running or waiting run as completed.
        """
        self._require_transition(
            run.status,
            {
                AgentRunStatus.RUNNING,
                AgentRunStatus.WAITING_TOOL,
                AgentRunStatus.WAITING_APPROVAL,
            },
            AgentRunStatus.COMPLETED,
        )

        run.status = AgentRunStatus.COMPLETED
        run.result = result
        run.error = None
        return self._touch_and_persist(run)

    def fail_run(self, run: AgentRun, error: str) -> AgentRun:
        """
        Mark a run as failed and retain a machine-readable error message.
        """
        if not error:
            raise ValueError("error is required")

        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.EXPIRED,
        }:
            raise ValueError(
                f"Cannot fail a terminal run with status '{run.status.value}'"
            )

        run.status = AgentRunStatus.FAILED
        run.error = error
        run.errors.append(error)
        return self._touch_and_persist(run)

    def cancel_run(self, run: AgentRun) -> AgentRun:
        """
        Cancel a non-terminal run.
        """
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.EXPIRED,
        }:
            raise ValueError(
                f"Cannot cancel a terminal run with status '{run.status.value}'"
            )

        run.status = AgentRunStatus.CANCELLED
        return self._touch_and_persist(run)

    def save(self, run: AgentRun) -> AgentRun:
        """
        Explicitly persist the supplied runtime snapshot.
        """
        return self._persist(run)

    @staticmethod
    def _touch(run: AgentRun) -> AgentRun:
        """
        Update the runtime modification timestamp.
        """
        run.updated_at = datetime.utcnow()
        return run

    def _touch_and_persist(self, run: AgentRun) -> AgentRun:
        """
        Update timestamps and persist the resulting runtime state.
        """
        return self._persist(self._touch(run))

    @staticmethod
    def _persist(run: AgentRun) -> AgentRun:
        """
        Persist a run when durable state management is available.

        Persistence failures are intentionally propagated instead of being
        silently ignored: losing a state transition can corrupt orchestration.
        """
        AgentStateManager.save_agent_run(run)
        return run

    @staticmethod
    def _require_transition(
        current: AgentRunStatus,
        allowed: set[AgentRunStatus],
        target: AgentRunStatus,
    ) -> None:
        """
        Validate a lifecycle transition before mutating the run.
        """
        if current not in allowed:
            allowed_values = ", ".join(sorted(status.value for status in allowed))
            raise ValueError(
                f"Invalid AgentRun transition: "
                f"'{current.value}' -> '{target.value}'. "
                f"Allowed source states: {allowed_values}"
            )