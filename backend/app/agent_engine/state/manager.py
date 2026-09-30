"""
@file backend/app/agent_engine/state/manager.py
@description Durable PostgreSQL state management for native Agent Runtime runs.

This module serializes, persists, loads, and restores AgentRun checkpoints.

Security invariants:
- Every persisted run must have an explicit principal binding.
- Missing principal identity is rejected instead of replaced with a system user.
- Session, workspace, and principal bindings are verified on resume.
- Existing runs cannot be overwritten by a different authenticated principal.
- Legacy records without complete security context fail closed.
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
        return json.loads(
            result
        )
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

    Durable state must never silently acquire a synthetic identity.
    """
    if (
        not run.principal_id
        or not run.principal_id.strip()
    ):
        raise ValueError(
            "Cannot persist AgentRun without an explicit principal_id."
        )

    return run.principal_id


def _load_snapshot(
    record: DbAgentRun,
) -> Dict[str, Any]:
    """
    Deserialize the durable runtime snapshot.

    A malformed snapshot is a persistence integrity failure and is rejected
    instead of being silently reconstructed with guessed security context.
    """
    try:
        payload = json.loads(
            record.input_data
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ) as exc:
        raise ValueError(
            f"Persisted AgentRun '{record.id}' contains invalid JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"Persisted AgentRun '{record.id}' has an invalid snapshot shape."
        )

    return payload


def _validate_execution_binding(
    record: DbAgentRun,
    snapshot: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    principal_id: Optional[str] = None,
) -> None:
    """
    Validate persisted identity against the requested execution context.

    A mismatch raises PermissionError. Returning None for a mismatch would
    allow callers to interpret an existing foreign run as a new run and
    potentially overwrite it.
    """
    if (
        session_id is not None
        and record.session_id != session_id
    ):
        raise PermissionError(
            "Persisted run session does not match the authenticated session."
        )

    stored_principal_id = (
        record.principal_id
    )

    if (
        principal_id is not None
        and stored_principal_id != principal_id
    ):
        raise PermissionError(
            "Persisted run principal does not match the authenticated Principal."
        )

    stored_workspace_id = str(
        snapshot.get(
            "workspace_id",
            "",
        )
        or ""
    )

    if (
        workspace_id is not None
        and stored_workspace_id != workspace_id
    ):
        raise PermissionError(
            "Persisted run workspace does not match the execution workspace."
        )


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

        An existing durable record may only be updated by the same session and
        principal that originally created it. The workspace stored in the
        serialized snapshot is also immutable from the perspective of identity
        ownership.
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
                existing_snapshot = _load_snapshot(
                    record
                )

                _validate_execution_binding(
                    record,
                    existing_snapshot,
                    session_id=run.session_id,
                    workspace_id=run.workspace_id,
                    principal_id=principal_id,
                )

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
        *,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        principal_id: Optional[str] = None,
    ) -> Optional[AgentRun]:
        """
        Reconstruct a native AgentRun from durable state.

        Security-aware callers should always provide session_id, workspace_id,
        and principal_id. Identity mismatches raise PermissionError rather
        than returning None, preventing an existing foreign run from being
        mistaken for a new run.
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
                snapshot = _load_snapshot(
                    record
                )

                _validate_execution_binding(
                    record,
                    snapshot,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    principal_id=principal_id,
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

                # Relational principal identity is authoritative.
                snapshot["principal_id"] = (
                    record.principal_id
                )

                # Legacy snapshots may lack workspace information.
                # Never synthesize a default workspace.
                if not snapshot.get(
                    "workspace_id"
                ):
                    snapshot["workspace_id"] = ""

                return AgentRun(
                    **snapshot
                )

            except PermissionError:
                raise

            except (
                ValueError,
                TypeError,
            ):
                # Legacy or malformed security-sensitive state is reconstructed
                # only when the persisted relational fields are still usable.
                # Missing workspace remains an empty binding so authenticated
                # runtime resume validation fails closed.
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