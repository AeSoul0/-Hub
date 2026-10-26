"""
@file tests/agent_engine/test_settings_engine.py
@description F4: models, keys and limits from the Control Plane.

- the new settings (forced role, local server, approval window, circuit
  breaker, context budget) are checked and reach the engine without a
  restart;
- the settings view shows each role's chain and each provider's key state;
- the provider catalog: OpenRouter with prices per 1M tokens and only the
  models that call tools, OpenAI only with its key, the local server at its
  configured address; errors become 503.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_engine import catalog
from app.agent_engine.adapters.chat_completions_adapter import ChatCompletionsAdapter
from app.agent_engine.approval.manager import approval_ttl
from app.agent_engine.context import ContextBudget
from app.agent_engine.routing import Role, breaker_for, reset_breakers, triage_role
from app.api import settings as settings_api
from app.core.runtime_config import replace_stored
from app.core.security import Principal, resolve_principal
from app.core.settings_service import (
    SettingsValidationError,
    provider_view,
    role_view,
    validate_changes,
)
from app.domain.models.identity import RoleEnum


ADMIN = Principal(id="admin-owner", role=RoleEnum.ADMIN, workspace_id="workspace-1")


class FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return self._body


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in (
        "OPENAI_MODEL",
        "AEHUB_CHECKER_MODEL",
        "AEHUB_MODEL_ROLES",
        "AEHUB_FORCE_ROLE",
        "AEHUB_LOCAL_BASE_URL",
        "AEHUB_LOCAL_API_KEY",
        "AEHUB_APPROVAL_TTL_SECONDS",
        "AEHUB_BREAKER_THRESHOLD",
        "AEHUB_BREAKER_COOLDOWN_SECONDS",
        "AEHUB_CONTEXT_BUDGET",
        "AEHUB_SNAPSHOT_EVERY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    replace_stored({})
    reset_breakers()
    catalog.clear_cache()
    yield
    replace_stored({})
    reset_breakers()
    catalog.clear_cache()


# ==============================================================================
# VALIDATION
# ==============================================================================


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AEHUB_FORCE_ROLE", "critic"),
        ("AEHUB_LOCAL_BASE_URL", "file:///etc/passwd"),
        ("AEHUB_LOCAL_BASE_URL", "javascript:alert(1)"),
        ("AEHUB_LOCAL_BASE_URL", "http://host/a b"),
        ("AEHUB_APPROVAL_TTL_SECONDS", "5"),
        ("AEHUB_APPROVAL_TTL_SECONDS", "100000"),
        ("AEHUB_BREAKER_THRESHOLD", "0"),
        ("AEHUB_BREAKER_COOLDOWN_SECONDS", "0"),
        ("AEHUB_CONTEXT_BUDGET", "500"),
        ("AEHUB_SNAPSHOT_EVERY", "30"),
    ],
)
def test_out_of_range_engine_settings_are_refused(name, value):
    with pytest.raises(SettingsValidationError) as error:
        validate_changes({name: value})

    assert name in error.value.errors


def test_valid_engine_settings_pass(monkeypatch):
    # A valid routing around them: the Critic differs from the Worker.
    monkeypatch.setenv("AEHUB_CHECKER_MODEL", "gpt-5.5-critic")
    changes = {
        "AEHUB_FORCE_ROLE": "research",
        "AEHUB_LOCAL_BASE_URL": "http://192.168.1.20:1234/v1",
        "AEHUB_APPROVAL_TTL_SECONDS": "600",
        "AEHUB_BREAKER_THRESHOLD": "2",
        "AEHUB_BREAKER_COOLDOWN_SECONDS": "30",
        "AEHUB_CONTEXT_BUDGET": "64000",
        "AEHUB_SNAPSHOT_EVERY": "12",
    }

    assert validate_changes(changes) == changes


# ==============================================================================
# THE ENGINE READS THEM WITHOUT A RESTART
# ==============================================================================


def test_engine_settings_apply_without_a_restart():
    assert triage_role("ciao") is Role.TRIAGE
    assert approval_ttl() == timedelta(seconds=300)
    assert ContextBudget.from_env().total == 88_000
    assert breaker_for("openai:a").threshold == 3
    assert ChatCompletionsAdapter.local("llama")._base_url == "http://localhost:11434/v1"

    replace_stored(
        {
            "AEHUB_FORCE_ROLE": "research",
            "AEHUB_APPROVAL_TTL_SECONDS": "900",
            "AEHUB_CONTEXT_BUDGET": "64000",
            "AEHUB_SNAPSHOT_EVERY": "12",
            "AEHUB_BREAKER_THRESHOLD": "1",
            "AEHUB_BREAKER_COOLDOWN_SECONDS": "5",
            "AEHUB_LOCAL_BASE_URL": "http://127.0.0.1:1234/v1",
        }
    )
    # Saving settings resets the breakers (settings_service.rebuild_engine).
    reset_breakers()

    assert triage_role("ciao") is Role.RESEARCH
    assert approval_ttl() == timedelta(seconds=900)
    budget = ContextBudget.from_env()
    assert (budget.total, budget.snapshot_every) == (64_000, 12)
    breaker = breaker_for("openai:a")
    assert (breaker.threshold, breaker.cooldown) == (1, 5.0)
    assert ChatCompletionsAdapter.local("llama")._base_url == "http://127.0.0.1:1234/v1"


def test_role_and_provider_views(monkeypatch):
    replace_stored(
        {
            "OPENAI_MODEL": "gpt-5.5",
            "AEHUB_MODEL_ROLES": '{"critic": ["openrouter:anthropic/claude-sonnet-5.5"], '
            '"triage": ["local:llama3.3", "openai:gpt-5.5-mini"]}',
        }
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-not-real")

    roles = role_view()
    assert roles["critic"] == {"chain": ["openrouter:anthropic/claude-sonnet-5.5"], "custom": True}
    assert roles["triage"] == {"chain": ["local:llama3.3", "openai:gpt-5.5-mini"], "custom": True}
    assert roles["architect"] == {"chain": ["openai:gpt-5.5"], "custom": False}

    providers = provider_view()
    assert providers["openrouter"]["key"] is True
    assert providers["openai"]["key"] is False
    assert providers["local"] == {"key": False, "needs_key": False, "base_url": "http://localhost:11434/v1"}


# ==============================================================================
# PROVIDER CATALOG
# ==============================================================================


def client() -> TestClient:
    app = FastAPI()
    app.include_router(settings_api.router)
    app.dependency_overrides[resolve_principal] = lambda: ADMIN
    return TestClient(app)


def test_openrouter_catalog_keeps_tool_models_with_prices(monkeypatch):
    calls: List[Dict[str, Any]] = []

    def get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "anthropic/claude-sonnet-5.5",
                        "name": "Claude Sonnet 5.5",
                        "context_length": 200000,
                        "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                        "supported_parameters": ["tools", "temperature"],
                    },
                    {
                        "id": "some/image-model",
                        "name": "No tools",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "supported_parameters": ["temperature"],
                    },
                    {"id": "meta/free", "pricing": {"prompt": "abc"}, "supported_parameters": ["tools"]},
                ]
            },
        )

    monkeypatch.setattr("httpx.get", get)

    models = client().get("/api/settings/provider-models/openrouter").json()["models"]

    assert models == [
        {
            "id": "anthropic/claude-sonnet-5.5",
            "name": "Claude Sonnet 5.5",
            "context": 200000,
            "price": {"input": 3.0, "output": 15.0},
        },
        {"id": "meta/free", "name": "meta/free", "context": None, "price": None},
    ]
    assert calls[0]["url"] == "https://openrouter.ai/api/v1/models"
    assert calls[0]["headers"] == {}

    # Cached: a second look does not ask again.
    client().get("/api/settings/provider-models/openrouter")
    assert len(calls) == 1


def test_openai_needs_its_key_and_lists_chat_models(monkeypatch):
    response = client().get("/api/settings/provider-models/openai")
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]

    seen: Dict[str, Any] = {}

    def get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(200, {"data": [{"id": "gpt-5.5"}, {"id": "text-embedding-3-large"}, {"id": "o4-mini"}]})

    monkeypatch.setattr("httpx.get", get)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")

    ids = [model["id"] for model in client().get("/api/settings/provider-models/openai").json()["models"]]
    assert ids == ["gpt-5.5", "o4-mini"]
    assert seen["headers"] == {"Authorization": "Bearer sk-test-not-real"}


def test_local_catalog_uses_the_configured_server(monkeypatch):
    seen: List[str] = []

    def get(url, **kwargs):
        seen.append(url)
        return FakeResponse(500, None)

    monkeypatch.setattr("httpx.get", get)
    replace_stored({"AEHUB_LOCAL_BASE_URL": "http://127.0.0.1:1234/v1/"})

    response = client().get("/api/settings/provider-models/local")

    assert response.status_code == 503
    assert seen == ["http://127.0.0.1:1234/v1/models"]
    assert client().get("/api/settings/provider-models/anthropic").status_code == 422
