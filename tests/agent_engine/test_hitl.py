"""
@file tests/agent_engine/test_hitl.py
@description Human-in-the-loop end-to-end tests (roadmap M2 exit, spec 3.4).

A HIGH-risk tool proposed by the model parks the run on a durable approval
request. The run resumes with the same run_id once a Principal of the same
workspace decides:

    task -> function_call (HIGH tool) -> ToolGateway -> WAITING_APPROVAL
         -> POST /api/approvals/{id} -> resume -> tool runs -> ACCEPT

Silence is never consent: an undecided request past its TTL is a DENY, and
an approval only covers the exact arguments it was requested for.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.agent_engine.application import AgentEngine
from app.agent_engine.approval.manager import (
    TIMEOUT_DECIDER,
    ApprovalManager,
)
from app.agent_engine.runtime import AgentRuntime
from app.api import approvals as approvals_api
from app.core.security import Principal, RoleEnum, resolve_principal
from app.domain.models.audit import ApprovalRecord
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


SESSION_ID = "session-hitl"
WORKSPACE_ID = "workspace-hitl"


# ==============================================================================
# TEST DOUBLES
# ==============================================================================


class RecordsSkill(BaseSkill):
    """
    Skill with one HIGH-risk tool that must never run unapproved.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="records",
            description="Destructive record management.",
        )

    @property
    def tools(self):
        def delete_record(record_id: str) -> str:
            self.calls.append({"record_id": record_id})
            return f"deleted {record_id}"

        return [delete_record]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "delete_record": ToolMetadata(
                name="delete_record",
                description="Permanently delete one record.",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                    },
                    "required": ["record_id"],
                    "additionalProperties": False,
                },
            )
        }


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def records_skill(agent_infrastructure) -> RecordsSkill:
    skill = RecordsSkill()
    agent_infrastructure.use_skills(skill)
    return skill


@pytest.fixture
def owner() -> Principal:
    # HIGH tools require EXECUTE_SENSITIVE_TOOL: USER is denied outright.
    return Principal(
        id="admin-owner",
        role=RoleEnum.ADMIN,
        workspace_id=WORKSPACE_ID,
    )


@pytest.fixture
def decider() -> Principal:
    return Principal(
        id="admin-decider",
        role=RoleEnum.ADMIN,
        workspace_id=WORKSPACE_ID,
    )


@pytest.fixture
def make_engine(fake_model):
    """
    Build an AgentEngine whose worker proposes delete_record(r1) first.
    """

    def build(after_tool: List[Any], checker: List[Any]) -> AgentEngine:
        worker = fake_model.adapter(
            [
                fake_model.function_call(
                    "call_del",
                    "delete_record",
                    {"record_id": "r1"},
                ),
                *after_tool,
            ]
        )

        return AgentEngine(
            model_provider=worker,
            checker_provider=fake_model.checker(checker),
            runtime=AgentRuntime(),
        )

    return build


async def start_parked_run(engine: AgentEngine, owner: Principal) -> Dict[str, Any]:
    """
    Run the task until it parks on the approval request.
    """
    result = await engine.run(
        session_id=SESSION_ID,
        task="Delete record r1.",
        principal=owner,
    )

    parked = result["messages"][0].content
    assert parked["status"] == "WAITING_APPROVAL"
    assert parked["run_id"] == result["run_id"]
    assert parked["approval_id"]

    return parked


def run_row(db_session_factory, run_id: str) -> DbAgentRun:
    with db_session_factory() as db:
        return db.query(DbAgentRun).filter(DbAgentRun.id == run_id).one()


def worker_context_of(row: DbAgentRun) -> Dict[str, Any]:
    """
    Durable worker context from the run snapshot.
    """
    return json.loads(row.input_data)["current_state"]["worker_context"]


def approval_row(db_session_factory, approval_id: str) -> ApprovalRecord:
    with db_session_factory() as db:
        return (
            db.query(ApprovalRecord)
            .filter(ApprovalRecord.id == approval_id)
            .one()
        )


async def decide_and_resume(
    engine: AgentEngine,
    approval_id: str,
    decision: str,
    decider: Principal,
) -> Dict[str, Any]:
    """
    Decide through the API route and run the background resume inline.
    """
    with patch.object(approvals_api, "_schedule_resume") as schedule:
        approval = await approvals_api.decide_approval(
            approval_id,
            approvals_api.ApprovalDecision(decision=decision),
            principal=decider,
        )

    schedule.assert_called_once_with(approval)

    with patch.object(
        approvals_api,
        "get_agent_engine",
        return_value=engine,
    ):
        await approvals_api.resume_after_decision(approval)

    return approval


def resumed_payload(published: List[Any]) -> Dict[str, Any]:
    payloads = [
        data
        for _, event_type, data in published
        if event_type == "run.resumed"
    ]
    assert len(payloads) == 1
    return payloads[0]


# ==============================================================================
# HIGH TOOL NEVER RUNS UNAPPROVED
# ==============================================================================


async def test_high_tool_does_not_run_without_approval(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    owner,
):
    engine = make_engine(after_tool=[], checker=[])

    parked = await start_parked_run(engine, owner)

    assert records_skill.calls == []

    row = run_row(db_session_factory, parked["run_id"])
    assert row.status.lower() == "waiting_approval"

    pending = worker_context_of(row)["pending_tool_call"]
    assert pending["tool_name"] == "delete_record"
    assert pending["arguments"] == {"record_id": "r1"}
    assert pending["approval_id"] == parked["approval_id"]

    request = approval_row(db_session_factory, parked["approval_id"])
    assert request.decision is None
    assert request.run_id == parked["run_id"]
    assert request.requested_by == owner.id
    assert request.arguments_hash == ApprovalManager.argument_hash(
        {"record_id": "r1"}
    )

    events = [event_type for _, event_type, _ in agent_infrastructure.published]
    assert "approval.requested" in events

    # Resuming while still undecided keeps the run parked.
    outcome = await engine.resume(
        run_id=parked["run_id"],
        session_id=SESSION_ID,
        principal=owner,
    )
    assert outcome["status"] == "WAITING_APPROVAL"
    assert records_skill.calls == []


# ==============================================================================
# APPROVE -> RESUME -> COMPLETED
# ==============================================================================


async def test_approve_resumes_same_run_to_completion(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    fake_model,
    owner,
    decider,
):
    engine = make_engine(
        after_tool=[fake_model.text("Record r1 deleted.")],
        checker=[fake_model.accept()],
    )

    parked = await start_parked_run(engine, owner)

    pending = await ApprovalManager.list_pending(WORKSPACE_ID)
    assert [item["id"] for item in pending] == [parked["approval_id"]]

    approval = await decide_and_resume(
        engine,
        parked["approval_id"],
        "allow",
        decider,
    )

    assert approval["decision"] == "ALLOW"
    assert approval["decided_by"] == decider.id

    payload = resumed_payload(agent_infrastructure.published)
    assert payload["run_id"] == parked["run_id"]
    assert payload["result"] == "Record r1 deleted."

    # The tool ran exactly once, with the approved arguments.
    assert records_skill.calls == [{"record_id": "r1"}]

    # The resumed turn threads the real call output back to the model.
    worker_requests = engine.model_provider._client.responses.requests
    assert len(worker_requests) == 2
    outputs = [
        item
        for item in worker_requests[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert [item["call_id"] for item in outputs] == ["call_del"]
    assert outputs[0]["output"] == "deleted r1"

    row = run_row(db_session_factory, parked["run_id"])
    assert row.status.lower() == "completed"
    assert worker_context_of(row)["pending_tool_call"] is None

    assert await ApprovalManager.list_pending(WORKSPACE_ID) == []


# ==============================================================================
# DENY AND TIMEOUT
# ==============================================================================


async def test_deny_cancels_run_without_running_tool(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    owner,
    decider,
):
    engine = make_engine(after_tool=[], checker=[])

    parked = await start_parked_run(engine, owner)

    await decide_and_resume(
        engine,
        parked["approval_id"],
        "deny",
        decider,
    )

    payload = resumed_payload(agent_infrastructure.published)
    assert payload["result"] == {
        "status": "DENIED",
        "run_id": parked["run_id"],
    }

    assert records_skill.calls == []

    row = run_row(db_session_factory, parked["run_id"])
    assert row.status.lower() == "cancelled"


async def test_timeout_is_deny(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    owner,
    decider,
):
    engine = make_engine(after_tool=[], checker=[])

    parked = await start_parked_run(engine, owner)

    with db_session_factory() as db:
        request = (
            db.query(ApprovalRecord)
            .filter(ApprovalRecord.id == parked["approval_id"])
            .one()
        )
        request.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    # A late decision is refused: the request is denied by timeout.
    with pytest.raises(HTTPException) as late:
        await approvals_api.decide_approval(
            parked["approval_id"],
            approvals_api.ApprovalDecision(decision="allow"),
            principal=decider,
        )

    assert late.value.status_code == 409

    request = approval_row(db_session_factory, parked["approval_id"])
    assert request.decision == "DENY"
    assert request.decided_by == TIMEOUT_DECIDER

    outcome = await engine.resume(
        run_id=parked["run_id"],
        session_id=SESSION_ID,
        principal=owner,
    )

    assert outcome["status"] == "DENIED"
    assert records_skill.calls == []
    assert run_row(db_session_factory, parked["run_id"]).status.lower() == (
        "cancelled"
    )


# ==============================================================================
# APPROVAL IS BOUND TO THE EXACT ARGUMENTS
# ==============================================================================


async def test_modified_arguments_invalidate_approval(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    owner,
    decider,
):
    engine = make_engine(after_tool=[], checker=[])

    parked = await start_parked_run(engine, owner)

    await ApprovalManager.grant_approval(
        req_id=parked["approval_id"],
        decision="ALLOW",
        decided_by=decider.id,
        workspace_id=WORKSPACE_ID,
    )

    context = {
        "session_id": SESSION_ID,
        "workspace_id": WORKSPACE_ID,
        "principal_id": owner.id,
        "run_id": parked["run_id"],
        "tool_name": "delete_record",
    }

    assert await ApprovalManager.check_approval_status(
        **context,
        arguments={"record_id": "r1"},
    ) == "APPROVED"

    assert await ApprovalManager.check_approval_status(
        **context,
        arguments={"record_id": "r2"},
    ) == "NONE"

    # Tamper with the parked call in durable state after the approval.
    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == parked["run_id"]).one()
        snapshot = json.loads(row.input_data)
        pending = snapshot["current_state"]["worker_context"]["pending_tool_call"]
        pending["arguments"] = {"record_id": "r2"}
        row.input_data = json.dumps(snapshot)
        db.commit()

    outcome = await engine.resume(
        run_id=parked["run_id"],
        session_id=SESSION_ID,
        principal=owner,
    )

    assert outcome["status"] == "DENIED"
    assert records_skill.calls == []


# ==============================================================================
# WORKSPACE ISOLATION
# ==============================================================================


async def test_decider_from_other_workspace_cannot_decide(
    agent_infrastructure,
    records_skill,
    db_session_factory,
    make_engine,
    owner,
):
    engine = make_engine(after_tool=[], checker=[])

    parked = await start_parked_run(engine, owner)

    outsider = Principal(
        id="admin-outsider",
        role=RoleEnum.ADMIN,
        workspace_id="workspace-other",
    )

    assert await ApprovalManager.list_pending(outsider.workspace_id) == []

    with pytest.raises(HTTPException) as missing:
        await approvals_api.decide_approval(
            parked["approval_id"],
            approvals_api.ApprovalDecision(decision="allow"),
            principal=outsider,
        )

    assert missing.value.status_code == 404
    assert approval_row(db_session_factory, parked["approval_id"]).decision is None


# ==============================================================================
# HTTP CONTRACT
# ==============================================================================


def test_approvals_http_contract(
    agent_infrastructure,
    db_session_factory,
    decider,
):
    """
    GET lists the caller's pending requests; POST decides once (409 after).
    """
    with db_session_factory() as db:
        record = ApprovalRecord(
            run_id="run-http",
            session_id=SESSION_ID,
            workspace_id=WORKSPACE_ID,
            tool="delete_record",
            arguments_hash=ApprovalManager.argument_hash({"record_id": "r1"}),
            risk="high",
            requested_by="admin-owner",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(record)
        db.commit()
        approval_id = record.id

    app = FastAPI()
    app.include_router(approvals_api.router)
    app.dependency_overrides[resolve_principal] = lambda: decider
    client = TestClient(app)

    listed = client.get("/api/approvals")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [approval_id]

    with patch.object(approvals_api, "_schedule_resume") as schedule:
        decided = client.post(
            f"/api/approvals/{approval_id}",
            json={"decision": "deny"},
        )
        again = client.post(
            f"/api/approvals/{approval_id}",
            json={"decision": "allow"},
        )

    assert decided.status_code == 200
    assert decided.json()["decision"] == "DENY"
    assert again.status_code == 409
    schedule.assert_called_once()

    assert client.post(
        "/api/approvals/does-not-exist",
        json={"decision": "allow"},
    ).status_code == 404

    assert client.post(
        f"/api/approvals/{approval_id}",
        json={"decision": "maybe"},
    ).status_code == 422

    assert client.get("/api/approvals").json() == []
