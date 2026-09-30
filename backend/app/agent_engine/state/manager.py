"""
@file backend/app/agent_engine/state/manager.py
@description Durable PostgreSQL state management for native Agent Runtime runs.

This module is responsible for serializing, persisting, loading, and restoring
AgentRun checkpoints. Persistence is deliberately implemented behind a small
manager boundary so the orchestration runtime never depends directly on ORM
records or database-specific serialization details.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.agent_engine.models import AgentRun, AgentRunStatus
from app.core.db import SessionLocal
from app.domain.models.runtime_state import AgentRun as DbAgentRun


def _serialize_run(run: AgentRun) -> str:
    """
    Serialize a native AgentRun into a JSON snapshot.

    Pydantic v2 is the supported runtime version. The fallback keeps the
    manager compatible with legacy callers during the migration period.
    """

    if hasattr(run, "model_dump"):
        payload = run.model_dump(mode="json")
    else:
        payload = run.dict()

    return json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )


def _deserialize_result(result: Optional[str]) -> Any:
    """
    Restore a persisted result when it contains JSON.

    Plain-text legacy values are returned unchanged.
    """

    if result is None:
        return None

    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return result


class AgentStateManager:
    """
    Durable persistence boundary for native Agent Runtime state.
    """

    @classmethod
    def save_state(
        cls,
        run_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Replace the current runtime checkpoint for an existing run.
        """

        run = cls.load_agent_run(run_id)

        if run is None:
            raise ValueError(
                f"Cannot save state: agent run '{run_id}' does not exist."
            )

        run.current_state = state
        run.updated_at = datetime.utcnow()

        cls.save_agent_run(run)

    @classmethod
    def load_state(
        cls,
        run_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load the serialized runtime checkpoint for a run.
        """

        run = cls.load_agent_run(run_id)

        if run is None:
            return None

        return run.current_state

    @classmethod
    def save_agent_run(
        cls,
        run: AgentRun,
    ) -> None:
        """
        Persist the complete AgentRun snapshot.

        The complete Pydantic model is stored in input_data so fields such as
        workspace_id, current_state, task_attempts, metadata, and usage survive
        process restarts without requiring a column migration for every runtime
        feature.
        """

        serialized_snapshot = _serialize_run(run)

        serialized_result = None
        if run.result is not None:
            serialized_result = json.dumps(
                run.result,
                ensure_ascii=False,
                default=str,
            )

        with SessionLocal() as db:
            record = (
                db.query(DbAgentRun)
                .filter(DbAgentRun.id == run.run_id)
                .first()
            )

            if record is None:
                record = DbAgentRun(
                    id=run.run_id,
                    session_id=run.session_id,
                    principal_id=run.principal_id or "system",
                    role=run.role,
                    input_data=serialized_snapshot,
                    status=run.status.value,
                    result=serialized_result,
                    error=run.error,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
                db.add(record)

            else:
                record.session_id = run.session_id
                record.principal_id = (
                    run.principal_id
                    or record.principal_id
                    or "system"
                )
                record.role = run.role
                record.input_data = serialized_snapshot
                record.status = run.status.value
                record.result = serialized_result
                record.error = run.error
                record.updated_at = run.updated_at

            db.commit()

    @classmethod
    def load_agent_run(
        cls,
        run_id: str,
    ) -> Optional[AgentRun]:
        """
        Reconstruct a native AgentRun from its durable database snapshot.

        Legacy records that predate the snapshot format are handled using a
        conservative compatibility path rather than silently failing.
        """

        with SessionLocal() as db:
            record = (
                db.query(DbAgentRun)
                .filter(DbAgentRun.id == run_id)
                .first()
            )

            if record is None:
                return None

            try:
                snapshot = json.loads(record.input_data)

                snapshot["status"] = AgentRunStatus(record.status).value
                snapshot["result"] = _deserialize_result(record.result)
                snapshot["error"] = record.error
                snapshot["updated_at"] = record.updated_at

                if not snapshot.get("created_at"):
                    snapshot["created_at"] = record.created_at

                return AgentRun(**snapshot)

            except (
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ):
                # Compatibility path for records written by the previous
                # persistence implementation.
                return AgentRun(
                    run_id=record.id,
                    session_id=record.session_id,
                    workspace_id="default_workspace",
                    principal_id=record.principal_id,
                    role=record.role or "agent",
                    status=AgentRunStatus(record.status),
                    result=_deserialize_result(record.result),
                    error=record.error,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )