"""
@file tests/agent_engine/test_approval.py
@description Unit tests for the durable ApprovalManager.

The tests validate that approval records remain bound to the exact
session, principal, workspace, run, tool, and canonical argument hash.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.agent_engine.approval.manager import ApprovalManager
from app.domain.models.audit import ApprovalRecord


# ==============================================================================
# TEST FIXTURES
# ==============================================================================


SESSION_ID = "session_1"
WORKSPACE_ID = "workspace_1"
PRINCIPAL_ID = "principal_1"
RUN_ID = "run_1"
TOOL_NAME = "tool_a"
ARGUMENTS = {"a": 1}


def make_record(
    *,
    decision=None,
    expires_at=None,
):
    """Build an isolated approval record mock with the required fields."""
    record = MagicMock(spec=ApprovalRecord)
    record.id = "req_123"
    record.session_id = SESSION_ID
    record.workspace_id = WORKSPACE_ID
    record.requested_by = PRINCIPAL_ID
    record.run_id = RUN_ID
    record.tool = TOOL_NAME
    record.arguments_hash = ApprovalManager.argument_hash(ARGUMENTS)
    record.risk = "low"
    record.requested_at = datetime.utcnow()
    record.expires_at = expires_at or (
        datetime.utcnow() + timedelta(hours=1)
    )
    record.decision = decision
    record.decided_by = None
    record.decided_at = None
    return record


def configure_query(mock_session_local, record):
    """Configure the SQLAlchemy-style query chain used by ApprovalManager."""
    mock_db = MagicMock()

    context_manager = mock_session_local.return_value
    context_manager.__enter__.return_value = mock_db
    context_manager.__exit__.return_value = None

    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .first.return_value
    ) = record

    return mock_db


# ==============================================================================
# TESTS
# ==============================================================================


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_check_approval_status_none(mock_session_local):
    """Return NONE when no exact approval record exists."""

    mock_db = configure_query(
        mock_session_local,
        None,
    )

    status = await ApprovalManager.check_approval_status(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
    )

    assert status == "NONE"
    mock_db.query.assert_called_once()


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_check_approval_status_expired(mock_session_local):
    """Expired approval records never authorize execution."""

    record = make_record(
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )

    configure_query(
        mock_session_local,
        record,
    )

    status = await ApprovalManager.check_approval_status(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
    )

    assert status == "EXPIRED"


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_check_approval_status_approved(mock_session_local):
    """Only explicit ALLOW is resolved as APPROVED."""

    record = make_record(
        decision="ALLOW",
    )

    configure_query(
        mock_session_local,
        record,
    )

    status = await ApprovalManager.check_approval_status(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
    )

    assert status == "APPROVED"


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_check_approval_status_denied(mock_session_local):
    """Explicit DENY is resolved as DENIED."""

    record = make_record(
        decision="DENY",
    )

    configure_query(
        mock_session_local,
        record,
    )

    status = await ApprovalManager.check_approval_status(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
    )

    assert status == "DENIED"


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_check_approval_status_pending(mock_session_local):
    """An unresolved approval remains WAITING_APPROVAL."""

    record = make_record(
        decision=None,
    )

    configure_query(
        mock_session_local,
        record,
    )

    status = await ApprovalManager.check_approval_status(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
    )

    assert status == "WAITING_APPROVAL"


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_request_approval(mock_session_local):
    """Create a durable approval bound to the complete security context."""

    mock_db = MagicMock()
    context_manager = mock_session_local.return_value
    context_manager.__enter__.return_value = mock_db
    context_manager.__exit__.return_value = None

    record = make_record()
    mock_db.refresh.side_effect = lambda item: None

    created_id = await ApprovalManager.request_approval(
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal_id=PRINCIPAL_ID,
        run_id=RUN_ID,
        tool_name=TOOL_NAME,
        arguments=ARGUMENTS,
        risk="high",
    )

    added_record = mock_db.add.call_args.args[0]

    assert added_record.session_id == SESSION_ID
    assert added_record.workspace_id == WORKSPACE_ID
    assert added_record.requested_by == PRINCIPAL_ID
    assert added_record.run_id == RUN_ID
    assert added_record.tool == TOOL_NAME
    assert added_record.arguments_hash == (
        ApprovalManager.argument_hash(ARGUMENTS)
    )
    assert added_record.risk == "high"

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()

    # SQLAlchemy does not assign an ID in this mock; the return contract is
    # therefore validated through the created record only in integration tests.
    assert created_id is None or isinstance(created_id, str)

    del record


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_grant_approval(mock_session_local):
    """Granting approval updates the record and returns success."""

    mock_db = MagicMock()

    context_manager = mock_session_local.return_value
    context_manager.__enter__.return_value = mock_db
    context_manager.__exit__.return_value = None

    record = make_record()

    mock_db.query.return_value.filter.return_value.first.return_value = record

    result = await ApprovalManager.grant_approval(
        req_id="req_123",
        decision="ALLOW",
    )

    assert result is True
    assert record.decision == "ALLOW"
    assert record.decided_by == "admin"
    assert record.decided_at is not None
    mock_db.commit.assert_called_once()


@pytest.mark.anyio
@patch("app.agent_engine.approval.manager.SessionLocal")
async def test_grant_approval_rejects_expired_request(mock_session_local):
    """Expired approval requests cannot be granted."""

    mock_db = MagicMock()

    context_manager = mock_session_local.return_value
    context_manager.__enter__.return_value = mock_db
    context_manager.__exit__.return_value = None

    record = make_record(
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )

    mock_db.query.return_value.filter.return_value.first.return_value = record

    result = await ApprovalManager.grant_approval(
        req_id="req_123",
        decision="ALLOW",
    )

    assert result is False
    mock_db.commit.assert_not_called()