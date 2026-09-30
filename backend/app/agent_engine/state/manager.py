"""
@file backend/app/agent_engine/state/manager.py
@description Durable PostgreSQL state management for native Agent Runtime runs.

This module serializes, persists, loads, and restores AgentRun checkpoints.

Security invariants:
- Every persisted run must have an explicit principal binding.
- Missing principal identity is rejected instead of replaced with a system user.
- Workspace/session/principal isolation is preserved in the serialized snapshot.
- Legacy records without complete security context are reconstructed in a
  fail-closed state so the runtime cannot accidentally resume them.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.agent_engine.models import (
    AgentRun,
    AgentRunStatus,
)
from app.core.db import SessionLocal
from app.domain.models.runtime_state import AgentRun as DbAgentRun


# ==============================================================================
# SERIALIZATION HELPERS
# ==============================================================================


def _serialize_run(
    run: AgentRun,
) -> str:
    """
    Serialize a native AgentRun into a JSON snapshot.

    Pydantic v2 is the supported runtime version. The legacy fallback is
    retained only for migration compatibility.
    """
    if hasattr(
        run,
        "model_dump",
    ):
        payload = run.model_dump(
            mode="json"
        )
    else:
        payload = run.dict()

    return json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )


def _deserialize_result(
    result: Optional[str],
) -> Any:
    """
    Restore a persisted result when it contains JSON.

    Plain-text legacy values are returned unchanged.
    """
    if result is None:
        return None

    try:
        return json.loads(result)
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return result


def _require_principal(
    run: AgentRun,
) -> str:
    """
    Require an explicit principal binding before persistence.

    Durable state must never silently acquire a synthetic system identity.
    """
    if not run.principal_id or not run.principal_id.strip():
        raise ValueError(
            "Cannot persist AgentRun without an explicit principal_id."
        )

    return run.principal_id


# ==============================================================================
# DURABLE STATE MANAGER
# ==============================================================================


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
        run = cls.load_agent_run(
            run_id
        )

        if run is None:
            raise ValueError(
                f"Cannot save state: agent run "
                f"'{run_id}' does not exist."
            )

        run.current_state = state
        run.updated_at = datetime.utcnow()

        cls.save_agent_run(
            run
        )

    @classmethod
    def load_state(
        cls,
        run_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load the serialized runtime checkpoint for one run.
        """
        run = cls.load_agent_run(
            run_id
        )

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

        Principal identity is mandatory. The full Pydantic snapshot is stored
        in input_data so runtime state survives process restarts without
        requiring a relational column for every orchestration field.
        """
        principal_id = _require_principal(
            run
        )

        serialized_snapshot = _serialize_run(
            run
        )

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
                .filter(
                    DbAgentRun.id
                    == run.run_id
                )
                .first()
            )

            if record is None:
                record = DbAgentRun(
                    id=run.run_id,
                    session_id=run.session_id,
                    principal_id=principal_id,
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
                record.session_id = (
                    run.session_id
                )

                record.principal_id = (
                    principal_id
                )

                record.role = run.role
                record.input_data = (
                    serialized_snapshot
                )
                record.status = (
                    run.status.value
                )
                record.result = (
                    serialized_result
                )
                record.error = run.error
                record.updated_at = (
                    run.updated_at
                )

            db.commit()

    @classmethod
    def load_agent_run(
        cls,
        run_id: str,
    ) -> Optional[AgentRun]:
        """
        Reconstruct a native AgentRun from its durable database snapshot.

        Legacy records are handled conservatively. Missing workspace context
        is represented as an empty binding rather than a default workspace so
        security validation rejects accidental cross-tenant continuation.
        """
        if not run_id or not run_id.strip():
            raise ValueError(
                "run_id is required."
            )

        with SessionLocal() as db:
            record = (
                db.query(DbAgentRun)
                .filter(
                    DbAgentRun.id
                    == run_id
                )
                .first()
            )

            if record is None:
                return None

            try:
                snapshot = json.loads(
                    record.input_data
                )

                snapshot["status"] = (
                    AgentRunStatus(
                        record.status
                    ).value
                )

                snapshot["result"] = (
                    _deserialize_result(
                        record.result
                    )
                )

                snapshot["error"] = record.error
                snapshot["updated_at"] = (
                    record.updated_at
                )

                if not snapshot.get(
                    "created_at"
                ):
                    snapshot["created_at"] = (
                        record.created_at
                    )

                # The relational principal binding remains authoritative.
                snapshot["principal_id"] = (
                    record.principal_id
                )

                # Do not invent tenant scope for legacy records.
                if not snapshot.get(
                    "workspace_id"
                ):
                    snapshot["workspace_id"] = ""

                return AgentRun(
                    **snapshot
                )

            except (
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ):
                # Compatibility path for records created by an older
                # persistence implementation. Security-sensitive fields are
                # deliberately left incomplete when they were not persisted.
                return AgentRun(
                    run_id=record.id,
                    session_id=record.session_id,
                    workspace_id="",
                    principal_id=record.principal_id,
                    role=record.role or "agent",
                    status=AgentRunStatus(
                        record.status
                    ),
                    result=_deserialize_result(
                        record.result
                    ),
                    error=record.error,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )


__all__ = [
    "AgentStateManager",
]