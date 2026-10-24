"""
@file tests/agent_engine/test_settings_onboarding.py
@description M12: settings that apply without a restart, configuration checks
and the first-run setup, end to end.

The end-to-end test starts from an empty database and an unusable
configuration, fixes it through the HTTP API exactly as the Settings page
does, and completes a run with the engine built from the saved settings. Only
the OpenAI client is fake.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_engine.application import get_agent_engine, reset_agent_engine
from app.agent_engine.control import RunLimits
from app.agent_engine.pricing import price_for
from app.api import settings as settings_api
from app.core.runtime_config import (
    candidate_values,
    config_value,
    replace_stored,
    source_of,
)
from app.core.security import Principal, resolve_principal
from app.core.settings_service import (
    SettingsValidationError,
    check_configuration,
    validate_changes,
)
from app.domain.models.audit import AuditLog
from app.domain.models.identity import RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.domain.models.settings import AppSetting
from app.runtime.aurora import reset_aurora_app


ADMIN = Principal(id="admin-owner", role=RoleEnum.ADMIN, workspace_id="workspace-1")
MEMBER = Principal(id="member-1", role=RoleEnum.MEMBER, workspace_id="workspace-1")

# What the launcher injects from the OS keyring; never stored by the API.
FAKE_OPENAI_KEY = "sk-test-onboarding-not-a-real-key"


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch, tmp_path):
    """
    No stored values, no cached engine, and a known environment.
    """
    for name in (
        "OPENAI_MODEL",
        "AEHUB_CHECKER_MODEL",
        "AEHUB_MODEL_ROLES",
        "AEHUB_MODEL_PRICES",
        "AEHUB_DEFAULT_MODEL_PRICE",
        "AEHUB_RUN_MAX_COST",
        "AEHUB_MONTHLY_BUDGET",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "AEHUB_FORCE_ROLE",
    ):
        monkeypatch.delenv(name, raising=False)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(workspace))

    def reset() -> None:
        replace_stored({})
        reset_agent_engine()
        reset_aurora_app()

    reset()
    yield
    reset()


def settings_client(principal: Principal) -> TestClient:
    app = FastAPI()
    app.include_router(settings_api.router)
    app.dependency_overrides[resolve_principal] = lambda: principal
    return TestClient(app)


def issue_codes(issues: List[Any]) -> Dict[str, str]:
    return {
        (issue["code"] if isinstance(issue, dict) else issue.code): (
            issue["severity"] if isinstance(issue, dict) else issue.severity
        )
        for issue in issues
    }


# ==============================================================================
# RESOLUTION ORDER
# ==============================================================================


def test_stored_value_wins_and_applies_without_restart(monkeypatch):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "2.5")
    assert RunLimits.from_env().max_run_cost == 2.5
    assert source_of("AEHUB_RUN_MAX_COST") == "environment"

    replace_stored({"AEHUB_RUN_MAX_COST": "0.5"})
    assert RunLimits.from_env().max_run_cost == 0.5
    assert source_of("AEHUB_RUN_MAX_COST") == "database"

    replace_stored({})
    monkeypatch.delenv("AEHUB_RUN_MAX_COST")
    assert RunLimits.from_env().max_run_cost == 2.0
    assert source_of("AEHUB_RUN_MAX_COST") == "default"


def test_prices_from_settings_are_not_estimated():
    replace_stored({"AEHUB_MODEL_PRICES": json.dumps({"m": {"input": 1, "output": 2}})})

    assert price_for("m") == (1.0, 2.0, False)
    assert price_for("other")[2] is True


def test_candidate_values_are_visible_only_inside_the_context(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    replace_stored({"OPENAI_MODEL": "stored-model"})

    with candidate_values({"OPENAI_MODEL": "candidate-model"}):
        assert config_value("OPENAI_MODEL") == "candidate-model"

    # None means "not stored": the environment shows through.
    with candidate_values({"OPENAI_MODEL": None}):
        assert config_value("OPENAI_MODEL") == "env-model"

    assert config_value("OPENAI_MODEL") == "stored-model"


# ==============================================================================
# VALIDATION
# ==============================================================================


@pytest.mark.parametrize(
    "name,value",
    [
        ("AEHUB_RUN_MAX_COST", "-1"),
        ("AEHUB_RUN_MAX_COST", "abc"),
        ("AEHUB_MONTHLY_BUDGET", "nan"),
        ("AEHUB_RUN_MAX_FAILED_TOOL_CALLS", "2.5"),
        ("AEHUB_BUDGET_WARNING_RATIO", "1.5"),
        ("AEHUB_MODEL_PRICES", "{not json"),
        ("AEHUB_MODEL_PRICES", '{"m": {"input": -1, "output": 1}}'),
        ("AEHUB_DEFAULT_MODEL_PRICE", "10"),
        ("AEHUB_MODEL_ROLES", "[1]"),
        ("AEHUB_MODEL_ROLES", '{"wizard": ["openai:m"]}'),
        ("NOT_A_SETTING", "1"),
    ],
)
def test_invalid_values_are_refused(monkeypatch, name, value):
    monkeypatch.setenv("AEHUB_CHECKER_MODEL", "critic-model")

    with pytest.raises(SettingsValidationError) as refused:
        validate_changes({name: value})

    assert refused.value.errors


def test_critic_equal_to_a_worker_is_refused():
    with pytest.raises(SettingsValidationError) as refused:
        validate_changes({"OPENAI_MODEL": "same-model", "AEHUB_CHECKER_MODEL": "same-model"})

    assert "Critic" in refused.value.errors["routing"]


# ==============================================================================
# CONFIGURATION CHECK
# ==============================================================================


def test_check_configuration_explains_what_to_fix(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_MODEL", "worker-model")
    monkeypatch.setenv("AEHUB_CHECKER_MODEL", "critic-model")
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "50")
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "30")
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(tmp_path / "missing"))

    issues = check_configuration()
    codes = issue_codes(issues)

    assert codes == {
        "provider_key_missing": "error",
        "price_missing": "warning",
        "run_cost_above_budget": "warning",
        "workspace_missing": "warning",
        "voice_disabled": "info",
    }

    missing_key = next(issue for issue in issues if issue.code == "provider_key_missing")
    assert "OPENAI_API_KEY" in missing_key.message
    assert "scripts/aehub.py setup" in missing_key.message

    unpriced = next(issue for issue in issues if issue.code == "price_missing")
    assert "critic-model" in unpriced.message and "worker-model" in unpriced.message


def test_check_configuration_flags_a_critic_equal_to_the_worker(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "same-model")
    monkeypatch.setenv("AEHUB_CHECKER_MODEL", "same-model")

    assert issue_codes(check_configuration())["routing_invalid"] == "error"


# ==============================================================================
# HTTP
# ==============================================================================


def test_settings_http_contract(agent_infrastructure, db_session_factory, monkeypatch):
    monkeypatch.setenv("AEHUB_CHECKER_MODEL", "critic-model")
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "2.5")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)
    admin = settings_client(ADMIN)

    view = admin.get("/api/settings")
    assert view.status_code == 200
    body = view.json()

    # Secrets: only whether they are set, never their value.
    assert FAKE_OPENAI_KEY not in view.text
    secrets = {secret["name"]: secret["configured"] for secret in body["secrets"]}
    assert secrets["OPENAI_API_KEY"] is True
    assert secrets["AEHUB_MQTT_PASSWORD"] is False
    assert "GROQ_API_KEY" not in secrets

    by_name = {setting["name"]: setting for setting in body["settings"]}
    assert by_name["AEHUB_RUN_MAX_COST"]["value"] == "2.5"
    assert by_name["AEHUB_RUN_MAX_COST"]["source"] == "environment"
    assert body["onboarding"]["completed"] is False

    saved = admin.put("/api/settings", json={"values": {"AEHUB_RUN_MAX_COST": "0.75"}})
    assert saved.status_code == 200
    by_name = {setting["name"]: setting for setting in saved.json()["settings"]}
    assert by_name["AEHUB_RUN_MAX_COST"] == {**by_name["AEHUB_RUN_MAX_COST"], "value": "0.75", "source": "database"}
    assert RunLimits.from_env().max_run_cost == 0.75

    with db_session_factory() as db:
        assert db.get(AppSetting, "AEHUB_RUN_MAX_COST").updated_by == ADMIN.id
        audit = db.query(AuditLog).filter(AuditLog.tool_name == "settings.update").one()
        assert json.loads(audit.execution_result) == {"AEHUB_RUN_MAX_COST": "0.75"}
        assert audit.principal_id == ADMIN.id

    # An invalid batch changes nothing.
    refused = admin.put(
        "/api/settings",
        json={"values": {"AEHUB_RUN_MAX_COST": "1", "AEHUB_MONTHLY_BUDGET": "-5"}},
    )
    assert refused.status_code == 422
    assert set(refused.json()["detail"]["errors"]) == {"AEHUB_MONTHLY_BUDGET"}
    assert RunLimits.from_env().max_run_cost == 0.75

    # Empty goes back to the environment.
    reverted = admin.put("/api/settings", json={"values": {"AEHUB_RUN_MAX_COST": ""}})
    assert reverted.status_code == 200
    assert RunLimits.from_env().max_run_cost == 2.5

    with db_session_factory() as db:
        assert db.get(AppSetting, "AEHUB_RUN_MAX_COST") is None

    member = settings_client(MEMBER)
    assert member.get("/api/settings").status_code == 200
    assert member.put("/api/settings", json={"values": {"AEHUB_RUN_MAX_COST": "9"}}).status_code == 403
    assert member.post("/api/settings/onboarding").status_code == 403


# ==============================================================================
# ONBOARDING, END TO END
# ==============================================================================


class ScriptedOpenAI:
    """
    Fake `AsyncOpenAI(...)`: scripted Responses API answers per model.
    """

    def __init__(self, scripts: Dict[str, List[Any]]) -> None:
        self.scripts = {model: list(answers) for model, answers in scripts.items()}
        self.requests: List[Dict[str, Any]] = []
        self.api_keys: List[str] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.api_keys.append(kwargs.get("api_key"))
        return SimpleNamespace(responses=SimpleNamespace(create=self.create))

    async def create(self, **request: Any) -> Any:
        self.requests.append(request)
        answers = self.scripts.get(request["model"])

        if not answers:
            raise AssertionError(f"Unexpected call to {request['model']}.")

        return answers.pop(0)


async def test_onboarding_from_empty_database_to_first_completed_run(
    agent_infrastructure,
    db_session_factory,
    fake_model,
    monkeypatch,
):
    agent_infrastructure.use_skills()
    admin = settings_client(ADMIN)

    # 1. Empty database, no keys: nothing can run, and the API says why.
    first = admin.get("/api/settings").json()
    assert first["onboarding"]["completed"] is False
    assert first["ready"] is False
    assert issue_codes(first["issues"])["routing_invalid"] == "error"

    blocked = admin.post("/api/settings/onboarding")
    assert blocked.status_code == 409
    assert "routing_invalid" in blocked.json()["detail"]["errors"]

    # 2. A Critic equal to the Worker is refused before it is saved.
    same = admin.put(
        "/api/settings",
        json={"values": {"OPENAI_MODEL": "onboard-worker", "AEHUB_CHECKER_MODEL": "onboard-worker"}},
    )
    assert same.status_code == 422
    assert "routing" in same.json()["detail"]["errors"]

    # 3. The launcher put the key in the environment (from the OS keyring).
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)

    # 4. Roles, prices and budget, as the first-run setup sends them.
    configured = admin.put(
        "/api/settings",
        json={
            "values": {
                "OPENAI_MODEL": "onboard-worker",
                "AEHUB_CHECKER_MODEL": "onboard-critic",
                "AEHUB_MODEL_PRICES": json.dumps(
                    {
                        "onboard-worker": {"input": 1.0, "output": 4.0},
                        "onboard-critic": {"input": 0.5, "output": 2.0},
                    }
                ),
                "AEHUB_MONTHLY_BUDGET": "5",
                "AEHUB_RUN_MAX_COST": "1",
            }
        },
    )
    assert configured.status_code == 200
    assert configured.json()["ready"] is True
    assert set(issue_codes(configured.json()["issues"])) == {"voice_disabled"}
    models = {entry["model"]: entry for entry in configured.json()["models"]}
    assert set(models) == {"onboard-worker", "onboard-critic"}
    assert models["onboard-critic"]["roles"] == ["critic"]
    assert all(entry["priced"] for entry in models.values())
    assert configured.json()["workspace"]["exists"] is True

    done = admin.post("/api/settings/onboarding")
    assert done.status_code == 200
    assert done.json()["onboarding"]["completed"] is True

    # 5. The first run, with the engine built from the saved settings.
    fake_openai = ScriptedOpenAI(
        {
            "onboard-worker": [fake_model.text("2 + 2 = 4.", usage=(1000, 200))],
            "onboard-critic": [fake_model.accept(usage=(400, 50))],
        }
    )

    with patch("app.agent_engine.adapters.openai_adapter.AsyncOpenAI", fake_openai):
        engine = await get_agent_engine()
        result = await engine.run(
            session_id="session-onboarding",
            task="How much is 2 + 2?",
            principal=ADMIN,
        )

    assert result["messages"][0].content == "2 + 2 = 4."
    assert [request["model"] for request in fake_openai.requests] == [
        "onboard-worker",
        "onboard-critic",
    ]
    assert set(fake_openai.api_keys) == {FAKE_OPENAI_KEY}

    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == result["run_id"]).one()
        assert row.status.lower() == "completed"
        usage = json.loads(row.input_data)["usage"]

    # Priced with the configured prices: (1000*1 + 200*4 + 400*0.5 + 50*2) / 1M.
    assert usage["cost"] == pytest.approx(0.0021)
