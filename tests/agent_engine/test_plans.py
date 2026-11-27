"""
@file tests/agent_engine/test_plans.py
@description N7 (ADR-047): plans in several steps for the long tasks.

- plan_steps writes 2 to 12 steps; writing it again keeps the steps done;
  plan_step marks one; outside a run both refuse;
- every run sees the plan tools, which take no place of a selected tool;
- the model reads the plan in its context (L1) with the next step;
- a run with a plan gets more turns, and the plan's own calls count for no
  tool-call limit;
- end to end: a run writes its plan, marks a step while it works, the plan
  is saved with the run, published as plan.updated, and shown on the Runs
  views; a retry after the Critic keeps it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest
from openai.types.responses import Response, ResponseFunctionToolCall

from app.agent_engine.application import AgentEngine
from app.agent_engine.context import ContextManager
from app.agent_engine.delegation import DelegationScope, clear_delegation_scope, set_delegation_scope
from app.agent_engine.runtime import AgentRuntime, DEFAULT_MAX_TURNS, PLAN_MAX_TURNS, _turn_limit
from app.agent_engine.tool_selection import ALWAYS_TOOLS, select_tools
from app.api import runs as runs_api
from app.core.security import Principal, RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills import plan_skill
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata
from app.skills.plan_skill import PlanSkill

WORKSPACE = "workspace-n7"
USER = Principal(id="user-n7", role=RoleEnum.USER, workspace_id=WORKSPACE)


def _scope(plan: Dict[str, Any] | None) -> DelegationScope:
    return DelegationScope(
        parent_run_id="run-1",
        session_id="s",
        workspace_id=WORKSPACE,
        principal=USER,
        usage={},
        max_run_cost=1,
        max_subagents=0,
        plan=plan,
    )


def test_writing_and_marking_a_plan(monkeypatch):
    published: List[Any] = []
    monkeypatch.setattr("app.agent_engine.events.EventDispatcher.dispatch", lambda self, event, **kw: published.append((event, kw["details"]["steps"])))
    plan: Dict[str, Any] = {}
    set_delegation_scope(_scope(plan))
    try:
        answer = asyncio.run(plan_skill.plan_steps(["Trova i file", "Riassumili", "Scrivi il report"]))
        assert "1. [pending] Trova i file" in answer and answer.endswith("Go on with step 1.")
        asyncio.run(plan_skill.plan_step(1, "done", "3 file trovati"))
        assert "1. [done] Trova i file — 3 file trovati" in plan_skill.render(plan)
        assert plan_skill.next_step(plan) == 2

        # Written again (a step changed): the step done stays done.
        asyncio.run(plan_skill.plan_steps(["Trova i file", "Riassumili in italiano", "Scrivi il report"]))
        assert [step["status"] for step in plan["steps"]] == ["done", "pending", "pending"]

        for wrong in (lambda: plan_skill.plan_steps(["uno"]), lambda: plan_skill.plan_steps([str(i) for i in range(13)]),
                      lambda: plan_skill.plan_step(9, "done"), lambda: plan_skill.plan_step(1, "pending")):
            with pytest.raises(ValueError):
                asyncio.run(wrong())
        asyncio.run(plan_skill.plan_step(2, "skipped"))
        asyncio.run(plan_skill.plan_step(3, "done"))
        assert plan_skill.render(plan).endswith("Every step is finished: give the final answer.")
    finally:
        clear_delegation_scope()
    assert [event for event, _ in published] == ["plan.updated"] * 5
    with pytest.raises(PermissionError):
        asyncio.run(plan_skill.plan_steps(["a", "b"]))


def test_every_run_sees_the_plan_tools(monkeypatch):
    class Many(BaseSkill):
        metadata = SkillMetadata(name="many", description="Many tools.")

        @property
        def tools(self):
            return []

        def get_tool_metadata(self):
            return {
                f"tool_{word}": ToolMetadata(name=f"tool_{word}", description=f"Does {word} things.", risk_level=RiskLevel.LOW, examples=[word])
                for word in ("weather", "music", "lights", "mail", "notes", "maps", "news", "files")
            }

    class Registry:
        def __init__(self):
            self.meta = {**Many().get_tool_metadata(), **PlanSkill().get_tool_metadata()}

        def get_registered_tool_names(self):
            return list(self.meta)

        def get_tool_metadata(self, name):
            return self.meta.get(name)

    monkeypatch.setenv("AEHUB_TOOL_SELECTION", "on")
    monkeypatch.setenv("AEHUB_TOOL_TOP_K", "2")
    monkeypatch.setenv("AEHUB_SKILL_INDEX_PATH", ":memory:")
    selected = select_tools(Registry(), "what is the weather")
    assert "tool_weather" in selected and set(ALWAYS_TOOLS) <= set(selected)
    assert len([name for name in selected if name not in ALWAYS_TOOLS]) <= 2
    monkeypatch.setenv("AEHUB_DISABLED_TOOLS", "plan_steps")
    assert "plan_steps" not in select_tools(Registry(), "what is the weather")


def test_the_model_reads_the_plan_and_gets_more_turns():
    plan = {"steps": [{"text": "A", "status": "done", "note": ""}, {"text": "B", "status": "pending", "note": ""}]}
    context, _ = ContextManager().build({"task": {"description": "Do A and B"}, "plan": plan, "observations": []})
    [block] = [block for block in context["context_blocks"] if block["level"] == "L1"]
    assert "2. [pending] B" in block["content"] and "Go on with step 2." in block["content"] and block["trusted"]
    untrusted, _ = ContextManager().build({"task": "x", "plan": plan, "observations": [], "untrusted_context": True})
    assert untrusted["context_blocks"][0]["trusted"] is False

    assert _turn_limit({}, DEFAULT_MAX_TURNS) == DEFAULT_MAX_TURNS
    assert _turn_limit({"plan": plan}, DEFAULT_MAX_TURNS) == DEFAULT_MAX_TURNS + 4
    assert _turn_limit({"plan": {"steps": [{}] * 12}}, DEFAULT_MAX_TURNS) == PLAN_MAX_TURNS


# ==============================================================================
# END TO END
# ==============================================================================


class Work(BaseSkill):
    def __init__(self) -> None:
        self.calls: List[str] = []

    metadata = SkillMetadata(name="work", description="Work tools.")

    @property
    def tools(self):
        def ping(target: str) -> str:
            self.calls.append(target)
            return f"pong {target}"

        return [ping]

    def get_tool_metadata(self):
        return {
            "ping": ToolMetadata(
                name="ping",
                description="Ping a target.",
                risk_level=RiskLevel.LOW,
                input_schema={"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"], "additionalProperties": False},
            )
        }


def _calls(response_id: str, *calls: tuple) -> Response:
    return Response(
        id=response_id,
        created_at=0,
        model="fake",
        object="response",
        output=[
            ResponseFunctionToolCall(type="function_call", call_id=call_id, name=name, arguments=json.dumps(arguments))
            for call_id, name, arguments in calls
        ],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
    )


async def test_a_run_writes_works_and_keeps_its_plan(agent_infrastructure, fake_model, db_session_factory, monkeypatch):
    monkeypatch.setenv("AEHUB_CRITIC_SIMPLE", "check")
    work = Work()
    agent_infrastructure.use_skills(work, PlanSkill())
    worker = fake_model.adapter(
        [
            fake_model.function_call("c1", "plan_steps", {"steps": ["Ping a", "Ping b"]}),
            # The plan's calls ride along with the work, in the same turn.
            _calls("r2", ("c2", "plan_step", {"step": 1, "status": "doing"}), ("c3", "ping", {"target": "a"})),
            _calls("r3", ("c4", "plan_step", {"step": 1, "status": "done", "note": "pong a"}), ("c5", "ping", {"target": "b"})),
            fake_model.text("Pinged a and b."),
            # After the Critic's retry the plan is still there.
            fake_model.function_call("c6", "plan_step", {"step": 2, "status": "done"}),
            fake_model.text("Pinged a and b, both answered."),
        ]
    )
    critic = fake_model.checker(
        [
            fake_model.text(json.dumps({"decision": "RETRY", "issues": [], "retry_instruction": "Mark step 2 done."})),
            fake_model.accept(),
        ]
    )
    engine = AgentEngine(model_provider=worker, checker_provider=critic, runtime=AgentRuntime())

    result = await engine.run(session_id="s-n7", task="Ping a, then b, and tell me.", principal=USER)
    for _ in range(5):
        await asyncio.sleep(0)

    assert work.calls == ["a", "b"]
    assert result["messages"][-1].content == "Pinged a and b, both answered."

    with db_session_factory() as db:
        row = db.query(DbAgentRun).one()
        snapshot = json.loads(row.input_data)
    plan = snapshot["current_state"]["worker_context"]["plan"]
    assert [(step["text"], step["status"]) for step in plan["steps"]] == [("Ping a", "done"), ("Ping b", "done")]
    # The plan's calls count for no limit: only the two pings.
    assert snapshot["usage"]["tool_calls"] == 2

    updates = [
        data["details"]["steps"]
        for _, kind, data in agent_infrastructure.published
        if kind == "engine.event" and data["event_type"] == "plan.updated"
    ]
    assert [[step["status"] for step in steps] for steps in updates] == [
        ["pending", "pending"],
        ["doing", "pending"],
        ["done", "pending"],
        ["done", "done"],
    ]
    # The model read the plan at its next turn.
    second = json.dumps(worker._client.responses.requests[1], default=str)
    assert "Go on with step 1" in second

    detail = runs_api.run_detail(row.id, WORKSPACE)
    assert [step["status"] for step in detail["plan"]] == ["done", "done"]
