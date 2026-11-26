"""
@file scripts/codespace_models.py
@description The models of each role for a codespace, from the keys it has.

Prints {"roles": AEHUB_MODEL_ROLES, "prices": AEHUB_MODEL_PRICES} as JSON,
plus "github_models": {"base_url", "token_variable"} when GitHub Models is
used (the name of the variable holding the token, never the token)
(roles empty when there is nothing to choose from; prices only for the
Claude models, whose prices are known; the others use ÆHub's fallback price,
which overestimates, until you set them in IMPOSTAZIONI). The model names are read from each provider's own list with your key,
so only models that exist today are chosen:

- Anthropic and Gemini: Claude Opus plans, Gemini Pro researches, Claude
  Haiku and Gemini Flash-Lite do the quick jobs, and the Critic is Gemini
  Flash (another family checks Claude's answers), with Claude Sonnet as its
  fallback. Each role falls back on the other provider.
- Anthropic only: Opus plans and researches, Haiku does the quick jobs,
  Sonnet is the Critic.
- Gemini only: Pro, Flash-Lite for the quick jobs, Flash as the Critic.
- OpenRouter only: its free models that can call tools, the largest first;
  the Critic is a different one.
- GitHub Models (free with a GitHub account, through ÆHub's "local"
  provider, an OpenAI-compatible server): with the codespace's own
  GITHUB_TOKEN, or a token with Models read access saved as the
  GITHUB_MODELS_TOKEN secret. With other providers it is each role's last
  fallback; alone, it does every role, the Critic with another publisher's
  model. Its models cost nothing (price 0), within GitHub's daily limits.

The Critic never shares a model with another role (routing refuses it). The
roles are only a starting point: IMPOSTAZIONI changes them, and what is saved
there wins over this.

Used by scripts/codespace.sh; it never prints or stores a key.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

TIMEOUT = 20
ANTHROPIC = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5", "opus": "claude-opus-5-5"}
# USD per 1M tokens (Anthropic's list prices, November 2026).
ANTHROPIC_PRICES = {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0},
}


def _get(url: str, headers: Dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - fixed https URLs
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310  # nosec B310
        return json.load(response)


def _post(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Any:
    request = urllib.request.Request(  # noqa: S310 - fixed https URLs
        url,
        data=json.dumps(body).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310  # nosec B310
        return json.load(response)


def anthropic_models(key: str) -> Dict[str, str]:
    """sonnet/haiku/opus -> the model id: the known ones if listed, else the newest of the family."""
    payload = _get(
        "https://api.anthropic.com/v1/models?limit=1000",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    listed = [item for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]
    ids = {item["id"] for item in listed}
    chosen: Dict[str, str] = {}
    for family, preferred in ANTHROPIC.items():
        if preferred in ids:
            chosen[family] = preferred
            continue
        newest = sorted(
            (item for item in listed if item["id"].startswith(f"claude-{family}")),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
        if newest:
            chosen[family] = newest[0]["id"]
    return chosen


_GEMINI = re.compile(r"^gemini-(\d+(?:\.\d+)?)-(pro|flash|flash-lite)$")


def gemini_models(key: str) -> Dict[str, str]:
    """pro/flash/flash-lite -> the newest stable model that generates content."""
    payload = _get(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        {"x-goog-api-key": key},
    )
    best: Dict[str, tuple] = {}
    names = set()
    for item in payload.get("models", []):
        name = str(item.get("name", "")).removeprefix("models/")
        if "generateContent" not in item.get("supportedGenerationMethods", []):
            continue
        names.add(name)
        match = _GEMINI.match(name)
        if match:
            version = tuple(int(part) for part in match.group(1).split("."))
            tier = match.group(2)
            if tier not in best or version > best[tier][0]:
                best[tier] = (version, name)
    chosen = {tier: name for tier, (_, name) in best.items()}
    # No stable name for a tier: the "latest" alias, when Google offers it.
    for tier in ("pro", "flash", "flash-lite"):
        alias = f"gemini-{tier}-latest"
        if tier not in chosen and alias in names:
            chosen[tier] = alias
    return chosen


def openrouter_free(key: Optional[str]) -> List[str]:
    """Free models that can call tools, largest context first, then newest."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    payload = _get("https://openrouter.ai/api/v1/models", headers)
    free = [
        item
        for item in payload.get("data", [])
        if str(item.get("id", "")).endswith(":free") and "tools" in (item.get("supported_parameters") or [])
    ]
    free.sort(key=lambda item: (int(item.get("context_length") or 0), int(item.get("created") or 0)), reverse=True)
    return [item["id"] for item in free]


GITHUB_MODELS = "https://models.github.ai/inference"
GITHUB_CATALOG = "https://models.github.ai/catalog/models"
# Tokens tried in order: a secret made for it, then the codespace's own.
GITHUB_TOKENS = ("GITHUB_MODELS_TOKEN", "GITHUB_TOKEN")
# Publishers, the preferred first (the id's prefix, as "openai/gpt-4.1").
PUBLISHERS = ("openai", "deepseek", "meta", "mistral-ai", "xai", "microsoft", "cohere", "ai21-labs")
_SMALL = re.compile(r"mini|nano|small|scout|phi|[^0-9][1-9]b\b", re.IGNORECASE)


def _github_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_models(token: str) -> Dict[str, str]:
    """
    main/quick/critic -> a GitHub Models id that can call tools. Main: a
    larger model (the "high" tier), quick: a small one ("low" tier, more
    requests a day), the Critic: another publisher's model.
    """
    catalog = _get(GITHUB_CATALOG, _github_headers(token))
    usable = [
        item
        for item in (catalog if isinstance(catalog, list) else [])
        if isinstance(item, dict)
        and item.get("id")
        and "tool-calling" in (item.get("capabilities") or [])
        and item.get("rate_limit_tier") in ("low", "high")
        and "text" in (item.get("supported_output_modalities") or ["text"])
    ]

    def publisher(item: Dict[str, Any]) -> str:
        return str(item["id"]).split("/", 1)[0].lower()

    def rank(item: Dict[str, Any]) -> int:
        name = publisher(item)
        return PUBLISHERS.index(name) if name in PUBLISHERS else len(PUBLISHERS)

    def small(item: Dict[str, Any]) -> bool:
        return bool(_SMALL.search(str(item["id"])))

    big = sorted(usable, key=lambda item: (item["rate_limit_tier"] != "high", small(item), rank(item)))
    quick = sorted(usable, key=lambda item: (item["rate_limit_tier"] != "low", not small(item), rank(item)))
    if not big:
        return {}
    chosen = {"main": big[0]["id"]}
    chosen["quick"] = next((item["id"] for item in quick if item["id"] != chosen["main"]), chosen["main"])
    taken = {chosen["main"], chosen["quick"]}
    others = [item for item in sorted(usable, key=rank) if item["id"] not in taken]
    critic = next((item for item in others if publisher(item) != publisher(big[0])), None) or (others[0] if others else None)
    if critic is not None:
        chosen["critic"] = critic["id"]
    return chosen


def github_token() -> Tuple[Optional[str], Dict[str, str], List[str]]:
    """
    (variable, models, notes): the first token that GitHub Models answers,
    checked with a one-token request (one of the day's free requests), and
    the models chosen with it.
    """
    notes: List[str] = []
    for variable in GITHUB_TOKENS:
        token = os.getenv(variable, "").strip()
        if not token:
            continue
        try:
            chosen = github_models(token)
            if not chosen:
                notes.append(f"{variable}: GitHub Models lists no model that can call tools.")
                continue
            _post(
                f"{GITHUB_MODELS}/chat/completions",
                _github_headers(token),
                {"model": chosen["quick"], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1},
            )
            return variable, chosen, notes
        except Exception as exc:  # noqa: BLE001 - try the next token
            code = getattr(exc, "code", None)
            notes.append(f"{variable}: GitHub Models refused it ({code or exc.__class__.__name__}).")
    return None, {}, notes


def roles(
    anthropic: Dict[str, str],
    gemini: Dict[str, str],
    free: List[str],
    github: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    a = {family: f"anthropic:{model}" for family, model in anthropic.items()}
    g = {tier: f"google:{model}" for tier, model in gemini.items()}
    h = {kind: f"local:{model}" for kind, model in (github or {}).items()}

    def chain(*models: Optional[str]) -> List[str]:
        return [model for model in dict.fromkeys(models) if model]

    # GitHub Models, by role: alone it does everything; otherwise each
    # role's last fallback.
    h_roles = (
        {
            "architect": chain(h.get("main")),
            "research": chain(h.get("main")),
            "fast_worker": chain(h.get("quick"), h.get("main")),
            "triage": chain(h.get("quick")),
            "critic": chain(h.get("critic")),
        }
        if h
        else {}
    )

    if a and g:
        config = {
            "architect": chain(a.get("opus"), g.get("pro")),
            "research": chain(g.get("pro"), a.get("opus")),
            "fast_worker": chain(a.get("haiku"), g.get("flash-lite")),
            "triage": chain(g.get("flash-lite"), a.get("haiku")),
            "critic": chain(g.get("flash"), a.get("sonnet")),
        }
    elif a:
        config = {
            "architect": chain(a.get("opus")),
            "research": chain(a.get("opus")),
            "fast_worker": chain(a.get("haiku"), a.get("opus")),
            "triage": chain(a.get("haiku")),
            "critic": chain(a.get("sonnet")),
        }
    elif g:
        config = {
            "architect": chain(g.get("pro")),
            "research": chain(g.get("pro")),
            "fast_worker": chain(g.get("flash-lite"), g.get("pro")),
            "triage": chain(g.get("flash-lite")),
            "critic": chain(g.get("flash")),
        }
    elif len(free) >= 2:
        main, quick, *rest = [f"openrouter:{model}" for model in free]
        critic = rest[0] if rest else None
        if critic is None:
            # Only two free models: the Critic takes the second, the quick roles the first.
            quick, critic = main, quick
        config = {
            "architect": [main],
            "research": [main],
            "fast_worker": chain(quick, main),
            "triage": [quick],
            "critic": [critic],
        }
    elif h_roles:
        config = {role: [] for role in h_roles}
    else:
        return {}

    for role, models in h_roles.items():
        config[role] = chain(*config[role], *models)

    # The Critic never shares a model with the others: drop any overlap from its chain.
    others = {model for role, models in config.items() if role != "critic" for model in models}
    config["critic"] = [model for model in config["critic"] if model not in others]
    if not config["critic"] or any(not models for models in config.values()):
        return {}
    return config


def main() -> int:
    anthropic: Dict[str, str] = {}
    gemini: Dict[str, str] = {}
    free: List[str] = []
    notes: List[str] = []

    for name, reader, target in (
        ("ANTHROPIC_API_KEY", anthropic_models, anthropic),
        ("GEMINI_API_KEY", gemini_models, gemini),
    ):
        key = os.getenv(name, "").strip()
        if key:
            try:
                target.update(reader(key))
            except Exception as exc:  # noqa: BLE001 - one provider down must not stop the others
                notes.append(f"{name}: the model list could not be read ({exc.__class__.__name__}).")

    if not anthropic and not gemini and os.getenv("OPENROUTER_API_KEY", "").strip():
        try:
            free = openrouter_free(os.getenv("OPENROUTER_API_KEY", "").strip())
        except Exception as exc:  # noqa: BLE001
            notes.append(f"OPENROUTER_API_KEY: the model list could not be read ({exc.__class__.__name__}).")

    # GitHub Models, unless another local server is configured.
    github: Dict[str, str] = {}
    variable = None
    if not os.getenv("AEHUB_LOCAL_BASE_URL", "").strip():
        variable, github, github_notes = github_token()
        notes.extend(github_notes)

    for note in notes:
        print(note, file=sys.stderr)
    config = roles(anthropic, gemini, free, github)
    used = {model.split(":", 1)[1] for models in config.values() for model in models}
    prices = {model: price for model, price in ANTHROPIC_PRICES.items() if model in used}
    local = {model.split(":", 1)[1] for models in config.values() for model in models if model.startswith("local:")}
    # Free on GitHub Models (within its daily limits).
    prices.update({model: {"input": 0.0, "output": 0.0} for model in sorted(local)})
    result: Dict[str, Any] = {"roles": config, "prices": prices}
    if local and variable:
        result["github_models"] = {"base_url": GITHUB_MODELS, "token_variable": variable}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
