"""
@file tests/agent_engine/test_budget_killswitch.py
@description Spend limits, kill switch and live run state (roadmap M4 exit).

Exit tests:
- an exceeded budget stops the run in the middle of the loop;
- the kill switch interrupts a long-running tool within a few seconds;
- the run cost equals the sum of the reported model usage.

Prices are configured so that one token costs a whole number of dollars:
input 1 USD/token, output 2 USD/token.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException

from app.agent_engine.application import AgentEngine
from app.agent_engine.control import SpendLedger, current_period, run_registry
from app.agent_engine.pricing import FALLBACK_PRICE, usage_from_response
from app.agent_engine.runtime import AgentRuntime
from app.api import runs as runs_api
from app.core.security import Principal, RoleEnum
from app.domain.models.audit import AuditLog
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


SESSION_ID = "session-m4"
WORKSPACE_ID = "workspace-m4"
KILL_SWITCH_DEADLINE_SECONDS = 3.0


# ==============================================================================
# TEST DOUBLES
# ==============================================================================


class OpsSkill(BaseSkill):
    """
    A quick LOW tool and a slow one that only ends when cancelled.
    """

    def __init__(self) -> None:
        self.calls: List[str] = []
        self.slow_started = asyncio.Event()
        self.slow_cancelled = False

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="ops", description="Ops tools.")

    @property
    def tools(self):
        def ping(target: str) -> str:
            self.calls.append(target)
            return f"pong {target}"

        async def long_job(seconds: int) -> str:
            self.slow_started.set()
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                self.slow_cancelled = True
                raise
            return "finished"

        return [ping, long_job]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        def schema(**properties: Any) -> Dict[str, Any]:
            return {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }

        return {
            "ping": ToolMetadata(
                name="ping",
                description="Ping a target.",
                risk_level=RiskLevel.LOW,
                input_schema=schema(target={"type": "string"}),
            ),
            "long_job": ToolMetadata(
                name="long_job",
                description="A long-running job.",
                risk_level=RiskLevel.LOW,
                input_schema=schema(seconds={"type": "integer"}),
            ),
        }


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def ops(agent_infrastructure) -> OpsSkill:
    skill = OpsSkill()
    agent_infrastructure.use_skills(skill)
    return skill


@pytest.fixture(autouse=True)
def priced(monkeypatch):
    monkeypatch.setenv(
        "AEHUB_MODEL_PRICES",
        json.dumps(
            {
                model: {"input": 1_000_000, "output": 2_000_000}
                for model in ("fake-model", "fake-critic")
            }
        ),
    )
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "100")
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "1000")


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    run_registry.resume()
    for live in run_registry.active():
        run_registry.unregister(live.run_id)


@pytest.fixture
def user() -> Principal:
    return Principal(id="user-m4", role=RoleEnum.USER, workspace_id=WORKSPACE_ID)


def _engine(fake_model, worker_script: List[Any], checker_script: List[Any]) -> AgentEngine:
    worker = fake_model.adapter(worker_script)
    engine = AgentEngine(
        model_provider=worker,
        checker_provider=fake_model.checker(checker_script),
        runtime=AgentRuntime(),
    )
    engine.model_requests = worker._client.responses.requests
    return engine


def _run_row(db_session_factory, run_id: str) -> Dict[str, Any]:
    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).one()
        return {"status": row.status.lower(), "snapshot": json.loads(row.input_data)}


# ==============================================================================
# PRICING
# ==============================================================================


def test_usage_is_priced_from_configuration():
    usage = usage_from_response(
        "fake-model",
        {"input_tokens": 3, "output_tokens": 2},
    )

    assert usage.total_tokens == 5
    assert usage.cost == 3 * 1 + 2 * 2
    assert usage.estimated is False


def test_unknown_model_uses_the_conservative_fallback(monkeypatch):
    monkeypatch.delenv("AEHUB_DEFAULT_MODEL_PRICE", raising=False)

    usage = usage_from_response("mystery-model", {"prompt_tokens": 1_000_000, "completion_tokens": 0})

    assert usage.estimated is True
    assert usage.cost == FALLBACK_PRICE[0]


def test_missing_usage_costs_nothing():
    assert usage_from_response("fake-model", None).cost == 0.0


# ==============================================================================
# EXIT: RUN COST == SUM OF USAGE
# ==============================================================================


async def test_run_cost_equals_the_sum_of_model_usage(
    ops, user, fake_model, db_session_factory, agent_infrastructure
):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "ping", {"target": "a"}, usage=(2, 1)),
            fake_model.text("Done.", usage=(1, 1)),
        ],
        [fake_model.accept(usage=(1, 0))],
    )

    result = await engine.run(session_id=SESSION_ID, task="Ping a.", principal=user)

    assert result["messages"][0].content == "Done."

    usage = _run_row(db_session_factory, result["run_id"])["snapshot"]["usage"]

    # worker (2,1)=4 + worker (1,1)=3 + checker (1,0)=1
    assert usage["cost"] == 8
    assert usage["cost"] == sum(call["cost"] for call in usage["calls"])
    assert usage["input_tokens"] == 4
    assert usage["output_tokens"] == 2
    assert usage["total_tokens"] == 6
    assert usage["model_calls"] == 3
    assert [call["role"] for call in usage["calls"]] == ["worker", "worker", "critic"]
    assert usage["by_model"] == {
        "fake-model": {"calls": 2, "total_tokens": 5, "cost": 7},
        "fake-critic": {"calls": 1, "total_tokens": 1, "cost": 1},
    }
    assert SpendLedger.spent(user.id, current_period()) == 8


# ==============================================================================
# EXIT: BUDGET STOPS THE RUN MID-LOOP
# ==============================================================================


async def test_run_budget_stops_the_loop_midway(
    ops, user, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "10")

    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "ping", {"target": "a"}, usage=(2, 1)),
            fake_model.function_call("call_2", "ping", {"target": "b"}, usage=(3, 2)),
            fake_model.text("Never reached.", usage=(1, 1)),
        ],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Ping a then b.", principal=user)
    outcome = result["messages"][0].content

    # Turn 1 (4 USD) ran its tool; turn 2 brought the run to 11 USD, so its
    # tool never ran and no further model call was made.
    assert outcome["status"] == "BUDGET_EXCEEDED"
    assert "Run budget exhausted" in outcome["reason"]
    assert ops.calls == ["a"]
    assert len(engine.model_requests) == 2

    row = _run_row(db_session_factory, result["run_id"])
    assert row["status"] == "failed"
    assert row["snapshot"]["usage"]["cost"] == 11


async def test_monthly_budget_blocks_before_any_model_call(
    ops, user, fake_model, monkeypatch
):
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "50")
    SpendLedger.add(user.id, 50)

    engine = _engine(fake_model, [fake_model.text("Hi.", usage=(1, 1))], [fake_model.accept()])

    result = await engine.run(session_id=SESSION_ID, task="Say hi.", principal=user)
    outcome = result["messages"][0].content

    assert outcome["status"] == "BUDGET_EXCEEDED"
    assert "Monthly budget exhausted" in outcome["reason"]
    assert engine.model_requests == []


async def test_monthly_budget_warns_at_eighty_percent(
    ops, user, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "100")
    SpendLedger.add(user.id, 78)

    engine = _engine(
        fake_model,
        [fake_model.text("Hi.", usage=(1, 1))],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Say hi.", principal=user)

    assert result["messages"][0].content == "Hi."
    usage = _run_row(db_session_factory, result["run_id"])["snapshot"]["usage"]
    assert usage["budget_warning"] is True


async def test_spend_ledger_failure_blocks_model_calls(ops, user, fake_model, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(SpendLedger, "spent", staticmethod(broken))

    engine = _engine(fake_model, [fake_model.text("Hi.")], [fake_model.accept()])

    result = await engine.run(session_id=SESSION_ID, task="Say hi.", principal=user)

    assert result["messages"][0].content["status"] == "BUDGET_EXCEEDED"
    assert engine.model_requests == []


# ==============================================================================
# EXIT: KILL SWITCH INTERRUPTS A LONG TOOL
# ==============================================================================


async def _start_long_run(engine: AgentEngine, user: Principal, ops: OpsSkill):
    task = asyncio.create_task(
        engine.run(session_id=SESSION_ID, task="Run the long job.", principal=user)
    )
    await asyncio.wait_for(ops.slow_started.wait(), timeout=5)

    [live] = run_registry.active(WORKSPACE_ID)
    return task, live.run_id


async def test_kill_switch_interrupts_a_long_tool(
    ops, user, fake_model, db_session_factory, agent_infrastructure
):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "long_job", {"seconds": 600}),
            fake_model.text("Never reached."),
        ],
        [fake_model.accept()],
    )

    task, run_id = await _start_long_run(engine, user, ops)

    loop = asyncio.get_running_loop()
    started = loop.time()

    await runs_api.cancel_run(run_id, principal=user)
    result = await asyncio.wait_for(task, timeout=KILL_SWITCH_DEADLINE_SECONDS)

    assert loop.time() - started < KILL_SWITCH_DEADLINE_SECONDS
    assert result["messages"][0].content["status"] == "CANCELLED"
    assert ops.slow_cancelled is True
    assert len(engine.model_requests) == 1
    assert run_registry.active(WORKSPACE_ID) == []

    assert _run_row(db_session_factory, run_id)["status"] == "cancelled"

    with db_session_factory() as db:
        decisions = [
            row.decision
            for row in db.query(AuditLog)
            .filter(AuditLog.run_id == run_id)
            .order_by(AuditLog.timestamp)
            .all()
        ]

    assert decisions == ["EXECUTING", "CANCELLED"]

    states = [
        data["state"]
        for _, event_type, data in agent_infrastructure.published
        if event_type == "run.state"
    ]
    assert states == ["planning", "tool_running", "done"]


async def test_stop_all_cancels_live_runs_and_blocks_new_ones(ops, user, fake_model):
    admin = Principal(id="admin-m4", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)

    engine = _engine(
        fake_model,
        [fake_model.function_call("call_1", "long_job", {"seconds": 600})],
        [fake_model.accept()],
    )
    task, _ = await _start_long_run(engine, user, ops)

    stopped = await runs_api.stop_all_runs(principal=admin)
    result = await asyncio.wait_for(task, timeout=KILL_SWITCH_DEADLINE_SECONDS)

    assert stopped == {"halted": True, "cancelled_runs": 1}
    assert result["messages"][0].content["status"] == "CANCELLED"

    # While halted, a new run never reaches the model.
    blocked = _engine(fake_model, [fake_model.text("Hi.")], [fake_model.accept()])
    refused = await blocked.run(session_id=SESSION_ID, task="Say hi.", principal=user)

    assert refused["messages"][0].content["status"] == "CANCELLED"
    assert blocked.model_requests == []

    await runs_api.resume_runs(principal=admin)
    assert run_registry.halted is False


async def test_kill_switch_permissions(user):
    other = Principal(id="other", role=RoleEnum.USER, workspace_id=WORKSPACE_ID)
    run_registry.register("run-x", SESSION_ID, WORKSPACE_ID, user.id)

    with pytest.raises(HTTPException) as forbidden:
        await runs_api.cancel_run("run-x", principal=other)
    assert forbidden.value.status_code == 403

    stranger = Principal(id="stranger", role=RoleEnum.ADMIN, workspace_id="elsewhere")
    with pytest.raises(HTTPException) as missing:
        await runs_api.cancel_run("run-x", principal=stranger)
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as not_admin:
        await runs_api.stop_all_runs(principal=user)
    assert not_admin.value.status_code == 403

    assert run_registry.get("run-x").token.is_cancelled is False


# ==============================================================================
# DASHBOARD
# ==============================================================================


async def test_stats_report_inferences_cost_and_failed_tools(
    ops, user, fake_model
):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "ping", {"target": "a"}, usage=(2, 1)),
            # Wrong argument type: denied by schema validation in the Gateway.
            fake_model.function_call("call_2", "ping", {"target": 5}, usage=(1, 0)),
            fake_model.text("Done.", usage=(1, 1)),
        ],
        [fake_model.accept(usage=(1, 0))],
    )

    result = await engine.run(session_id=SESSION_ID, task="Ping a.", principal=user)

    stats = runs_api.build_stats(user, days=30)

    [day] = stats["inferences_per_day"].values()
    assert day == {"fake-model": 3, "fake-critic": 1}
    assert stats["cost_by_session"] == {SESSION_ID: 4 + 1 + 3 + 1}
    assert stats["cost_by_role"] == {"worker": 4 + 1 + 3, "critic": 1}
    assert stats["cost_by_model"] == {"fake-model": 8, "fake-critic": 1}
    assert stats["runs"][0]["run_id"] == result["run_id"]
    assert stats["runs"][0]["model_calls"] == 4
    assert stats["budget"]["month_spent"] == 9
    assert stats["cost_estimated"] is False
    assert stats["failed_tool_calls"] == {"total": 1, "by_tool": {"ping": 1}}
