"""
@file backend/app/agent_engine/routing.py
@description Multi-model routing (spec 4.1, roadmap M5).

Roles are fixed, the models behind them are chosen by the user:

    AEHUB_MODEL_ROLES='{
        "architect":   ["openrouter:<model>", "openai:<model>"],
        "research":    ["openrouter:<model>"],
        "critic":      ["openrouter:<model>"],
        "fast_worker": ["openrouter:<model>"],
        "triage":      ["openrouter:<model>", "local:<model>"]
    }'

Each role is an ordered chain "provider:model": the first entry is the
primary, the others are fallbacks. Providers: "openai" (Responses API),
"openrouter" and "local" (OpenAI-compatible Chat Completions, e.g. Ollama).
A role left out uses the default chain: OPENAI_MODEL on "openai" (the
critic uses AEHUB_CHECKER_MODEL when set).

- triage_role(): deterministic, free routing of a task to a role, so simple
  tasks run on the cheap models (no model call involved).
- FailoverProvider: tries the chain in order behind per-target circuit
  breakers. The runtime rebuilds the model input from durable observations
  on every turn, so a switch mid-run never repeats an executed tool.
- validate_critic_independence(): the Critic must never share a model with
  an Implementer role (fail closed).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agent_engine.adapters.base import ModelProvider
from app.core.runtime_config import config_value


logger = logging.getLogger(__name__)


class Role(str, Enum):
    ARCHITECT = "architect"
    RESEARCH = "research"
    CRITIC = "critic"
    FAST_WORKER = "fast_worker"
    TRIAGE = "triage"


IMPLEMENTER_ROLES = (
    Role.ARCHITECT,
    Role.RESEARCH,
    Role.FAST_WORKER,
    Role.TRIAGE,
)

PROVIDERS = ("openai", "openrouter", "local")


class RoutingConfigError(ValueError):
    """
    Raised for an invalid or unsafe model routing configuration.
    """


class ProviderUnavailableError(RuntimeError):
    """
    Raised when every provider in a role chain failed or is circuit-open.
    """


# ==============================================================================
# CONFIGURATION
# ==============================================================================


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    @classmethod
    def parse(cls, raw: str) -> "ModelTarget":
        provider, separator, model = str(raw).partition(":")
        provider = provider.strip().lower()
        model = model.strip()

        if not separator or not model or provider not in PROVIDERS:
            raise RoutingConfigError(
                f"Invalid model target '{raw}': expected 'provider:model' "
                f"with provider in {', '.join(PROVIDERS)}."
            )

        return cls(provider=provider, model=model)


def _default_chain(role: Role) -> List[ModelTarget]:
    model = config_value("OPENAI_MODEL") or "gpt-5.5"

    if role is Role.CRITIC:
        model = config_value("AEHUB_CHECKER_MODEL") or model

    return [ModelTarget("openai", model)]


@dataclass(frozen=True)
class RoutingConfig:
    chains: Dict[Role, Tuple[ModelTarget, ...]]

    @classmethod
    def from_env(cls) -> "RoutingConfig":
        raw = (config_value("AEHUB_MODEL_ROLES") or "").strip()
        configured: Dict[str, Any] = {}

        if raw:
            try:
                configured = json.loads(raw)
            except ValueError as exc:
                raise RoutingConfigError("AEHUB_MODEL_ROLES is not valid JSON.") from exc

            if not isinstance(configured, dict):
                raise RoutingConfigError("AEHUB_MODEL_ROLES must be a JSON object.")

            unknown = set(configured) - {role.value for role in Role}
            if unknown:
                raise RoutingConfigError(
                    f"Unknown roles in AEHUB_MODEL_ROLES: {', '.join(sorted(unknown))}."
                )

        chains: Dict[Role, Tuple[ModelTarget, ...]] = {}

        for role in Role:
            entries = configured.get(role.value)

            if entries is None:
                chains[role] = tuple(_default_chain(role))
                continue

            if isinstance(entries, str):
                entries = [entries]

            if not isinstance(entries, list) or not entries:
                raise RoutingConfigError(
                    f"Role '{role.value}' needs a non-empty list of 'provider:model'."
                )

            chains[role] = tuple(ModelTarget.parse(entry) for entry in entries)

        return cls(chains=chains)

    def chain(self, role: Role) -> Tuple[ModelTarget, ...]:
        return self.chains[role]


def validate_critic_independence(config: RoutingConfig) -> None:
    """
    Spec 4.1, "doppio controllo": the model that implements never reviews
    itself. No model of the critic chain may appear in an implementer chain.
    """
    critic_models = {target.model for target in config.chain(Role.CRITIC)}

    for role in IMPLEMENTER_ROLES:
        shared = critic_models & {target.model for target in config.chain(role)}

        if shared:
            raise RoutingConfigError(
                f"Critic and {role.value} share model(s) {', '.join(sorted(shared))}: "
                "the Critic must be independent of every Implementer. Configure "
                "AEHUB_MODEL_ROLES (or AEHUB_CHECKER_MODEL) with a different model."
            )


def ensure_distinct_models(implementer: Any, critic: Any) -> None:
    """
    Same rule for explicitly injected providers.
    """
    implementer_models = set(getattr(implementer, "model_names", None) or [getattr(implementer, "model_name", None)])
    critic_models = set(getattr(critic, "model_names", None) or [getattr(critic, "model_name", None)])
    shared = (implementer_models & critic_models) - {None}

    if shared:
        raise RoutingConfigError(
            f"Implementer and Critic use the same model ({', '.join(sorted(shared))})."
        )


# ==============================================================================
# TRIAGE
# ==============================================================================


def _hints(*stems: str) -> "re.Pattern[str]":
    # Word starts only: "test" matches "tests" but not "latest".
    return re.compile(r"\b(?:" + "|".join(re.escape(stem) for stem in stems) + ")")


_RESEARCH_HINTS = _hints(
    "research", "ricerca", "analy", "analizz", "analisi", "compar",
    "confront", "investigat", "approfond", "why", "perché", "perche",
)
_ARCHITECT_HINTS = _hints(
    "architect", "architettur", "refactor", "design", "progett",
    "pianific", "implement", "migrat", "migra", "debug", "codebase",
    "modul",
)
_FAST_WORKER_HINTS = _hints(
    "test", "doc", "json", "pars", "estra", "extract", "boilerplate",
    "format", "conver", "script",
)

# Short tasks without other hints go to the triage (cheapest) models.
TRIAGE_MAX_CHARS = 280
ARCHITECT_MIN_CHARS = 1500


def triage_role(task: str) -> Role:
    """
    Pick the role for a task from its text, without a model call.

    The order matters: architecture/coding hints win over research, which
    wins over repetitive work; short plain requests go to triage; anything
    long and unclassified goes to the architect.
    """
    forced = (config_value("AEHUB_FORCE_ROLE") or "").strip().lower()
    if forced:
        try:
            return Role(forced)
        except ValueError:
            logger.error("AEHUB_FORCE_ROLE '%s' is not a role; using triage.", forced)

    text = task.lower()

    if _ARCHITECT_HINTS.search(text):
        return Role.ARCHITECT

    if _RESEARCH_HINTS.search(text):
        return Role.RESEARCH

    if _FAST_WORKER_HINTS.search(text):
        return Role.FAST_WORKER

    if len(task) <= TRIAGE_MAX_CHARS:
        return Role.TRIAGE

    if len(task) >= ARCHITECT_MIN_CHARS:
        return Role.ARCHITECT

    return Role.FAST_WORKER


# ==============================================================================
# CIRCUIT BREAKER AND FAILOVER
# ==============================================================================


class CircuitBreaker:
    """
    Opens after `threshold` consecutive failures; after `cooldown` seconds
    one trial call is let through (half-open).
    """

    def __init__(
        self,
        threshold: int = 3,
        cooldown: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self.failures = 0
        self.opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self._clock() - self.opened_at >= self.cooldown:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.threshold or self.opened_at is not None:
                # A failed half-open trial re-opens for a full cooldown.
                self.opened_at = self._clock()


_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(label: str) -> CircuitBreaker:
    """
    Process-wide breaker per provider target, shared across runs.
    """
    with _breakers_lock:
        if label not in _breakers:
            _breakers[label] = CircuitBreaker(
                threshold=int(config_value("AEHUB_BREAKER_THRESHOLD") or "3"),
                cooldown=float(config_value("AEHUB_BREAKER_COOLDOWN_SECONDS") or "60"),
            )
        return _breakers[label]


def reset_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()


class FailoverProvider(ModelProvider):
    """
    Try each provider of a role chain in order.

    A provider error or timeout records a breaker failure and moves on to
    the next target; the first success is returned. Cancellation (kill
    switch) is never swallowed.
    """

    def __init__(
        self,
        role: Role,
        providers: List[Tuple[str, ModelProvider]],
    ) -> None:
        if not providers:
            raise RoutingConfigError(f"Role '{role.value}' has no provider.")

        super().__init__(model_name=providers[0][1].model_name)
        self.role = role
        self.providers = providers

    @property
    def model_names(self) -> List[str]:
        return [provider.model_name for _, provider in self.providers]

    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []

        for label, provider in self.providers:
            breaker = breaker_for(label)

            if not breaker.allow():
                errors.append(f"{label}: circuit open")
                continue

            try:
                result = await provider.generate(context)
            except Exception as exc:
                breaker.record_failure()
                errors.append(f"{label}: {type(exc).__name__}")
                logger.warning(
                    "Provider %s failed for role %s (%s); trying the next one.",
                    label,
                    self.role.value,
                    type(exc).__name__,
                )
                continue

            breaker.record_success()

            if isinstance(result, dict):
                result = {
                    **result,
                    "provider": label,
                    "role": self.role.value,
                    "failed_over": bool(errors),
                }

            return result

        raise ProviderUnavailableError(
            f"No provider available for role '{self.role.value}': " + "; ".join(errors)
        )


ProviderFactory = Callable[[ModelTarget], ModelProvider]


def default_provider_factory(target: ModelTarget) -> ModelProvider:
    from app.agent_engine.adapters.chat_completions_adapter import ChatCompletionsAdapter
    from app.agent_engine.adapters.openai_adapter import OpenAIAdapter

    if target.provider == "openai":
        return OpenAIAdapter(model_name=target.model)

    if target.provider == "openrouter":
        return ChatCompletionsAdapter.openrouter(target.model)

    return ChatCompletionsAdapter.local(target.model)


class ModelRouter:
    """
    Builds the failover provider of each role from a validated config.
    """

    def __init__(
        self,
        config: Optional[RoutingConfig] = None,
        factory: ProviderFactory = default_provider_factory,
    ) -> None:
        self.config = config or RoutingConfig.from_env()
        validate_critic_independence(self.config)
        self._factory = factory
        self._providers: Dict[Role, FailoverProvider] = {}

    def provider_for(self, role: Role) -> FailoverProvider:
        if role not in self._providers:
            self._providers[role] = FailoverProvider(
                role,
                [
                    (target.label, self._factory(target))
                    for target in self.config.chain(role)
                ],
            )
        return self._providers[role]

    def describe(self) -> Dict[str, List[str]]:
        return {
            role.value: [target.label for target in self.config.chain(role)]
            for role in Role
        }


def check_routing_at_startup() -> Optional[str]:
    """
    Validate the routing config once at startup. Returns the error message
    (the agent refuses runs) or None when the configuration is safe.
    """
    try:
        validate_critic_independence(RoutingConfig.from_env())
    except RoutingConfigError as exc:
        logger.critical("Model routing rejected: %s", exc)
        return str(exc)

    return None


__all__ = [
    "CircuitBreaker",
    "FailoverProvider",
    "IMPLEMENTER_ROLES",
    "ModelRouter",
    "ModelTarget",
    "ProviderUnavailableError",
    "Role",
    "RoutingConfig",
    "RoutingConfigError",
    "breaker_for",
    "check_routing_at_startup",
    "default_provider_factory",
    "ensure_distinct_models",
    "reset_breakers",
    "triage_role",
    "validate_critic_independence",
]
