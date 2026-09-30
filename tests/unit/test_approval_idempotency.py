"""
@file tests/unit/test_approval_idempotency.py
@description Unit tests for durable approval and idempotency services.

The tests mock the shared SQLAlchemy session boundary and verify tenant,
principal, run, and argument isolation without requiring PostgreSQL.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.state.idempotency import IdempotencyManager
from app.domain.models.audit import ApprovalRecord
from app.domain.models.runtime_state import IdempotencyKey


def _mock_session():
    """
    Build a mocked SQLAlchemy session context.
    """
    session = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = session
    context.__exit__.return_value = False
    return context, session


def test_argument_hash_is_deterministic() -> None:
    """
    Equivalent argument dictionaries must produce the same hash.
    """
    first = ApprovalManager.argument_hash(
        {"b": 2, "a": 1}
    )
    second = ApprovalManager.argument_hash(
        {"a": 1, "b": 2}
    )

    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_missing_approval_is_not_approved() -> None:
    """
    No approval record must fail closed.
    """
    context, db = _mock_session()

    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .first.return_value
    ) = None

    with patch(
        "app.agent_engine.approval.manager.SessionLocal",
        return_value=context,
    ):
        status = await ApprovalManager.check_approval_status(
            session_id="session-1",
            workspace_id="workspace-1",
            principal_id="principal-1",
            run_id="run-1",
            tool_name="dangerous_tool",
            arguments={"value": 1},
        )

    assert status == "NONE"


@pytest.mark.asyncio
async def test_approved_execution_requires_exact_context() -> None:
    """
    Approval lookup is bound to the exact session, tenant, principal, run,
    tool, and argument hash.
    """
    context, db = _mock_session()

    record = ApprovalRecord(
        id="approval-1",
        session_id="session-1",
        workspace_id="workspace-1",
        requested_by="principal-1",
        run_id="run-1",
        tool="dangerous_tool",
        arguments_hash=ApprovalManager.argument_hash(
            {"value": 1}
        ),
        risk="high",
        expires_at=datetime.utcnow() + timedelta(hours=1),
        decision="ALLOW",
    )

    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .first.return_value
    ) = record

    with patch(
        "app.agent_engine.approval.manager.SessionLocal",
        return_value=context,
    ):
        status = await ApprovalManager.check_approval_status(
            session_id="session-1",
            workspace_id="workspace-1",
            principal_id="principal-1",
            run_id="run-1",
            tool_name="dangerous_tool",
            arguments={"value": 1},
        )

    assert status == "APPROVED"


@pytest.mark.asyncio
async def test_expired_approval_is_not_authorized() -> None:
    """
    Expired ALLOW records must not authorize execution.
    """
    context, db = _mock_session()

    record = ApprovalRecord(
        id="approval-2",
        session_id="session-1",
        workspace_id="workspace-1",
        requested_by="principal-1",
        run_id="run-1",
        tool="dangerous_tool",
        arguments_hash=ApprovalManager.argument_hash(
            {"value": 1}
        ),
        risk="high",
        expires_at=datetime.utcnow() - timedelta(minutes=1),
        decision="ALLOW",
    )

    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .first.return_value
    ) = record

    with patch(
        "app.agent_engine.approval.manager.SessionLocal",
        return_value=context,
    ):
        status = await ApprovalManager.check_approval_status(
            session_id="session-1",
            workspace_id="workspace-1",
            principal_id="principal-1",
            run_id="run-1",
            tool_name="dangerous_tool",
            arguments={"value": 1},
        )

    assert status == "EXPIRED"


@pytest.mark.asyncio
async def test_idempotency_result_is_persisted() -> None:
    """
    Saving an idempotency result must create a durable DB record.
    """
    context, db = _mock_session()

    db.query.return_value.filter.return_value.first.return_value = None

    with patch(
        "app.agent_engine.state.idempotency.SessionLocal",
        return_value=context,
    ):
        IdempotencyManager.save_result(
            "idem-1",
            {"status": "ok"},
        )

    db.add.assert_called_once()
    db.commit.assert_called_once()

    created = db.add.call_args.args[0]

    assert isinstance(created, IdempotencyKey)
    assert created.key == "idem-1"
    assert created.result == '{"status": "ok"}'


def test_idempotency_expiry_is_a_cache_miss() -> None:
    """
    Expired records must be deleted and treated as absent.
    """
    context, db = _mock_session()

    expired = IdempotencyKey(
        key="idem-expired",
        result='{"status":"ok"}',
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )

    db.query.return_value.filter.return_value.first.return_value = expired

    with patch(
        "app.agent_engine.state.idempotency.SessionLocal",
        return_value=context,
    ):
        result = IdempotencyManager.get_result(
            "idem-expired"
        )

    assert result is None
    db.delete.assert_called_once_with(expired)
    db.commit.assert_called_once()


def test_idempotency_returns_json_result() -> None:
    """
    A valid non-expired record must return its decoded result.
    """
    context, db = _mock_session()

    valid = IdempotencyKey(
        key="idem-valid",
        result='{"status":"ok","value":42}',
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    db.query.return_value.filter.return_value.first.return_value = valid

    with patch(
        "app.agent_engine.state.idempotency.SessionLocal",
        return_value=context,
    ):
        result = IdempotencyManager.get_result(
            "idem-valid"
        )

    assert result == {
        "status": "ok",
        "value": 42,
    }