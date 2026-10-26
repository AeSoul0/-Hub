"""
@file backend/app/core/runtime_config.py
@description Settings that change without a restart (M12).

Model roles, prices, run limits and voice can be edited from the Control Plane. An
edited value is stored in the `app_settings` table and wins over the
environment; a value never edited falls back to the environment variable of
the same name, then to the built-in default. So CI, tests and an existing
`backend/.env` keep working unchanged.

Every value is a string, exactly as it would appear in the environment, so the
existing parsers (routing, pricing, limits) read both sources the same way.

This module has no application imports: the agent engine reads it on every
run, and the database layer only loads it (app.core.settings_service).

Secrets (provider API keys, the login key) are not settings: they come from
the environment only, injected by the launcher from the OS keyring.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Dict, Iterator, Literal, Mapping, Optional, Tuple


Source = Literal["database", "environment", "default"]


@dataclass(frozen=True)
class SettingSpec:
    """
    One editable setting: its environment name, where it shows in the UI and
    how its value is checked.
    """

    name: str
    group: Literal["models", "prices", "limits", "voice"]
    label: str
    kind: Literal["text", "roles", "prices", "price_pair", "number", "integer", "ratio", "choice"]
    default: str
    help: str
    # "choice": the accepted values. "text": a regular expression the whole
    # value must match (names that end up in a path or a URL).
    options: Tuple[str, ...] = ()
    pattern: str = ""


SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        name="OPENAI_MODEL",
        group="models",
        label="Worker model",
        kind="text",
        default="gpt-5.5",
        help="OpenAI model for every role not listed in the role routing.",
    ),
    SettingSpec(
        name="AEHUB_CHECKER_MODEL",
        group="models",
        label="Critic model",
        kind="text",
        default="",
        help="Model that reviews the Worker's result. It must differ from every Worker model.",
    ),
    SettingSpec(
        name="AEHUB_MODEL_ROLES",
        group="models",
        label="Role routing",
        kind="roles",
        default="",
        help=(
            'JSON: role -> list of "provider:model", tried in order. Roles: architect, '
            "research, critic, fast_worker, triage. Providers: openai, openrouter, local."
        ),
    ),
    SettingSpec(
        name="AEHUB_MODEL_PRICES",
        group="prices",
        label="Model prices",
        kind="prices",
        default="",
        help='JSON: model -> {"input": USD, "output": USD} per 1M tokens.',
    ),
    SettingSpec(
        name="AEHUB_DEFAULT_MODEL_PRICE",
        group="prices",
        label="Price of an unlisted model",
        kind="price_pair",
        default="15,60",
        help="input,output in USD per 1M tokens. Deliberately high, so a missing price overstates spend.",
    ),
    SettingSpec(
        name="AEHUB_RUN_MAX_COST",
        group="limits",
        label="Maximum cost of one run (USD)",
        kind="number",
        default="2.0",
        help="The run stops when it reaches this cost. 0 disables the limit.",
    ),
    SettingSpec(
        name="AEHUB_MONTHLY_BUDGET",
        group="limits",
        label="Monthly budget (USD)",
        kind="number",
        default="30.0",
        help="New runs are refused once the month's model spend reaches it. 0 disables the limit.",
    ),
    SettingSpec(
        name="AEHUB_BUDGET_WARNING_RATIO",
        group="limits",
        label="Budget warning threshold",
        kind="ratio",
        default="0.8",
        help="Fraction of the monthly budget that raises a warning (between 0 and 1).",
    ),
    SettingSpec(
        name="AEHUB_RUN_TIMEOUT_SECONDS",
        group="limits",
        label="Active time of one run (seconds)",
        kind="number",
        default="900",
        help="Time spent waiting for an approval does not count. 0 disables the limit.",
    ),
    SettingSpec(
        name="AEHUB_RUN_MAX_FAILED_TOOL_CALLS",
        group="limits",
        label="Failed tool calls per run",
        kind="integer",
        default="10",
        help="The run stops after this many failed tool calls. 0 disables the limit.",
    ),
    SettingSpec(
        name="AEHUB_RUN_MAX_FILES_MODIFIED",
        group="limits",
        label="Files modified per run",
        kind="integer",
        default="20",
        help="The run stops after modifying this many files. 0 disables the limit.",
    ),
    # Voice (F3, ADR-021, ADR-024): read on every use, so a change applies
    # to the next sentence without a restart.
    SettingSpec(
        name="AEHUB_STT_MODEL",
        group="voice",
        label="Speech recognition model",
        kind="choice",
        default="base",
        help="faster-whisper model, int8 on CPU. Larger is more accurate, slower and uses more RAM.",
        options=("tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"),
    ),
    SettingSpec(
        name="AEHUB_STT_LANGUAGE",
        group="voice",
        label="Spoken language",
        kind="choice",
        default="it",
        help='Language of what you say; "auto" lets the model detect it.',
        options=("it", "en", "es", "fr", "de", "pt", "auto"),
    ),
    SettingSpec(
        name="AEHUB_TTS_ENGINE",
        group="voice",
        label="Voice engine",
        kind="choice",
        default="piper",
        help="piper speaks on this computer; elevenlabs sends the reply text to ElevenLabs (ADR-024).",
        options=("piper", "elevenlabs"),
    ),
    SettingSpec(
        name="AEHUB_TTS_VOICE",
        group="voice",
        label="Piper voice",
        kind="text",
        default="it_IT-paola-medium",
        help="A voice of the Piper catalogue, e.g. it_IT-paola-medium; downloaded on first use.",
        pattern=r"[a-z]{2,3}_[A-Z]{2}-[A-Za-z0-9_]{1,40}-(x_low|low|medium|high)",
    ),
    SettingSpec(
        name="AEHUB_ELEVENLABS_VOICE",
        group="voice",
        label="ElevenLabs voice",
        kind="text",
        default="",
        help="Voice ID from your ElevenLabs voice list.",
        pattern=r"[A-Za-z0-9]{8,64}",
    ),
    SettingSpec(
        name="AEHUB_ELEVENLABS_MODEL",
        group="voice",
        label="ElevenLabs model",
        kind="text",
        default="eleven_flash_v2_5",
        help="eleven_flash_v2_5 is the fastest and cheapest; eleven_multilingual_v2 sounds richer.",
        pattern=r"[a-z0-9_]{3,64}",
    ),
)

SPEC_BY_NAME: Dict[str, SettingSpec] = {spec.name: spec for spec in SPECS}


# Values stored in the database, loaded at startup and after every edit. The
# dict is replaced, never mutated, so a reader always sees one whole version.
_stored: Dict[str, str] = {}

# Values being validated before they are saved (see candidate_values).
_candidate: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    "aehub_candidate_settings",
    default=None,
)


def config_value(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    The current value of a setting: candidate, then database, then
    environment, then `default`.
    """
    candidate = _candidate.get()

    if candidate is not None and name in candidate:
        return candidate[name]

    stored = _stored

    if name in stored:
        return stored[name]

    return os.getenv(name, default)


def source_of(name: str) -> Source:
    if name in _stored:
        return "database"

    if os.getenv(name) is not None:
        return "environment"

    return "default"


def stored_values() -> Dict[str, str]:
    return dict(_stored)


def replace_stored(values: Mapping[str, str]) -> None:
    """
    Install a new version of the database values (unknown names are ignored).
    """
    global _stored
    _stored = {
        name: str(value)
        for name, value in values.items()
        if name in SPEC_BY_NAME
    }


@contextmanager
def candidate_values(values: Mapping[str, Optional[str]]) -> Iterator[None]:
    """
    Read settings as if `values` were saved. None means "not stored", so the
    environment or default shows through. Only this context sees them.
    """
    base = dict(_candidate.get() or {})

    for name, value in values.items():
        if value is None:
            base[name] = os.getenv(name, SPEC_BY_NAME[name].default if name in SPEC_BY_NAME else "")
        else:
            base[name] = value

    token = _candidate.set(base)

    try:
        yield
    finally:
        _candidate.reset(token)


__all__ = [
    "SPECS",
    "SPEC_BY_NAME",
    "SettingSpec",
    "candidate_values",
    "config_value",
    "replace_stored",
    "source_of",
    "stored_values",
]
