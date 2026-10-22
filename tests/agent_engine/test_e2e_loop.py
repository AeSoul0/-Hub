"""
@file tests/agent_engine/test_e2e_loop.py
@description End-to-end agent loop with a fake model provider (roadmap M1 exit).

Shared fixtures live in conftest.py. The only fake boundary on the model
side is the OpenAI client; everything between it and the database is real: AgentEngine -> AgentRuntime -> OpenAIAdapter (worker) ->
ToolGateway -> registered skill tool -> OpenAIAdapter (checker) -> durable
AgentRun and AuditLog rows.

Flow under test:
    task -> function_call (LOW tool) -> ToolGateway -> observation
         -> final answer -> Checker ACCEPT -> AgentRun + audit persisted
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app.agent_engine.application import AgentEngine
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.domain.models.audit import AuditLog
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.runtime.audit_chain import verify_audit_chain
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


# ==============================================================================
# TEST DOUBLES
# ==============================================================================


class CapitalsSkill(BaseSkill):
    """
    Minimal LOW-risk skill with one deterministic tool.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="capitals",
            description="Country capital lookup.",
        )

    @property
    def tools(self):
        def lookup_capital(country: str) -> str:
            self.calls.append({"country": country})
            return {"Italy": "Rome"}.get(country, "unknown")

        return [lookup_capital]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "lookup_capital": ToolMetadata(
                name="lookup_capital",
                description="Return the capital city of a country.",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "country": {"type": "string"},
                    },
                    "required": ["country"],
                    "additionalProperties": False,
                },
            )
        }


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def capitals_skill() -> CapitalsSkill:
    return CapitalsSkill()


@pytest.fixture
def isolated_infrastructure(agent_infrastructure, capitals_skill):
    agent_infrastructure.use_skills(capitals_skill)
    return agent_infrastructure


@pytest.fixture
def principal() -> Principal:
    return Principal(
        id="user-e2e",
        role=RoleEnum.USER,
        workspace_id="workspace-e2e",
    )


# ==============================================================================
# END-TO-END LOOP
# ==============================================================================


async def test_task_tool_observation_accept_is_persisted(
    isolated_infrastructure,
    capitals_skill,
    db_session_factory,
    principal,
    fake_model,
):
    """
    A LOW tool proposed by the model is executed through the ToolGateway,
    its output is threaded back to the model, the Checker accepts, and both
    the AgentRun and the audit record are persisted.
    """
    worker = fake_model.adapter(
        [
            fake_model.function_call(
                "call_1",
                "lookup_capital",
                {"country": "Italy"},
            ),
            fake_model.text("The capital of Italy is Rome."),
        ]
    )

    checker = fake_model.checker(
        [
            fake_model.accept(),
        ]
    )

    engine = AgentEngine(
        model_provider=worker,
        checker_provider=checker,
        runtime=AgentRuntime(),
    )

    result = await engine.run(
        session_id="session-e2e",
        task="What is the capital of Italy?",
        principal=principal,
    )

    run_id = result["run_id"]
    assert result["messages"][0].content == "The capital of Italy is Rome."

    # The registered tool schema reaches the model.
    worker_requests = worker._client.responses.requests
    assert len(worker_requests) == 2

    exposed = {tool["name"]: tool for tool in worker_requests[0]["tools"]}
    assert exposed["lookup_capital"]["type"] == "function"
    assert exposed["lookup_capital"]["parameters"]["required"] == ["country"]

    # The tool really ran, once, with the model's arguments.
    assert capitals_skill.calls == [{"country": "Italy"}]

    # The second turn replays the function call before its output.
    second_input = worker_requests[1]["input"]
    call_items = [
        item
        for item in second_input
        if item.get("type") in {"function_call", "function_call_output"}
    ]
    assert [item["type"] for item in call_items] == [
        "function_call",
        "function_call_output",
    ]
    assert call_items[0]["call_id"] == call_items[1]["call_id"] == "call_1"
    assert call_items[0]["name"] == "lookup_capital"
    assert json.loads(call_items[0]["arguments"]) == {"country": "Italy"}
    assert call_items[1]["output"] == "Rome"

    # The checker receives its own system prompt, not the adapter default.
    checker_request = checker._client.responses.requests[0]
    assert "independent security and correctness checker" in (
        checker_request["instructions"]
    )

    with db_session_factory() as db:
        run_row = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).one()
        assert run_row.status.lower() == "completed"
        assert "Rome" in run_row.result

        audit_rows = (
            db.query(AuditLog)
            .filter(AuditLog.run_id == run_id)
            .order_by(AuditLog.timestamp)
            .all()
        )

        chain = verify_audit_chain(db)

    # Fail-closed audit: the intent is recorded before the tool runs, the
    # outcome after it; both rows are hash-chained.
    assert [row.decision for row in audit_rows] == ["EXECUTING", "ALLOW"]
    assert chain.valid is True
    assert chain.checked == 2

    outcome = audit_rows[1]
    assert outcome.tool_name == "lookup_capital"
    assert outcome.tool_call_id == "call_1"
    assert outcome.success is True
    assert outcome.principal_id == principal.id
    assert outcome.workspace_id == principal.workspace_id


async def test_run_stops_at_total_tool_call_cap(
    isolated_infrastructure,
    capitals_skill,
    principal,
    fake_model,
):
    """
    A model that keeps calling tools is stopped by the per-run cap instead
    of looping until max_turns.
    """
    from app.agent_engine.errors import MaxTurnsReachedError

    worker = fake_model.adapter(
        [
            fake_model.function_call(
                f"call_{index}",
                "lookup_capital",
                {"country": "Italy"},
            )
            for index in range(10)
        ]
    )

    runtime = AgentRuntime()

    with pytest.raises(MaxTurnsReachedError):
        await runtime.execute_task(
            task={"description": "Loop forever."},
            orchestrator=None,
            worker=worker,
            checker=fake_model.checker([]),
            max_total_tool_calls=3,
            run_id="run-cap",
            session_id="session-cap",
            workspace_id=principal.workspace_id,
            principal=principal,
        )

    assert len(capitals_skill.calls) == 3
