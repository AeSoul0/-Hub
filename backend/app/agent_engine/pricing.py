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
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from app.core.runtime_config import config_value


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


def parse_prices(raw: str) -> Dict[str, Tuple[float, float]]:
    """
    Parse AEHUB_MODEL_PRICES. Raises ValueError on anything but a JSON object
    of model -> {"input": USD, "output": USD} with non-negative prices.
    """
    raw = raw.strip()

    if not raw:
        return {}

    try:
        table = json.loads(raw)
        prices = {
            str(model): (float(price["input"]), float(price["output"]))
            for model, price in table.items()
        }
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(
            'Prices must be a JSON object: model -> {"input": USD, "output": USD}.'
        ) from exc

    if any(value < 0 for pair in prices.values() for value in pair):
        raise ValueError("Prices cannot be negative.")

    return prices


def parse_price_pair(raw: str) -> Tuple[float, float]:
    """
    Parse AEHUB_DEFAULT_MODEL_PRICE ("input,output"). Raises ValueError.
    """
    try:
        input_price, output_price = (float(part) for part in raw.split(","))
    except ValueError as exc:
        raise ValueError("The price must be 'input,output' in USD per 1M tokens.") from exc

    if input_price < 0 or output_price < 0:
        raise ValueError("Prices cannot be negative.")

    return input_price, output_price


def _configured_prices() -> Dict[str, Tuple[float, float]]:
    try:
        return parse_prices(config_value("AEHUB_MODEL_PRICES") or "")
    except ValueError:
        logger.error("AEHUB_MODEL_PRICES is not valid JSON pricing; using the fallback price.")
        return {}


def configured_price_models() -> set:
    """
    Models with a configured (not estimated) price.
    """
    return set(_configured_prices())


def _fallback_price() -> Tuple[float, float]:
    raw = (config_value("AEHUB_DEFAULT_MODEL_PRICE") or "").strip()

    if raw:
        try:
            return parse_price_pair(raw)
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
