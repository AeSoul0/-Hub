"""
@file backend/app/core/settings_service.py
@description Load, validate and save the Control Plane settings; check the
whole configuration with clear messages (M12).

- load_settings(db): installs the stored values (startup, after each save).
- validate_changes(changes): field errors, then the routing rules (the Critic
  must differ from every Worker) on the would-be configuration.
- save_settings(db, changes, principal): audit entry first (fail closed), then
  the rows; the engine is rebuilt on the next request.
- check_configuration(): what blocks a run (errors), what may surprise the
  user (warnings) and what is off (info).
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Literal, Mapping, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.runtime_config import (
    SPEC_BY_NAME,
    SPECS,
    candidate_values,
    config_value,
    replace_stored,
    source_of,
)
from app.domain.models.settings import AppSetting


logger = logging.getLogger(__name__)

ONBOARDING_KEY = "_onboarding_completed_at"
MAX_VALUE_LENGTH = 10_000

# Provider -> the environment variable holding its key. The local provider
# (an OpenAI-compatible server on this machine) needs none.
PROVIDER_KEYS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

SECRETS = (
    ("OPENAI_API_KEY", "OpenAI API key", "models with the openai provider"),
    ("OPENROUTER_API_KEY", "OpenRouter API key", "models with the openrouter provider"),
    ("AEHUB_MQTT_PASSWORD", "MQTT broker password", "home devices (optional)"),
)

SETUP_HINT = "Add it with: python scripts/aehub.py setup, then restart with: python scripts/aehub.py up."

Severity = Literal["error", "warning", "info"]


class SettingsValidationError(ValueError):
    def __init__(self, errors: Dict[str, str]) -> None:
        super().__init__("; ".join(f"{name}: {message}" for name, message in errors.items()))
        self.errors = errors


@dataclass(frozen=True)
class ConfigIssue:
    code: str
    severity: Severity
    message: str
    setting: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


# ==============================================================================
# LOAD AND SAVE
# ==============================================================================


def load_settings(db: DBSession) -> None:
    rows = db.query(AppSetting).all()
    replace_stored({row.key: row.value for row in rows if row.key in SPEC_BY_NAME})


def _check_value(name: str, value: str) -> Optional[str]:
    spec = SPEC_BY_NAME[name]

    if len(value) > MAX_VALUE_LENGTH:
        return "The value is too long."

    try:
        if spec.kind == "roles":
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                return "Role routing must be a JSON object."

        elif spec.kind == "prices":
            from app.agent_engine.pricing import parse_prices

            parse_prices(value)

        elif spec.kind == "price_pair":
            from app.agent_engine.pricing import parse_price_pair

            parse_price_pair(value)

        elif spec.kind in {"number", "integer", "ratio"}:
            number = int(value) if spec.kind == "integer" else float(value)

            if not math.isfinite(number) or number < 0:
                return "Enter a number greater than or equal to 0."

            if spec.kind == "ratio" and not 0 < number <= 1:
                return "Enter a number between 0 and 1."

    except ValueError as exc:
        if spec.kind in {"number", "ratio"}:
            return "Enter a number."
        if spec.kind == "integer":
            return "Enter a whole number."
        if spec.kind == "roles":
            return "Role routing is not valid JSON."
        return str(exc)

    return None


def normalize_changes(changes: Mapping[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """
    Trim values; an empty value means "back to the environment or default".
    """
    unknown = sorted(set(changes) - set(SPEC_BY_NAME))

    if unknown:
        raise SettingsValidationError({name: "Unknown setting." for name in unknown})

    normalized: Dict[str, Optional[str]] = {}

    for name, value in changes.items():
        value = None if value is None else str(value).strip()
        normalized[name] = value or None

    return normalized


def validate_changes(changes: Mapping[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """
    Return the normalized changes or raise SettingsValidationError.
    """
    from app.agent_engine.routing import (
        RoutingConfig,
        RoutingConfigError,
        validate_critic_independence,
    )

    normalized = normalize_changes(changes)
    errors = {
        name: message
        for name, value in normalized.items()
        if value is not None and (message := _check_value(name, value))
    }

    if errors:
        raise SettingsValidationError(errors)

    with candidate_values(normalized):
        try:
            validate_critic_independence(RoutingConfig.from_env())
        except RoutingConfigError as exc:
            raise SettingsValidationError({"routing": str(exc)}) from exc

    return normalized


def save_settings(
    db: DBSession,
    changes: Mapping[str, Optional[str]],
    principal_id: str,
    workspace_id: str,
) -> Dict[str, Optional[str]]:
    """
    Validate and store `changes` (None removes the stored value). The audit
    entry is written first: a change that cannot be audited is not applied.
    """
    from app.runtime.audit_chain import append_audit_record

    normalized = validate_changes(changes)

    if not normalized:
        return normalized

    append_audit_record(
        db,
        session_id="control-plane",
        principal_id=principal_id,
        workspace_id=workspace_id,
        tool_name="settings.update",
        risk="high",
        decision="ALLOW",
        success=True,
        execution_result=json.dumps(normalized, sort_keys=True, ensure_ascii=False),
    )

    for name, value in normalized.items():
        row = db.get(AppSetting, name)

        if value is None:
            if row is not None:
                db.delete(row)
            continue

        if row is None:
            db.add(AppSetting(key=name, value=value, updated_by=principal_id))
        else:
            row.value = value
            row.updated_by = principal_id

    db.commit()
    load_settings(db)
    rebuild_engine()

    return normalized


def rebuild_engine() -> None:
    """
    The next request builds the engine from the new model settings.
    """
    from app.agent_engine.application import reset_agent_engine
    from app.agent_engine.routing import reset_breakers
    from app.runtime.aurora import reset_aurora_app

    reset_agent_engine()
    reset_aurora_app()
    reset_breakers()


# ==============================================================================
# ONBOARDING
# ==============================================================================


def onboarding_completed_at(db: DBSession) -> Optional[str]:
    row = db.get(AppSetting, ONBOARDING_KEY)
    return row.value if row is not None else None


def complete_onboarding(db: DBSession, principal_id: str) -> str:
    """
    Mark the first-run setup done. Refused while a configuration error would
    stop every run.
    """
    blocking = [issue for issue in check_configuration() if issue.severity == "error"]

    if blocking:
        raise SettingsValidationError({issue.code: issue.message for issue in blocking})

    completed_at = datetime.utcnow().isoformat() + "Z"
    row = db.get(AppSetting, ONBOARDING_KEY)

    if row is None:
        db.add(AppSetting(key=ONBOARDING_KEY, value=completed_at, updated_by=principal_id))
    else:
        row.value = completed_at
        row.updated_by = principal_id

    db.commit()
    return completed_at


# ==============================================================================
# CONFIGURATION CHECK
# ==============================================================================


def _env_set(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def check_configuration() -> List[ConfigIssue]:
    """
    Everything that would stop or surprise a run, with how to fix it.
    """
    from app.agent_engine.guardrails import allowed_directories
    from app.agent_engine.pricing import FALLBACK_PRICE, configured_price_models
    from app.agent_engine.routing import (
        RoutingConfig,
        RoutingConfigError,
        validate_critic_independence,
    )

    issues: List[ConfigIssue] = []

    try:
        routing = RoutingConfig.from_env()
    except RoutingConfigError as exc:
        issues.append(ConfigIssue("routing_invalid", "error", str(exc), "AEHUB_MODEL_ROLES"))
        routing = None

    if routing is not None:
        # Reported with the other issues below, so every problem shows at once.
        try:
            validate_critic_independence(routing)
        except RoutingConfigError as exc:
            issues.append(ConfigIssue("routing_invalid", "error", str(exc), "AEHUB_CHECKER_MODEL"))

    if routing is not None:
        roles_by_provider: Dict[str, List[str]] = {}
        models = set()

        for role, chain in routing.chains.items():
            for target in chain:
                roles_by_provider.setdefault(target.provider, [])
                if role.value not in roles_by_provider[target.provider]:
                    roles_by_provider[target.provider].append(role.value)
                models.add(target.model)

        for provider, roles in sorted(roles_by_provider.items()):
            key = PROVIDER_KEYS.get(provider)

            if key and not _env_set(key):
                issues.append(
                    ConfigIssue(
                        "provider_key_missing",
                        "error",
                        f"The {provider} provider is used by {', '.join(roles)}, but {key} "
                        f"is not set. {SETUP_HINT}",
                    )
                )

        unpriced = sorted(models - configured_price_models())

        if unpriced:
            issues.append(
                ConfigIssue(
                    "price_missing",
                    "warning",
                    f"No price for {', '.join(unpriced)}: the cost is estimated with the price "
                    f"of an unlisted model ({config_value('AEHUB_DEFAULT_MODEL_PRICE') or '%g,%g' % FALLBACK_PRICE} "
                    "USD per 1M tokens), so spend and budget are approximate.",
                    "AEHUB_MODEL_PRICES",
                )
            )

    try:
        run_cost = float(config_value("AEHUB_RUN_MAX_COST", "2.0"))
        monthly = float(config_value("AEHUB_MONTHLY_BUDGET", "30.0"))
    except ValueError:
        run_cost = monthly = 0.0

    if run_cost > 0 and monthly > 0 and run_cost > monthly:
        issues.append(
            ConfigIssue(
                "run_cost_above_budget",
                "warning",
                f"One run may cost up to ${run_cost:g}, more than the monthly budget of ${monthly:g}.",
                "AEHUB_RUN_MAX_COST",
            )
        )

    workspace = allowed_directories()[0]

    if not workspace.is_dir():
        issues.append(
            ConfigIssue(
                "workspace_missing",
                "warning",
                f"The working folder {workspace} does not exist: file tools will fail. "
                "Choose it with: python scripts/aehub.py setup.",
            )
        )
    elif not os.access(workspace, os.W_OK):
        issues.append(
            ConfigIssue(
                "workspace_read_only",
                "warning",
                f"The working folder {workspace} is not writable.",
            )
        )

    from app.voice.engines import missing_packages, voice_enabled

    if not voice_enabled():
        issues.append(
            ConfigIssue(
                "voice_disabled",
                "info",
                "Voice is off (AEHUB_VOICE=off).",
            )
        )
    elif missing_packages():
        issues.append(
            ConfigIssue(
                "voice_disabled",
                "warning",
                f"Voice needs {', '.join(missing_packages())}: install the backend requirements.",
            )
        )

    return issues


def log_configuration_issues() -> List[ConfigIssue]:
    """
    Startup report: one line per issue, so `docker compose logs backend`
    says what to fix.
    """
    issues = check_configuration()

    for issue in issues:
        level = {"error": logging.ERROR, "warning": logging.WARNING}.get(issue.severity, logging.INFO)
        logger.log(level, "Configuration %s: %s", issue.severity, issue.message)
        print(f"[CONFIG {issue.severity.upper()}] {issue.message}")

    return issues


# ==============================================================================
# VIEW
# ==============================================================================


def routed_models() -> List[Dict[str, object]]:
    """
    Every model the current routing can call, with its roles and whether it
    has a configured price. Empty when the routing is invalid.
    """
    from app.agent_engine.pricing import configured_price_models
    from app.agent_engine.routing import RoutingConfig, RoutingConfigError

    try:
        routing = RoutingConfig.from_env()
    except RoutingConfigError:
        return []

    priced = configured_price_models()
    models: Dict[str, Dict[str, object]] = {}

    for role, chain in routing.chains.items():
        for target in chain:
            entry = models.setdefault(
                target.model,
                {"model": target.model, "providers": [], "roles": [], "priced": target.model in priced},
            )
            if target.provider not in entry["providers"]:
                entry["providers"].append(target.provider)
            if role.value not in entry["roles"]:
                entry["roles"].append(role.value)

    return sorted(models.values(), key=lambda entry: str(entry["model"]))


def settings_view(db: DBSession) -> Dict[str, object]:
    """
    What the Settings page shows. Secrets appear only as configured or not.
    """
    from app.agent_engine.guardrails import allowed_directories

    issues = check_configuration()
    completed_at = onboarding_completed_at(db)
    workspace = allowed_directories()[0]

    return {
        "models": routed_models(),
        "workspace": {"path": str(workspace), "exists": workspace.is_dir()},
        "settings": [
            {
                "name": spec.name,
                "group": spec.group,
                "label": spec.label,
                "kind": spec.kind,
                "help": spec.help,
                "default": spec.default,
                "value": config_value(spec.name, spec.default) or "",
                "source": source_of(spec.name),
            }
            for spec in SPECS
        ],
        "secrets": [
            {"name": name, "label": label, "used_for": used_for, "configured": _env_set(name)}
            for name, label, used_for in SECRETS
        ],
        "issues": [issue.to_dict() for issue in issues],
        "ready": not any(issue.severity == "error" for issue in issues),
        "onboarding": {
            "completed": completed_at is not None,
            "completed_at": completed_at,
        },
    }


__all__ = [
    "ConfigIssue",
    "SettingsValidationError",
    "check_configuration",
    "complete_onboarding",
    "load_settings",
    "log_configuration_issues",
    "onboarding_completed_at",
    "rebuild_engine",
    "save_settings",
    "settings_view",
    "validate_changes",
]
