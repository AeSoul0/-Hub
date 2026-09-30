"""
@file tests/unit/test_state_manager.py
@description Unit tests for durable native AgentRun state management.

The suite verifies:
- complete snapshot persistence;
- explicit principal binding;
- session/workspace/principal validation;
- protection against cross-principal overwrite;
- fail-closed handling of incomplete legacy security context.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.agent_engine.models import (
    AgentRun,
    AgentRunStatus,
)
from app.agent_engine.state.manager import AgentStateManager
from app.domain.models.runtime_state import (
    AgentRun as DbAgentRun,
)


# ==============================================================================
# TEST FIXTURES
# ==============================================================================


def make_run(
    *,
    run_id="run-test",
    session_id="session-test",
    principal_id="user-1",
    workspace_id="workspace-1",
) -> AgentRun:
    """
    Create a complete native AgentRun test object.
    """
    now = datetime.utcnow()

    return AgentRun(
        run_id=run_id,
        session_id=session_id,
        workspace_id=workspace_id,
        principal_id=principal_id,
        role="user",
        status=AgentRunStatus.RUNNING,
        metadata={
            "source": "unit-test",
        },
        current_state={
            "turn": 1,
            "worker_context": {
                "task": {
                    "description": "test",
                },
            },
        },
        messages=[],
        task_attempts=1,
        errors=[],
        usage={
            "tokens": 10,
        },
        created_at=now,
        updated_at=now,
    )


def configure_session(
    mock_session_local,
    record=None,
):
    """
    Configure the SQLAlchemy-style mocked session boundary.
    """
    mock_db = MagicMock()

    context = mock_session_local.return_value

    context.__enter__.return_value = (
        mock_db
    )

    context.__exit__.return_value = None

    (
        mock_db.query.return_value
        .filter.return_value
        .first.return_value
    ) = record

    return mock_db


def make_db_record(
    run: AgentRun,
):
    """
    Create a database-style record containing a complete snapshot.
    """
    record = MagicMock(
        spec=DbAgentRun
    )

    record.id = run.run_id
    record.session_id = run.session_id
    record.principal_id = run.principal_id
    record.role = run.role
    record.input_data = (
        run.model_dump_json()
    )
    record.status = run.status.value
    record.result = None
    record.error = None
    record.created_at = run.created_at
    record.updated_at = run.updated_at

    return record


# ==============================================================================
# PERSISTENCE TESTS
# ==============================================================================


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_save_agent_run_persists_complete_snapshot(
    mock_session_local,
):
    """
    Save the complete runtime snapshot together with its principal binding.
    """
    mock_db = configure_session(
        mock_session_local
    )

    run = make_run()

    AgentStateManager.save_agent_run(
        run
    )

    record = (
        mock_db.add.call_args.args[0]
    )

    assert record.id == run.run_id
    assert (
        record.session_id
        == run.session_id
    )
    assert (
        record.principal_id
        == run.principal_id
    )
    assert (
        record.role
        == run.role
    )
    assert (
        record.status
        == run.status.value
    )

    snapshot = json.loads(
        record.input_data
    )

    assert (
        snapshot["run_id"]
        == run.run_id
    )
    assert (
        snapshot["workspace_id"]
        == run.workspace_id
    )
    assert (
        snapshot["principal_id"]
        == run.principal_id
    )
    assert (
        snapshot["current_state"]
        == run.current_state
    )

    mock_db.commit.assert_called_once()


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_save_agent_run_rejects_missing_principal(
    mock_session_local,
):
    """
    A run without principal identity must never be persisted.
    """
    run = make_run(
        principal_id=None
    )

    with pytest.raises(
        ValueError,
        match="principal_id",
    ):
        AgentStateManager.save_agent_run(
            run
        )

    mock_session_local.assert_not_called()


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_save_agent_run_updates_existing_record(
    mock_session_local,
):
    """
    Existing durable runs may be updated only by the same security context.
    """
    run = make_run()

    record = make_db_record(
        run
    )

    mock_db = configure_session(
        mock_session_local,
        record=record,
    )

    AgentStateManager.save_agent_run(
        run
    )

    assert (
        record.principal_id
        == "user-1"
    )

    assert record.input_data
    mock_db.add.assert_not_called()
    mock_db.commit.assert_called_once()


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_save_agent_run_rejects_cross_principal_overwrite(
    mock_session_local,
):
    """
    An authenticated principal cannot overwrite another user's run.
    """
    stored_run = make_run(
        principal_id="user-1"
    )

    attempted_run = make_run(
        principal_id="user-2"
    )

    record = make_db_record(
        stored_run
    )

    mock_db = configure_session(
        mock_session_local,
        record=record,
    )

    with pytest.raises(
        PermissionError,
        match="principal",
    ):
        AgentStateManager.save_agent_run(
            attempted_run
        )

    mock_db.commit.assert_not_called()


# ==============================================================================
# LOAD TESTS
# ==============================================================================


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_load_agent_run_restores_snapshot(
    mock_session_local,
):
    """
    Reconstruct a native AgentRun from a complete durable snapshot.
    """
    run = make_run()

    record = make_db_record(
        run
    )

    configure_session(
        mock_session_local,
        record=record,
    )

    restored = AgentStateManager.load_agent_run(
        run.run_id,
        session_id=run.session_id,
        workspace_id=run.workspace_id,
        principal_id=run.principal_id,
    )

    assert restored is not None
    assert (
        restored.run_id
        == run.run_id
    )
    assert (
        restored.session_id
        == run.session_id
    )
    assert (
        restored.workspace_id
        == run.workspace_id
    )
    assert (
        restored.principal_id
        == run.principal_id
    )
    assert (
        restored.current_state
        == run.current_state
    )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_load_agent_run_rejects_session_mismatch(
    mock_session_local,
):
    """
    A run cannot be resumed from another authenticated session.
    """
    run = make_run()

    record = make_db_record(
        run
    )

    configure_session(
        mock_session_local,
        record=record,
    )

    with pytest.raises(
        PermissionError,
        match="session",
    ):
        AgentStateManager.load_agent_run(
            run.run_id,
            session_id="other-session",
            workspace_id=run.workspace_id,
            principal_id=run.principal_id,
        )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_load_agent_run_rejects_workspace_mismatch(
    mock_session_local,
):
    """
    A run cannot cross workspace boundaries during resume.
    """
    run = make_run()

    record = make_db_record(
        run
    )

    configure_session(
        mock_session_local,
        record=record,
    )

    with pytest.raises(
        PermissionError,
        match="workspace",
    ):
        AgentStateManager.load_agent_run(
            run.run_id,
            session_id=run.session_id,
            workspace_id="other-workspace",
            principal_id=run.principal_id,
        )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_load_agent_run_rejects_principal_mismatch(
    mock_session_local,
):
    """
    A run cannot be resumed by another principal.
    """
    run = make_run()

    record = make_db_record(
        run
    )

    configure_session(
        mock_session_local,
        record=record,
    )

    with pytest.raises(
        PermissionError,
        match="principal",
    ):
        AgentStateManager.load_agent_run(
            run.run_id,
            session_id=run.session_id,
            workspace_id=run.workspace_id,
            principal_id="other-user",
        )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_legacy_record_without_workspace_fails_closed(
    mock_session_local,
):
    """
    A legacy record without tenant scope must never acquire a default
    workspace.
    """
    run = make_run()

    snapshot = run.model_dump(
        mode="json"
    )

    snapshot.pop(
        "workspace_id",
        None,
    )

    record = MagicMock(
        spec=DbAgentRun
    )

    record.id = run.run_id
    record.session_id = run.session_id
    record.principal_id = run.principal_id
    record.role = run.role
    record.input_data = json.dumps(
        snapshot
    )
    record.status = run.status.value
    record.result = None
    record.error = None
    record.created_at = run.created_at
    record.updated_at = run.updated_at

    configure_session(
        mock_session_local,
        record=record,
    )

    restored = AgentStateManager.load_agent_run(
        run.run_id
    )

    assert restored is not None
    assert restored.workspace_id == ""
    assert (
        restored.principal_id
        == run.principal_id
    )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_legacy_record_rejects_authenticated_workspace_resume(
    mock_session_local,
):
    """
    A legacy record with no workspace binding must not resume into any
    authenticated workspace.
    """
    run = make_run()

    snapshot = run.model_dump(
        mode="json"
    )

    snapshot.pop(
        "workspace_id",
        None,
    )

    record = MagicMock(
        spec=DbAgentRun
    )

    record.id = run.run_id
    record.session_id = run.session_id
    record.principal_id = run.principal_id
    record.role = run.role
    record.input_data = json.dumps(
        snapshot
    )
    record.status = run.status.value
    record.result = None
    record.error = None
    record.created_at = run.created_at
    record.updated_at = run.updated_at

    configure_session(
        mock_session_local,
        record=record,
    )

    with pytest.raises(
        PermissionError,
        match="workspace",
    ):
        AgentStateManager.load_agent_run(
            run.run_id,
            session_id=run.session_id,
            workspace_id=run.workspace_id,
            principal_id=run.principal_id,
        )


@patch(
    "app.agent_engine.state.manager.SessionLocal"
)
def test_load_unknown_run_returns_none(
    mock_session_local,
):
    """
    Missing durable runs must produce an explicit cache miss.
    """
    configure_session(
        mock_session_local,
        record=None,
    )

    result = AgentStateManager.load_agent_run(
        "missing-run"
    )

    assert result is None