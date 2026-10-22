"""
@file backend/app/agent_engine/pricing.py
@description Model usage normalization and cost calculation.

Prices are USD per 1M tokens and come from configuration, because provider
prices change and must not be guessed in code:

    AEHUB_MODEL_PRICES='{"gpt-5.5": {"input": 1.25, "output": 10.0}}'

A model missing from the table is priced with AEHUB_DEFAULT_MODEL_PRICE
("input,output", deliberately high by default) and the usage is flagged as
estimated, so a misconfiguration overstates spend instead of hiding it.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


logger = logging.getLogger(__name__)

# Conservative fallback (USD per 1M input / output tokens).
FALLBACK_PRICE: Tuple[float, float] = (15.0, 60.0)


@dataclass(frozen=True)
class ModelUsage:
    """
    Token usage and cost of one model call.
    """

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "estimated": self.estimated,
        }


def _configured_prices() -> Dict[str, Tuple[float, float]]:
    raw = os.getenv("AEHUB_MODEL_PRICES", "").strip()

    if not raw:
        return {}

    try:
        table = json.loads(raw)
        return {
            str(model): (float(price["input"]), float(price["output"]))
            for model, price in table.items()
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        logger.error("AEHUB_MODEL_PRICES is not valid JSON pricing; using the fallback price.")
        return {}


def _fallback_price() -> Tuple[float, float]:
    raw = os.getenv("AEHUB_DEFAULT_MODEL_PRICE", "").strip()

    if raw:
        try:
            input_price, output_price = (float(part) for part in raw.split(","))
            return input_price, output_price
        except ValueError:
            logger.error("AEHUB_DEFAULT_MODEL_PRICE must be 'input,output'.")

    return FALLBACK_PRICE


def price_for(model: str) -> Tuple[float, float, bool]:
    """
    Return (input price, output price, estimated) for a model.
    """
    prices = _configured_prices()

    if model in prices:
        return (*prices[model], False)

    input_price, output_price = _fallback_price()
    return input_price, output_price, True


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Tuple[float, bool]:
    input_price, output_price, estimated = price_for(model)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 8), estimated


def _read(source: Any, *names: str) -> Optional[int]:
    for name in names:
        value = (
            source.get(name)
            if isinstance(source, dict)
            else getattr(source, name, None)
        )

        if isinstance(value, (int, float)):
            return int(value)

    return None


def usage_from_response(model: str, raw_usage: Any) -> ModelUsage:
    """
    Normalize a provider usage object (Responses API input/output tokens or
    Chat Completions prompt/completion tokens) and price it.
    """
    if raw_usage is None:
        return ModelUsage(model=model)

    input_tokens = _read(raw_usage, "input_tokens", "prompt_tokens") or 0
    output_tokens = _read(raw_usage, "output_tokens", "completion_tokens") or 0
    cost, estimated = compute_cost(model, input_tokens, output_tokens)

    return ModelUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        estimated=estimated,
    )


__all__ = [
    "FALLBACK_PRICE",
    "ModelUsage",
    "compute_cost",
    "price_for",
    "usage_from_response",
]
