"""
@file tests/unit/test_codespace_models.py
@description scripts/codespace_models.py: the models of each role in a
codespace, from the providers' own model lists (faked here, no network).

- Anthropic and Gemini: Claude Opus plans, Gemini researches and checks
  (Claude Sonnet as the Critic's fallback); each role falls back on the
  other provider;
- only one provider, or only OpenRouter's free models with tools;
- the newest stable Gemini of each tier, the "latest" alias when there is
  none; the newest Claude of a family when the known id is not listed;
- every choice passes ÆHub's own routing check (the Critic shares no model);
- prices only for the Claude models used.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.agent_engine.routing import RoutingConfig, validate_critic_independence

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "codespace_models.py"
spec = importlib.util.spec_from_file_location("codespace_models", SCRIPT)
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

CLAUDE = {"data": [{"id": "claude-sonnet-5-5"}, {"id": "claude-haiku-5-5"}, {"id": "claude-opus-5-5"}, {"id": "claude-opus-5"}]}
GEMINI = {
    "models": [
        {"name": "models/gemini-3.5-pro", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.7-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.9-flash-preview", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]},
    ]
}
FREE = {
    "data": [
        {"id": "small/model:free", "context_length": 32000, "supported_parameters": ["tools"]},
        {"id": "big/model:free", "context_length": 262144, "supported_parameters": ["tools", "temperature"]},
        {"id": "mid/model:free", "context_length": 131072, "supported_parameters": ["tools"]},
        {"id": "notools/model:free", "context_length": 999999, "supported_parameters": []},
        {"id": "paid/model", "context_length": 999999, "supported_parameters": ["tools"]},
    ]
}


@pytest.fixture
def providers(monkeypatch):
    seen = []

    def get(url, headers):
        seen.append((url.split("/")[2], sorted(headers)))
        if "anthropic" in url:
            return CLAUDE
        if "googleapis" in url:
            return GEMINI
        return FREE

    monkeypatch.setattr(models, "_get", get)
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return seen


def run(capsys, monkeypatch, **keys):
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    assert models.main() == 0
    return json.loads(capsys.readouterr().out)


def valid(roles, monkeypatch):
    monkeypatch.setenv("AEHUB_MODEL_ROLES", json.dumps(roles))
    validate_critic_independence(RoutingConfig.from_env())


def test_claude_and_gemini(providers, capsys, monkeypatch):
    out = run(capsys, monkeypatch, ANTHROPIC_API_KEY="test-a", GEMINI_API_KEY="test-g")
    assert out["roles"] == {
        "architect": ["anthropic:claude-opus-5-5", "google:gemini-3.5-pro"],
        "research": ["google:gemini-3.5-pro", "anthropic:claude-opus-5-5"],
        "fast_worker": ["anthropic:claude-haiku-5-5", "google:gemini-3.5-flash-lite"],
        "triage": ["google:gemini-3.5-flash-lite", "anthropic:claude-haiku-5-5"],
        "critic": ["google:gemini-3.8-flash", "anthropic:claude-sonnet-5-5"],
    }
    assert set(out["prices"]) == {"claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"}
    valid(out["roles"], monkeypatch)
    # Each key goes only to its own provider; OpenRouter is not asked.
    assert providers == [("api.anthropic.com", ["anthropic-version", "x-api-key"]), ("generativelanguage.googleapis.com", ["x-goog-api-key"])]


def test_one_provider(providers, capsys, monkeypatch):
    claude = run(capsys, monkeypatch, ANTHROPIC_API_KEY="test-a")["roles"]
    assert claude == {
        "architect": ["anthropic:claude-opus-5-5"],
        "research": ["anthropic:claude-opus-5-5"],
        "fast_worker": ["anthropic:claude-haiku-5-5", "anthropic:claude-opus-5-5"],
        "triage": ["anthropic:claude-haiku-5-5"],
        "critic": ["anthropic:claude-sonnet-5-5"],
    }
    valid(claude, monkeypatch)

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    gemini = run(capsys, monkeypatch, GEMINI_API_KEY="test-g")
    assert gemini["roles"]["architect"] == ["google:gemini-3.5-pro"]
    assert gemini["roles"]["critic"] == ["google:gemini-3.8-flash"]
    assert gemini["prices"] == {}
    valid(gemini["roles"], monkeypatch)


def test_openrouter_free_models_with_tools(providers, capsys, monkeypatch):
    out = run(capsys, monkeypatch, OPENROUTER_API_KEY="test-o")["roles"]
    assert out == {
        "architect": ["openrouter:big/model:free"],
        "research": ["openrouter:big/model:free"],
        "fast_worker": ["openrouter:mid/model:free", "openrouter:big/model:free"],
        "triage": ["openrouter:mid/model:free"],
        "critic": ["openrouter:small/model:free"],
    }
    valid(out, monkeypatch)


def test_aliases_newest_family_and_nothing(providers, capsys, monkeypatch):
    monkeypatch.setattr(models, "_get", lambda url, headers: {"data": [{"id": "claude-sonnet-6", "created_at": "2027"}, {"id": "claude-sonnet-5-0", "created_at": "2026"}]} if "anthropic" in url else {"models": [{"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]}]})
    assert models.anthropic_models("k") == {"sonnet": "claude-sonnet-6"}
    assert models.gemini_models("k") == {"flash": "gemini-flash-latest"}

    # No key at all: no roles.
    assert run(capsys, monkeypatch) == {"roles": {}, "prices": {}}

    # A provider that fails is reported, not fatal.
    def down(url, headers):
        raise OSError("down")

    monkeypatch.setattr(models, "_get", down)
    assert run(capsys, monkeypatch, ANTHROPIC_API_KEY="test-a") == {"roles": {}, "prices": {}}
