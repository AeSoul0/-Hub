"""
@file tests/agent_engine/test_e2e_loop.py
@description End-to-end agent loop with a fake model provider (roadmap M1 exit).

The only fake boundary is the OpenAI client. Everything between it and the
database is real: AgentEngine -> AgentRuntime -> OpenAIAdapter (worker) ->
ToolGateway -> registered skill tool -> OpenAIAdapter (checker) -> durable
AgentRun and AuditLog rows.

Flow under test:
    task -> function_call (LOW tool) -> ToolGateway -> observation
         -> final answer -> Checker ACCEPT -> AgentRun + audit persisted
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.application import AgentEngine
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.domain.models.audit import AuditLog
from app.domain.models.identity import Base
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata
from app.skills.registry import SkillRegistry


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


class FakeResponses:
    """
    Fake `client.responses` endpoint returning scripted responses.
    """

    def __init__(self, scripted: List[Any]) -> None:
        self.scripted = list(scripted)
        self.requests: List[Dict[str, Any]] = []

    async def create(self, **request: Any) -> Any:
        self.requests.append(request)

        if not self.scripted:
            raise AssertionError("Unexpected extra model call.")

        return self.scripted.pop(0)


def fake_adapter(scripted: List[Any]) -> OpenAIAdapter:
    """
    Build a real OpenAIAdapter whose HTTP client is replaced by a fake.
    """
    adapter = OpenAIAdapter(
        model_name="fake-model",
        api_key="test-only",
    )
    adapter._client = SimpleNamespace(
        responses=FakeResponses(scripted),
    )
    return adapter


def function_call_response(call_id: str, name: str, arguments: Dict[str, Any]) -> Any:
    return SimpleNamespace(
        id="resp_tool",
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id=call_id,
                name=name,
                arguments=json.dumps(arguments),
            )
        ],
    )


def text_response(text: str) -> Any:
    return SimpleNamespace(
        id="resp_text",
        output_text=text,
        output=[],
    )


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def db_session_factory():
    """
    In-memory database holding the durable run and audit tables.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine,
        tables=[
            DbAgentRun.__table__,
            AuditLog.__table__,
        ],
    )

    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )


@pytest.fixture
def capitals_skill() -> CapitalsSkill:
    return CapitalsSkill()


@pytest.fixture
def isolated_infrastructure(db_session_factory, capitals_skill, tmp_path):
    """
    Route persistence to the in-memory database and install the test skill.

    TaskManager uses a separate raw connection pool and is out of scope for
    this test, so only its two calls are stubbed.
    """
    registry = SkillRegistry()
    registry.register_skill(capitals_skill)

    with (
        patch("app.core.db.SessionLocal", db_session_factory),
        patch(
            "app.agent_engine.state.manager.SessionLocal",
            db_session_factory,
        ),
        patch("app.agent_engine.runtime.skill_registry", registry),
        patch(
            "app.agent_engine.events.FLIGHT_RECORDER_FILE",
            str(tmp_path / "flight_recorder.jsonl"),
        ),
        patch("app.runtime.tool_gateway.TaskManager") as task_manager,
    ):
        task_manager.create_task.return_value = SimpleNamespace(id="task-1")
        yield


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
):
    """
    A LOW tool proposed by the model is executed through the ToolGateway,
    its output is threaded back to the model, the Checker accepts, and both
    the AgentRun and the audit record are persisted.
    """
    worker = fake_adapter(
        [
            function_call_response(
                "call_1",
                "lookup_capital",
                {"country": "Italy"},
            ),
            text_response("The capital of Italy is Rome."),
        ]
    )

    checker = fake_adapter(
        [
            text_response(
                json.dumps(
                    {
                        "decision": "ACCEPT",
                        "issues": [],
                    }
                )
            ),
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

        audit_rows = db.query(AuditLog).filter(AuditLog.run_id == run_id).all()

    assert len(audit_rows) == 1
    assert audit_rows[0].tool_name == "lookup_capital"
    assert audit_rows[0].tool_call_id == "call_1"
    assert audit_rows[0].decision == "ALLOW"
    assert audit_rows[0].success is True
    assert audit_rows[0].principal_id == principal.id
    assert audit_rows[0].workspace_id == principal.workspace_id


async def test_run_stops_at_total_tool_call_cap(
    isolated_infrastructure,
    capitals_skill,
    principal,
):
    """
    A model that keeps calling tools is stopped by the per-run cap instead
    of looping until max_turns.
    """
    from app.agent_engine.errors import MaxTurnsReachedError

    worker = fake_adapter(
        [
            function_call_response(
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
            checker=fake_adapter([]),
            max_total_tool_calls=3,
            run_id="run-cap",
            session_id="session-cap",
            workspace_id=principal.workspace_id,
            principal=principal,
        )

    assert len(capitals_skill.calls) == 3
