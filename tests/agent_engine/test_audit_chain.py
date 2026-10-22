"""
@file tests/agent_engine/test_audit_chain.py
@description Tamper-evident and fail-closed audit (roadmap M3).

- every audit row is hash-chained, and editing or deleting a row breaks
  verification from that row on;
- the ToolGateway never runs a tool whose audit record cannot be written.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent_engine.models import ToolSpec
from app.core.security import Principal, RoleEnum
from app.domain.models.audit import AuditChainLink, AuditLog
from app.runtime.audit_chain import (
    GENESIS_HASH,
    append_audit_record,
    verify_audit_chain,
)
from app.runtime.tool_gateway import ToolGateway, ToolInvocation


def _append(db, n: int) -> list:
    return [
        append_audit_record(
            db,
            session_id="s1",
            principal_id="p1",
            workspace_id="w1",
            tool_name=f"tool_{i}",
            success=True,
            decision="ALLOW",
        )
        for i in range(n)
    ]


def test_records_are_chained_from_genesis(db_session_factory):
    with db_session_factory() as db:
        ids = _append(db, 3)

        links = db.query(AuditChainLink).order_by(AuditChainLink.seq).all()

        assert [link.audit_id for link in links] == ids
        assert links[0].prev_hash == GENESIS_HASH
        assert links[1].prev_hash == links[0].record_hash
        assert links[2].prev_hash == links[1].record_hash

        result = verify_audit_chain(db)

    assert result.valid is True
    assert result.checked == 3


def test_modified_row_breaks_the_chain(db_session_factory):
    with db_session_factory() as db:
        ids = _append(db, 3)

        row = db.query(AuditLog).filter(AuditLog.id == ids[1]).one()
        row.decision = "DENY"
        db.commit()

        result = verify_audit_chain(db)

    assert result.valid is False
    assert result.broken_at_seq == 2
    assert result.reason == "audit row modified"


def test_deleted_row_breaks_the_chain(db_session_factory):
    with db_session_factory() as db:
        ids = _append(db, 3)

        db.query(AuditLog).filter(AuditLog.id == ids[0]).delete()
        db.commit()

        result = verify_audit_chain(db)

    assert result.valid is False
    assert result.broken_at_seq == 1
    assert result.reason == "audit row deleted"


def test_deleted_link_breaks_the_chain(db_session_factory):
    with db_session_factory() as db:
        _append(db, 3)

        db.query(AuditChainLink).filter(AuditChainLink.seq == 2).delete()
        db.commit()

        result = verify_audit_chain(db)

    assert result.valid is False
    assert result.broken_at_seq == 2


# ==============================================================================
# FAIL-CLOSED GATEWAY
# ==============================================================================


def _invocation() -> ToolInvocation:
    spec = ToolSpec(
        name="write_note",
        version="1.0.0",
        description="Write a note.",
        input_schema={},
        output_schema={},
        risk_level="LOW",
        permissions=[],
        network_access=False,
        filesystem_access=False,
        max_runtime=10,
        max_output=1000,
        max_cost=0.0,
        idempotent=False,
        requires_approval=False,
        sandbox_profile="default",
        audit_policy="standard",
    )

    return ToolInvocation(
        tool_name="write_note",
        arguments={"text": "hello"},
        principal=Principal(id="u1", role=RoleEnum.USER, workspace_id="w1"),
        session_id="s1",
        spec=spec,
        tool_call_id="call_1",
        run_id="run_1",
    )


async def test_gateway_blocks_tool_when_audit_is_unavailable():
    calls = []

    async def executor(**kwargs):
        calls.append(kwargs)
        return "written"

    def broken_session():
        raise RuntimeError("database is down")

    with (
        patch("app.core.db.SessionLocal", broken_session),
        patch("app.runtime.tool_gateway.TaskManager") as task_manager,
    ):
        result = await ToolGateway.execute(_invocation(), executor)

    assert calls == []
    assert result.success is False
    assert "Audit log unavailable" in result.error
    task_manager.create_task.assert_not_called()


async def test_gateway_records_intent_before_execution(db_session_factory):
    seen_rows = []

    async def executor(**kwargs):
        # The intent row is already durable when the side effect starts.
        with db_session_factory() as db:
            seen_rows.extend(row.decision for row in db.query(AuditLog).all())
        return "written"

    with (
        patch("app.core.db.SessionLocal", db_session_factory),
        patch("app.runtime.tool_gateway.TaskManager") as task_manager,
    ):
        task_manager.create_task.return_value.id = "task-1"
        result = await ToolGateway.execute(_invocation(), executor)

    assert result.success is True
    assert seen_rows == ["EXECUTING"]

    with db_session_factory() as db:
        assert verify_audit_chain(db).checked == 2


async def test_gateway_redacts_secrets_from_output_and_audit(db_session_factory):
    secret = "ghp_" + "Z" * 40

    async def executor(**kwargs):
        return f"config token={secret}"

    with (
        patch("app.core.db.SessionLocal", db_session_factory),
        patch("app.runtime.tool_gateway.TaskManager") as task_manager,
    ):
        task_manager.create_task.return_value.id = "task-1"
        result = await ToolGateway.execute(_invocation(), executor)

    assert secret not in result.output
    assert "[REDACTED:github_token]" in result.output

    with db_session_factory() as db:
        stored = [row.execution_result or "" for row in db.query(AuditLog).all()]

    assert all(secret not in value for value in stored)
