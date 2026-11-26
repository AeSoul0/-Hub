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
- GitHub Models (the "local" provider): alone it does every role, the
  Critic with another publisher; with other providers it is each role's last
  fallback; the token is checked first, a refused one is skipped;
- every choice passes ÆHub's own routing check (the Critic shares no model);
- prices only for the Claude models used, and 0 for GitHub Models.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
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

GITHUB = [
    {"id": "openai/gpt-4.1", "rate_limit_tier": "high", "capabilities": ["streaming", "tool-calling"], "supported_output_modalities": ["text"]},
    {"id": "openai/gpt-4.1-mini", "rate_limit_tier": "low", "capabilities": ["tool-calling"]},
    {"id": "meta/llama-4-scout", "rate_limit_tier": "high", "capabilities": ["tool-calling"]},
    {"id": "deepseek/deepseek-v3", "rate_limit_tier": "high", "capabilities": ["tool-calling"]},
    {"id": "openai/o3", "rate_limit_tier": "custom", "capabilities": ["tool-calling"]},
    {"id": "microsoft/phi-4", "rate_limit_tier": "low", "capabilities": []},
    {"id": "openai/text-embedding-3-small", "rate_limit_tier": "embeddings", "capabilities": []},
]


class Calls(list):
    """The calls made to the providers, plus the tokens GitHub Models refuses."""

    refused: set


@pytest.fixture
def providers(monkeypatch):
    seen = Calls()
    seen.refused = set()

    def get(url, headers):
        seen.append((url.split("/")[2], sorted(headers)))
        if "anthropic" in url:
            return CLAUDE
        if "googleapis" in url:
            return GEMINI
        if "models.github.ai" in url:
            return GITHUB
        return FREE

    def post(url, headers, body):
        seen.append((url, headers["Authorization"], body["model"], body["max_tokens"]))
        if headers["Authorization"] in seen.refused:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        return {"choices": []}

    monkeypatch.setattr(models, "_get", get)
    monkeypatch.setattr(models, "_post", post)
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GITHUB_TOKEN",
        "GITHUB_MODELS_TOKEN",
        "AEHUB_LOCAL_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    return seen


def run(capsys, monkeypatch, **keys):
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    assert models.main() == 0
    captured = capsys.readouterr()
    run.err = captured.err
    return json.loads(captured.out)


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


def test_github_models_alone(providers, capsys, monkeypatch):
    out = run(capsys, monkeypatch, GITHUB_TOKEN="test-gh")
    # A larger model plans, a small one does the quick jobs, another publisher checks.
    assert out["roles"] == {
        "architect": ["local:openai/gpt-4.1"],
        "research": ["local:openai/gpt-4.1"],
        "fast_worker": ["local:openai/gpt-4.1-mini", "local:openai/gpt-4.1"],
        "triage": ["local:openai/gpt-4.1-mini"],
        "critic": ["local:deepseek/deepseek-v3"],
    }
    assert out["prices"] == {
        model: {"input": 0.0, "output": 0.0}
        for model in ("deepseek/deepseek-v3", "openai/gpt-4.1", "openai/gpt-4.1-mini")
    }
    # The variable's name, never the token.
    assert out["github_models"] == {"base_url": "https://models.github.ai/inference", "token_variable": "GITHUB_TOKEN"}
    assert "test-gh" not in json.dumps(out)
    # The token was checked with one one-token request.
    assert providers[-1] == ("https://models.github.ai/inference/chat/completions", "Bearer test-gh", "openai/gpt-4.1-mini", 1)
    valid(out["roles"], monkeypatch)


def test_github_models_as_the_last_fallback(providers, capsys, monkeypatch):
    out = run(capsys, monkeypatch, ANTHROPIC_API_KEY="test-a", GITHUB_TOKEN="test-gh")
    assert out["roles"] == {
        "architect": ["anthropic:claude-opus-5-5", "local:openai/gpt-4.1"],
        "research": ["anthropic:claude-opus-5-5", "local:openai/gpt-4.1"],
        "fast_worker": ["anthropic:claude-haiku-5-5", "anthropic:claude-opus-5-5", "local:openai/gpt-4.1-mini", "local:openai/gpt-4.1"],
        "triage": ["anthropic:claude-haiku-5-5", "local:openai/gpt-4.1-mini"],
        "critic": ["anthropic:claude-sonnet-5-5", "local:deepseek/deepseek-v3"],
    }
    valid(out["roles"], monkeypatch)


def test_github_token_refused_or_another_local_server(providers, capsys, monkeypatch):
    # The secret made for it is refused: the codespace's own token is used.
    providers.refused.add("Bearer bad")
    out = run(capsys, monkeypatch, GITHUB_MODELS_TOKEN="bad", GITHUB_TOKEN="test-gh")
    assert out["github_models"]["token_variable"] == "GITHUB_TOKEN"
    assert "GITHUB_MODELS_TOKEN: GitHub Models refused it (401)." in run.err

    # Both refused: no GitHub Models, and nothing else to choose.
    providers.refused.add("Bearer test-gh")
    assert run(capsys, monkeypatch, GITHUB_TOKEN="test-gh") == {"roles": {}, "prices": {}}

    # Another local server configured: GitHub Models is not asked.
    providers.clear()
    providers.refused.clear()
    monkeypatch.setenv("AEHUB_LOCAL_BASE_URL", "http://localhost:11434/v1")
    assert run(capsys, monkeypatch, GITHUB_TOKEN="test-gh") == {"roles": {}, "prices": {}}
    assert providers == []
