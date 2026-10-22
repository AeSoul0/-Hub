"""
@file tests/agent_engine/test_routing_failover.py
@description Multi-model routing, failover and Critic independence (M5).

Exit test: provider A fails in the middle of a run; the run finishes on
provider B (a Chat Completions endpoint, so the durable observations are
replayed in the other API format) and no tool is executed twice.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.agent_engine.adapters.chat_completions_adapter import ChatCompletionsAdapter
from app.agent_engine.application import AgentEngine
from app.agent_engine.errors import MaxTurnsReachedError
from app.agent_engine.routing import (
    CircuitBreaker,
    ModelRouter,
    ModelTarget,
    ProviderUnavailableError,
    Role,
    RoutingConfig,
    RoutingConfigError,
    FailoverProvider,
    check_routing_at_startup,
    reset_breakers,
    triage_role,
)
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


SESSION_ID = "session-m5"
WORKSPACE_ID = "workspace-m5"


# ==============================================================================
# TEST DOUBLES
# ==============================================================================


class PingSkill(BaseSkill):
    def __init__(self) -> None:
        self.calls: List[str] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="pinger", description="Ping tool.")

    @property
    def tools(self):
        def ping(target: str) -> str:
            self.calls.append(target)
            return f"pong {target}"

        return [ping]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "ping": ToolMetadata(
                name="ping",
                description="Ping a target.",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"],
                    "additionalProperties": False,
                },
            )
        }


class FlakyResponses:
    """
    Responses endpoint that answers from a script, then fails.
    """

    def __init__(self, scripted: List[Any]) -> None:
        self.scripted = list(scripted)
        self.requests: List[Dict[str, Any]] = []

    async def create(self, **request: Any) -> Any:
        self.requests.append(request)
        if not self.scripted:
            raise ConnectionError("provider A is down")
        return self.scripted.pop(0)


class FakeChatCompletions:
    def __init__(self, scripted: List[Any]) -> None:
        self.scripted = list(scripted)
        self.requests: List[Dict[str, Any]] = []

    async def create(self, **request: Any) -> Any:
        self.requests.append(request)
        if not self.scripted:
            raise AssertionError("Unexpected extra chat call.")
        return self.scripted.pop(0)


def chat_text(text: str, usage=(1, 1)) -> Any:
    return SimpleNamespace(
        id="chat_1",
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
    )


def chat_adapter(model: str, scripted: List[Any]) -> ChatCompletionsAdapter:
    adapter = ChatCompletionsAdapter(
        model_name=model,
        base_url="http://chat.invalid/v1",
        api_key="test-only",
        provider="openrouter",
    )
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions(scripted)))
    return adapter


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture(autouse=True)
def clean_breakers():
    reset_breakers()
    yield
    reset_breakers()


@pytest.fixture
def pinger(agent_infrastructure) -> PingSkill:
    skill = PingSkill()
    agent_infrastructure.use_skills(skill)
    return skill


@pytest.fixture
def user() -> Principal:
    return Principal(id="user-m5", role=RoleEnum.USER, workspace_id=WORKSPACE_ID)


def routing(**chains: List[str]) -> RoutingConfig:
    """
    Config where every role not given uses a dedicated unused model.
    """
    return RoutingConfig(
        chains={
            role: tuple(
                ModelTarget.parse(entry)
                for entry in chains.get(role.value, [f"local:unused-{role.value}"])
            )
            for role in Role
        }
    )


# ==============================================================================
# EXIT: FAILOVER MID-RUN WITHOUT RE-RUNNING TOOLS
# ==============================================================================


async def test_failover_mid_run_finishes_on_b_without_repeating_tools(
    pinger, user, fake_model, db_session_factory
):
    provider_a = fake_model.adapter(
        [fake_model.function_call("call_1", "ping", {"target": "a"}, usage=(2, 1))],
        model_name="model-a",
    )
    flaky = FlakyResponses(provider_a._client.responses.scripted)
    provider_a._client = SimpleNamespace(responses=flaky)

    provider_b = chat_adapter("model-b", [chat_text("Pinged a.")])
    critic = fake_model.checker([fake_model.accept()])

    providers = {
        "openai:model-a": provider_a,
        "openrouter:model-b": provider_b,
        "local:fake-critic": critic,
    }

    router = ModelRouter(
        routing(
            architect=["openai:model-a", "openrouter:model-b"],
            critic=["local:fake-critic"],
        ),
        factory=lambda target: providers.get(target.label)
        or fake_model.adapter([], model_name=target.model),
    )

    engine = AgentEngine(router=router, runtime=AgentRuntime())

    result = await engine.run(
        session_id=SESSION_ID,
        task="Implement a ping of host a.",
        principal=user,
    )

    assert result["messages"][0].content == "Pinged a."

    # The tool ran exactly once, on A's proposal; B did not re-run it.
    assert pinger.calls == ["a"]
    assert len(flaky.requests) == 2

    # B received the executed call and its output, converted to Chat format.
    [chat_request] = provider_b._client.chat.completions.requests
    roles = [message["role"] for message in chat_request["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert chat_request["messages"][2]["tool_calls"][0]["id"] == "call_1"
    assert chat_request["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "pong a",
    }
    assert chat_request["tools"][0]["function"]["name"] == "ping"

    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == result["run_id"]).one()
        usage = json.loads(row.input_data)["usage"]

    assert [call["model"] for call in usage["calls"]] == ["model-a", "model-b", "fake-critic"]
    assert [call["role"] for call in usage["calls"]] == ["architect", "architect", "critic"]
    assert usage["tool_calls"] == 1


async def test_run_fails_closed_when_every_provider_is_down(pinger, user, fake_model):
    down = FlakyResponses([])
    provider_a = fake_model.adapter([], model_name="model-a")
    provider_a._client = SimpleNamespace(responses=down)

    router = ModelRouter(
        routing(architect=["openai:model-a"], critic=["local:fake-critic"]),
        factory=lambda target: provider_a
        if target.model == "model-a"
        else fake_model.adapter([], model_name=target.model),
    )

    engine = AgentEngine(router=router, runtime=AgentRuntime())

    with pytest.raises(MaxTurnsReachedError):
        await engine.run(session_id=SESSION_ID, task="Implement a ping.", principal=user)

    assert pinger.calls == []


# ==============================================================================
# CIRCUIT BREAKER
# ==============================================================================


def test_breaker_opens_after_threshold_and_half_opens_after_cooldown():
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown=30, clock=lambda: now[0])

    breaker.record_failure()
    assert breaker.allow()

    breaker.record_failure()
    assert breaker.state == "open"
    assert not breaker.allow()

    now[0] = 31
    assert breaker.state == "half_open"
    assert breaker.allow()

    # A failed trial re-opens for a full cooldown.
    breaker.record_failure()
    assert breaker.state == "open"

    now[0] = 62
    breaker.record_success()
    assert breaker.state == "closed"


async def test_open_breaker_skips_the_provider(fake_model, monkeypatch):
    monkeypatch.setenv("AEHUB_BREAKER_THRESHOLD", "1")

    down = FlakyResponses([])
    provider_a = fake_model.adapter([], model_name="model-a")
    provider_a._client = SimpleNamespace(responses=down)
    provider_b = chat_adapter("model-b", [chat_text("one"), chat_text("two")])

    failover = FailoverProvider(
        Role.FAST_WORKER,
        [("openai:model-a", provider_a), ("openrouter:model-b", provider_b)],
    )

    first = await failover.generate({"task": {"description": "x"}})
    second = await failover.generate({"task": {"description": "x"}})

    assert first["output"] == "one" and first["failed_over"] is True
    assert second["output"] == "two"
    # The open breaker kept the second call away from provider A.
    assert len(down.requests) == 1


async def test_failover_raises_when_the_chain_is_exhausted(fake_model):
    down = FlakyResponses([])
    provider_a = fake_model.adapter([], model_name="model-a")
    provider_a._client = SimpleNamespace(responses=down)

    failover = FailoverProvider(Role.TRIAGE, [("openai:model-a", provider_a)])

    with pytest.raises(ProviderUnavailableError, match="openai:model-a"):
        await failover.generate({"task": {"description": "x"}})


# ==============================================================================
# CRITIC != IMPLEMENTER
# ==============================================================================


def test_router_rejects_a_critic_shared_with_an_implementer():
    with pytest.raises(RoutingConfigError, match="Critic and fast_worker share"):
        ModelRouter(
            routing(
                fast_worker=["openrouter:same-model"],
                critic=["openrouter:other", "openai:same-model"],
            )
        )


def test_default_config_without_a_critic_model_is_rejected(monkeypatch):
    monkeypatch.delenv("AEHUB_MODEL_ROLES", raising=False)
    monkeypatch.delenv("AEHUB_CHECKER_MODEL", raising=False)

    with pytest.raises(RoutingConfigError):
        AgentEngine()

    assert "Critic" in check_routing_at_startup()


def test_injected_providers_must_differ(fake_model):
    with pytest.raises(RoutingConfigError, match="same model"):
        AgentEngine(
            model_provider=fake_model.adapter([]),
            checker_provider=fake_model.adapter([]),
        )


def test_routing_config_from_env(monkeypatch):
    monkeypatch.setenv(
        "AEHUB_MODEL_ROLES",
        json.dumps(
            {
                "architect": ["openrouter:arch-1", "openai:arch-2"],
                "critic": "local:critic-1",
            }
        ),
    )
    monkeypatch.setenv("OPENAI_MODEL", "default-model")

    config = RoutingConfig.from_env()

    assert [target.label for target in config.chain(Role.ARCHITECT)] == [
        "openrouter:arch-1",
        "openai:arch-2",
    ]
    assert [target.label for target in config.chain(Role.CRITIC)] == ["local:critic-1"]
    assert [target.label for target in config.chain(Role.TRIAGE)] == ["openai:default-model"]


@pytest.mark.parametrize(
    "raw, message",
    [
        ("not json", "not valid JSON"),
        (json.dumps({"boss": ["openai:x"]}), "Unknown roles"),
        (json.dumps({"critic": ["ftp:x"]}), "Invalid model target"),
        (json.dumps({"critic": []}), "non-empty list"),
    ],
)
def test_invalid_routing_config_is_rejected(monkeypatch, raw, message):
    monkeypatch.setenv("AEHUB_MODEL_ROLES", raw)

    with pytest.raises(RoutingConfigError, match=message):
        RoutingConfig.from_env()


# ==============================================================================
# TRIAGE
# ==============================================================================


@pytest.mark.parametrize(
    "task, role",
    [
        ("Refactor the auth module.", Role.ARCHITECT),
        ("Implementa la sincronizzazione con Notion.", Role.ARCHITECT),
        ("Analizza perché i test sono lenti.", Role.RESEARCH),
        ("Compare SQLite and Postgres for local-first apps.", Role.RESEARCH),
        ("Write unit tests for the parser.", Role.FAST_WORKER),
        ("Converti questo CSV in JSON.", Role.FAST_WORKER),
        ("What time is it in Tokyo?", Role.TRIAGE),
        ("Show me the latest news.", Role.TRIAGE),
        ("x" * 2000, Role.ARCHITECT),
        ("y " * 400, Role.FAST_WORKER),
    ],
)
def test_triage_routes_by_task(task, role):
    assert triage_role(task) is role


def test_triage_can_be_forced(monkeypatch):
    monkeypatch.setenv("AEHUB_FORCE_ROLE", "research")
    assert triage_role("What time is it?") is Role.RESEARCH


async def test_engine_routes_simple_tasks_to_the_triage_chain(pinger, user, fake_model):
    triage = fake_model.adapter([fake_model.text("Noon.")], model_name="cheap-model")
    critic = fake_model.checker([fake_model.accept()])
    architect = fake_model.adapter([], model_name="big-model")

    providers = {
        "local:cheap-model": triage,
        "local:fake-critic": critic,
        "openrouter:big-model": architect,
    }

    router = ModelRouter(
        routing(
            triage=["local:cheap-model"],
            architect=["openrouter:big-model"],
            critic=["local:fake-critic"],
        ),
        factory=lambda target: providers.get(target.label)
        or fake_model.adapter([], model_name=target.model),
    )

    engine = AgentEngine(router=router, runtime=AgentRuntime())
    result = await engine.run(session_id=SESSION_ID, task="What time is it?", principal=user)

    assert result["messages"][0].content == "Noon."
    assert len(triage._client.responses.requests) == 1
    assert architect._client.responses.requests == []
