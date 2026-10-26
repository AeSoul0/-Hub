"""
@file backend/app/agent_engine/catalog.py
@description The models each provider offers, for the role editor of the
Control Plane (F4). Suggestions only: any model name can still be typed, and
the routing is validated when it is saved.

- openrouter: GET https://openrouter.ai/api/v1/models. It includes prices
  (USD per token, turned into USD per 1M tokens like AEHUB_MODEL_PRICES) and
  keeps only the models that can call tools, which the agent needs.
- openai: GET https://api.openai.com/v1/models with the key; no prices.
- local: GET <AEHUB_LOCAL_BASE_URL>/models (Ollama, LM Studio, vLLM).

Answers are cached for CACHE_SECONDS per provider and address. The key is
sent only to its own provider and never returned.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.runtime_config import config_value


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
LOCAL_BASE_URL = "http://localhost:11434/v1"

TIMEOUT_SECONDS = 10.0
CACHE_SECONDS = 600
MAX_MODELS = 1000

# OpenAI lists embeddings, audio and image models too: only these can run
# the agent loop.
OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")

_cache: Dict[Tuple[str, str], Tuple[float, List[Dict[str, Any]]]] = {}
_cache_lock = threading.Lock()


class CatalogUnavailable(RuntimeError):
    pass


def _per_million(value: Any) -> Optional[float]:
    try:
        number = float(value) * 1_000_000
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return round(number, 6)


def _get(url: str, key: Optional[str]) -> Any:
    import httpx

    headers = {"Authorization": f"Bearer {key}"} if key else {}

    try:
        response = httpx.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise CatalogUnavailable(f"{url} is not reachable: {exc.__class__.__name__}") from exc

    if response.status_code != 200:
        raise CatalogUnavailable(f"{url} answered {response.status_code}.")

    try:
        return response.json()
    except ValueError as exc:
        raise CatalogUnavailable(f"{url} did not answer with JSON.") from exc


def _openrouter(payload: Any) -> List[Dict[str, Any]]:
    models = []

    for item in (payload or {}).get("data") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue

        parameters = item.get("supported_parameters")
        if isinstance(parameters, list) and "tools" not in parameters:
            continue

        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        input_price = _per_million(pricing.get("prompt"))
        output_price = _per_million(pricing.get("completion"))

        models.append(
            {
                "id": str(item["id"])[:200],
                "name": str(item.get("name") or item["id"])[:200],
                "context": item.get("context_length") if isinstance(item.get("context_length"), int) else None,
                "price": (
                    {"input": input_price, "output": output_price}
                    if input_price is not None and output_price is not None
                    else None
                ),
            }
        )

    return models


def _plain(payload: Any, prefixes: Tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    models = []

    for item in (payload or {}).get("data") or []:
        model_id = str(item.get("id") or "") if isinstance(item, dict) else ""

        if not model_id or (prefixes and not model_id.startswith(prefixes)):
            continue

        models.append({"id": model_id[:200], "name": model_id[:200], "context": None, "price": None})

    return models


def provider_models(provider: str) -> List[Dict[str, Any]]:
    """
    The models of `provider`, sorted by id. Raises CatalogUnavailable when
    the provider cannot be asked (no key, unreachable, error).
    """
    if provider == "openrouter":
        url, key = OPENROUTER_MODELS_URL, os.getenv("OPENROUTER_API_KEY") or None
    elif provider == "openai":
        key = os.getenv("OPENAI_API_KEY") or None
        if not key:
            raise CatalogUnavailable("OPENAI_API_KEY is not set.")
        url = OPENAI_MODELS_URL
    elif provider == "local":
        base = (config_value("AEHUB_LOCAL_BASE_URL") or LOCAL_BASE_URL).rstrip("/")
        url, key = f"{base}/models", os.getenv("AEHUB_LOCAL_API_KEY") or None
    else:
        raise CatalogUnavailable(f"Unknown provider '{provider}'.")

    cache_key = (provider, url)
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]

    payload = _get(url, key)

    if provider == "openrouter":
        models = _openrouter(payload)
    elif provider == "openai":
        models = _plain(payload, OPENAI_CHAT_PREFIXES)
    else:
        models = _plain(payload)

    models = sorted(models, key=lambda model: model["id"])[:MAX_MODELS]

    with _cache_lock:
        _cache[cache_key] = (now, models)

    return models


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


__all__ = ["CatalogUnavailable", "clear_cache", "provider_models"]
