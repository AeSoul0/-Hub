"""
@file tests/agent_engine/conftest.py
@description Shared end-to-end fixtures for the native agent engine.

The only fake boundaries are the OpenAI client, the Redis event bus and the
TaskManager connection pool. Everything else (AgentEngine, AgentRuntime,
OpenAIAdapter, ToolGateway, ApprovalManager, AgentStateManager, AuditLog)
runs for real against an in-memory database.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.domain.models.audit import ApprovalRecord, AuditChainLink, AuditLog
from app.domain.models.identity import Base
from app.domain.models.memory import MemoryChunk
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.domain.models.runtime_state import MonthlySpend
from app.domain.models.settings import AppSetting
from app.skills.registry import SkillRegistry


# ==============================================================================
# FAKE MODEL
# ==============================================================================


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


def _fake_adapter(scripted: List[Any], model_name: str = "fake-model") -> OpenAIAdapter:
    adapter = OpenAIAdapter(
        model_name=model_name,
        api_key="test-only",
    )
    adapter._client = SimpleNamespace(
        responses=FakeResponses(scripted),
    )
    return adapter


def _usage(usage: Optional[Tuple[int, int]]) -> Any:
    """
    Responses API usage object for (input_tokens, output_tokens).
    """
    if usage is None:
        return None

    return SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1])


def _function_call(
    call_id: str,
    name: str,
    arguments: Dict[str, Any],
    usage: Optional[Tuple[int, int]] = None,
) -> Any:
    return SimpleNamespace(
        id=f"resp_{call_id}",
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id=call_id,
                name=name,
                arguments=json.dumps(arguments),
            )
        ],
        usage=_usage(usage),
    )


def _text(text: str, usage: Optional[Tuple[int, int]] = None) -> Any:
    return SimpleNamespace(
        id="resp_text",
        output_text=text,
        output=[],
        usage=_usage(usage),
    )


def _accept(usage: Optional[Tuple[int, int]] = None) -> Any:
    return _text(json.dumps({"decision": "ACCEPT", "issues": []}), usage=usage)


@pytest.fixture
def fake_model() -> SimpleNamespace:
    """
    Builders for a real OpenAIAdapter backed by scripted responses.
    """
    return SimpleNamespace(
        adapter=_fake_adapter,
        # The Critic must be a different model from the Implementer.
        checker=lambda scripted: _fake_adapter(scripted, model_name="fake-critic"),
        function_call=_function_call,
        text=_text,
        accept=_accept,
    )


# ==============================================================================
# INFRASTRUCTURE
# ==============================================================================


@pytest.fixture
def db_session_factory():
    """
    In-memory database holding run, audit, approval and memory tables.
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
            AuditChainLink.__table__,
            MonthlySpend.__table__,
            ApprovalRecord.__table__,
            MemoryChunk.__table__,
            AppSetting.__table__,
        ],
    )

    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )


@pytest.fixture
def agent_infrastructure(db_session_factory, tmp_path):
    """
    Route persistence to the in-memory database and fake the transports.

    Returns a namespace with:
    - use_skills(*skills): install skills in a fresh SkillRegistry;
    - published: list of (session_id, event_type, data) sent to the bus.
    - workspace_published: the same events also sent to a workspace channel.
    """
    published: List[Any] = []
    workspace_published: List[Any] = []

    async def publish(session_id: str, event_type: str, data: Any, workspace_id: str = "") -> None:
        published.append((session_id, event_type, data))
        if workspace_id:
            workspace_published.append((workspace_id, event_type, data))

    with ExitStack() as stack:
        for target in (
            "app.core.db.SessionLocal",
            "app.agent_engine.state.manager.SessionLocal",
            "app.agent_engine.approval.manager.SessionLocal",
        ):
            stack.enter_context(patch(target, db_session_factory))

        stack.enter_context(
            patch(
                "app.agent_engine.events.FLIGHT_RECORDER_FILE",
                str(tmp_path / "flight_recorder.jsonl"),
            )
        )
        stack.enter_context(
            patch(
                "app.core.event_bus.event_bus.publish",
                AsyncMock(side_effect=publish),
            )
        )

        task_manager = stack.enter_context(
            patch("app.runtime.tool_gateway.TaskManager")
        )
        task_manager.create_task.return_value = SimpleNamespace(id="task-1")

        def use_skills(*skills: Any) -> SkillRegistry:
            registry = SkillRegistry()
            for skill in skills:
                registry.register_skill(skill)
            stack.enter_context(
                patch("app.agent_engine.runtime.skill_registry", registry)
            )
            return registry

        yield SimpleNamespace(
            use_skills=use_skills,
            published=published,
            workspace_published=workspace_published,
        )
