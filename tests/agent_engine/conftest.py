"""
@file tests/agent_engine/conftest.py
@description Shared end-to-end fixtures for the native agent engine.

The only fake boundaries are the OpenAI endpoint and the Redis event bus.
Everything else (AgentEngine, AgentRuntime, PydanticAIAdapter and Pydantic AI
itself, ToolGateway, ApprovalManager, AgentStateManager, AuditLog) runs for
real against an in-memory database.

The fake endpoint sits where the network would be (P1, ADR-032): a real
`AsyncOpenAI` client whose `responses.create` records the request Pydantic
AI built and answers with a real SDK `Response`.
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

from openai import AsyncOpenAI
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from app.agent_engine.adapters.pydantic_ai_adapter import PydanticAIAdapter
from app.domain.models.audit import ApprovalRecord, AuditChainLink, AuditLog
from app.domain.models.documents import DocumentFile
from app.domain.models.identity import Base
from app.domain.models.memory import MemoryChunk
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.domain.models.runtime_state import MonthlySpend
from app.domain.models.settings import AppSetting
from app.domain.models.skills import ImportedSkill
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

        return as_response(self.scripted.pop(0))


FAKE_BASE_URL = "http://openai.invalid/v1"


def as_response(scripted: Any) -> Any:
    """
    A scripted answer as the SDK's `Response`. Some test modules still script
    answers in the plain shape (id, output_text, output, usage) the engine
    read before Pydantic AI (P1); they keep working unchanged.
    """
    if isinstance(scripted, (Response, BaseException)) or not hasattr(scripted, "output"):
        return scripted

    output: List[Any] = []

    for item in getattr(scripted, "output", None) or []:
        if getattr(item, "type", None) == "function_call":
            output.append(
                ResponseFunctionToolCall(
                    type="function_call",
                    call_id=item.call_id,
                    name=item.name,
                    arguments=item.arguments,
                )
            )

    text = getattr(scripted, "output_text", "") or ""

    if text or not output:
        output.insert(
            0,
            ResponseOutputMessage(
                id="msg_text",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
            ),
        )

    raw_usage = getattr(scripted, "usage", None)
    usage = None if raw_usage is None else (raw_usage.input_tokens, raw_usage.output_tokens)

    return _response(getattr(scripted, "id", "resp_scripted"), output, usage)


def fake_openai_client(responses: Any) -> AsyncOpenAI:
    """
    A real AsyncOpenAI (Pydantic AI reads its address and options) whose
    Responses endpoint is `responses`. Nothing reaches the network.
    """
    client = AsyncOpenAI(api_key="test-only", base_url=FAKE_BASE_URL, max_retries=0)
    client.responses = responses
    return client


def _fake_adapter(scripted: List[Any], model_name: str = "fake-model") -> PydanticAIAdapter:
    return PydanticAIAdapter(
        model_name=model_name,
        provider="openai",
        api_key="test-only",
        client=fake_openai_client(FakeResponses(scripted)),
    )


def _usage(usage: Optional[Tuple[int, int]]) -> Optional[ResponseUsage]:
    """
    Responses API usage object for (input_tokens, output_tokens).
    """
    if usage is None:
        return None

    return ResponseUsage(
        input_tokens=usage[0],
        output_tokens=usage[1],
        total_tokens=usage[0] + usage[1],
        input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )


def _response(response_id: str, output: List[Any], usage: Optional[Tuple[int, int]]) -> Response:
    return Response(
        id=response_id,
        created_at=0,
        model="fake",
        object="response",
        output=output,
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
        usage=_usage(usage),
    )


def _function_call(
    call_id: str,
    name: str,
    arguments: Dict[str, Any],
    usage: Optional[Tuple[int, int]] = None,
) -> Response:
    return _response(
        f"resp_{call_id}",
        [
            ResponseFunctionToolCall(
                type="function_call",
                call_id=call_id,
                name=name,
                arguments=json.dumps(arguments),
            )
        ],
        usage,
    )


def _text(text: str, usage: Optional[Tuple[int, int]] = None) -> Response:
    return _response(
        "resp_text",
        [
            ResponseOutputMessage(
                id="msg_text",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
            )
        ],
        usage,
    )


def _accept(usage: Optional[Tuple[int, int]] = None) -> Any:
    return _text(json.dumps({"decision": "ACCEPT", "issues": []}), usage=usage)


@pytest.fixture
def fake_model() -> SimpleNamespace:
    """
    Builders for a real PydanticAIAdapter backed by scripted responses.
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
            DocumentFile.__table__,
            ImportedSkill.__table__,
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
