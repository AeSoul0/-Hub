"""
@file tests/agent_engine/test_delegation.py
@description F8 (ADR-029): delegation to subagents, the run tree, the
Critic's verdicts in the timeline and the role chosen for one command.

In single-model mode the parent and its subagent share one scripted worker
and one scripted Critic, so the scripts follow the order of the calls:
parent, subagent, subagent's Critic, parent, parent's Critic.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.agent_engine import events as events_module
from app.agent_engine import runtime as runtime_module
from app.agent_engine.application import AgentEngine
from app.agent_engine.control import run_registry
from app.agent_engine.delegation import UNCAPPED_SUBAGENT_BUDGET, DelegationScope
from app.agent_engine.resources import PROFILES, TaskClass
from app.agent_engine.routing import Role, command_role, triage_role
from app.agent_engine.runtime import AgentRuntime
from app.api.runs import limits_view, run_detail
from app.agent_engine.control import RunLimits
from app.core.security import Principal, RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, SkillMetadata, ToolMetadata
from app.skills.orchestration_skill import OrchestrationSkill


SESSION_ID = "session-f8"
WORKSPACE_ID = "workspace-f8"


class NoteSkill(BaseSkill):
    def __init__(self) -> None:
        self.calls: List[str] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="notes", description="Notes.")

    @property
    def tools(self):
        def note(text: str) -> str:
            self.calls.append(text)
            return f"noted {text}"

        return [note]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "note": ToolMetadata(
                name="note",
                description="Write a note.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            ),
        }


@pytest.fixture
def skills(agent_infrastructure) -> NoteSkill:
    notes = NoteSkill()
    agent_infrastructure.use_skills(OrchestrationSkill(), notes)
    return notes


@pytest.fixture(autouse=True)
def enough_memory(monkeypatch):
    monkeypatch.setattr(
        runtime_module.ResourceManager,
        "allocate",
        classmethod(lambda cls, description: PROFILES[TaskClass.STANDARD]),
    )


@pytest.fixture(autouse=True)
def priced(monkeypatch):
    # One dollar per token, so costs are easy to read.
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "100")
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "1000")
    monkeypatch.setenv(
        "AEHUB_MODEL_PRICES",
        json.dumps(
            {
                "fake-model": {"input": 1_000_000, "output": 1_000_000},
                "fake-critic": {"input": 1_000_000, "output": 1_000_000},
            }
        ),
    )


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    run_registry.resume()
    for live in run_registry.active():
        run_registry.unregister(live.run_id)


@pytest.fixture
def admin() -> Principal:
    return Principal(id="admin-f8", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)


def _engine(fake_model, worker_script: List[Any], checker_script: List[Any]) -> AgentEngine:
    worker = fake_model.adapter(worker_script)
    engine = AgentEngine(
        model_provider=worker,
        checker_provider=fake_model.checker(checker_script),
        runtime=AgentRuntime(),
    )
    engine.model_requests = worker._client.responses.requests
    return engine


def _snapshot(db_session_factory, run_id: str) -> Dict[str, Any]:
    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).one()
        return json.loads(row.input_data)


def _children(db_session_factory, parent_run_id: str) -> List[Dict[str, Any]]:
    with db_session_factory() as db:
        rows = db.query(DbAgentRun).all()
        snapshots = [json.loads(row.input_data) for row in rows]
    return [item for item in snapshots if item.get("parent_run_id") == parent_run_id]


def _tool_names(request: Dict[str, Any]) -> List[str]:
    return sorted(tool["name"] for tool in request.get("tools") or [])


def _tool_outputs(request: Dict[str, Any]) -> List[str]:
    return [
        item["output"]
        for item in request["input"]
        if item.get("type") == "function_call_output"
    ]


def _outcome(output: str) -> Dict[str, Any]:
    # The answer is untrusted for the parent, so it arrives wrapped.
    assert output.startswith("[UNTRUSTED CONTENT]")
    return json.loads(output[output.index("{\"subagent_run_id\""): output.rindex("}") + 1])


def _verdict(decision: str, instruction: str = "") -> Any:
    payload: Dict[str, Any] = {"decision": decision, "issues": []}
    if instruction:
        payload["retry_instruction"] = instruction
    return SimpleNamespace(id="resp_v", output_text=json.dumps(payload), output=[], usage=None)


# ==============================================================================
# DELEGATION
# ==============================================================================


async def test_delegate_task_runs_a_checked_subagent(skills, admin, fake_model, db_session_factory):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call(
                "call_d",
                "delegate_task",
                {"task": "Summarise the notes.", "role": "research"},
            ),
            fake_model.text("Three notes, all about the garden."),
            fake_model.text("The notes are about the garden."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate a summary of my notes.", principal=admin)

    assert result["messages"][0].content == "The notes are about the garden."

    # The parent sees the subagent's checked answer as the tool's output.
    outcome = _outcome(_tool_outputs(engine.model_requests[2])[0])
    assert outcome["status"] == "completed"
    assert outcome["role"] == "research"
    assert outcome["answer"] == "Three notes, all about the garden."

    # The run tree: the subagent keeps its parent and its role.
    children = _children(db_session_factory, result["run_id"])
    assert [child["run_id"] for child in children] == [outcome["subagent_run_id"]]
    assert children[0]["current_state"]["worker_context"]["task"]["role"] == "research"
    assert children[0]["status"] == "completed"


async def test_a_subagent_never_sees_the_delegation_tool(skills, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Write a note."}),
            fake_model.text("Done."),
            fake_model.text("All done."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    await engine.run(session_id=SESSION_ID, task="Delegate writing a note.", principal=admin)

    assert "delegate_task" in _tool_names(engine.model_requests[0])
    assert _tool_names(engine.model_requests[1]) == ["note"]


async def test_the_subagent_cost_is_charged_to_the_parent(skills, admin, fake_model, db_session_factory):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Count the notes."}, usage=(2, 1)),
            fake_model.text("Three.", usage=(4, 1)),
            fake_model.text("You have three notes.", usage=(1, 1)),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate counting my notes.", principal=admin)

    child = _children(db_session_factory, result["run_id"])[0]
    child_cost = child["usage"]["cost"]
    assert child_cost == pytest.approx(5)

    usage = _snapshot(db_session_factory, result["run_id"])["usage"]
    assert usage["subagents"] == 1
    assert usage["subagent_cost"] == pytest.approx(child_cost)
    # The parent's own calls (3 + 2) plus its subagent.
    assert usage["cost"] == pytest.approx(5 + child_cost)

    # Without a budget the subagent gets half of what the parent had left.
    assert child["current_state"]["worker_context"]["max_cost"] == pytest.approx((100 - 3) / 2)


async def test_a_budget_asked_for_never_exceeds_what_is_left(skills, admin, fake_model, db_session_factory):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call(
                "call_d", "delegate_task", {"task": "Count the notes.", "budget_usd": 500}, usage=(2, 1)
            ),
            fake_model.text("Three."),
            fake_model.text("Three notes."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate counting my notes.", principal=admin)

    child = _children(db_session_factory, result["run_id"])[0]
    assert child["current_state"]["worker_context"]["max_cost"] == pytest.approx(97)


# ==============================================================================
# NO RUN COST CAP (AEHUB_RUN_MAX_COST=0)
# ==============================================================================


def test_an_uncapped_scope_has_no_end():
    scope = DelegationScope(
        parent_run_id="run-1",
        session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        principal=Principal(id="admin-f8", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID),
        usage={"cost": 50.0},
        max_run_cost=0,
        max_subagents=3,
    )

    assert scope.remaining() == math.inf


def test_without_a_run_cap_a_subagent_budget_is_its_cap(monkeypatch):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "0")
    assert AgentRuntime._run_limits({"max_cost": 3}).max_run_cost == 3
    assert AgentRuntime._run_limits({}).max_run_cost == 0

    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "2")
    assert AgentRuntime._run_limits({"max_cost": 3}).max_run_cost == 2


async def test_without_a_run_cap_a_subagent_gets_the_default_budget(
    skills, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "0")
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Count the notes."}, usage=(2, 1)),
            fake_model.text("Three."),
            fake_model.text("You have three notes."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate counting my notes.", principal=admin)

    assert result["messages"][0].content == "You have three notes."
    child = _children(db_session_factory, result["run_id"])[0]
    assert child["status"] == "completed"
    assert child["current_state"]["worker_context"]["max_cost"] == pytest.approx(UNCAPPED_SUBAGENT_BUDGET)


async def test_without_a_run_cap_a_subagent_gets_the_budget_it_asks_for(
    skills, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "0")
    engine = _engine(
        fake_model,
        [
            fake_model.function_call(
                "call_d", "delegate_task", {"task": "Count the notes.", "budget_usd": 500}, usage=(2, 1)
            ),
            fake_model.text("Three."),
            fake_model.text("Three notes."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate counting my notes.", principal=admin)

    child = _children(db_session_factory, result["run_id"])[0]
    assert child["status"] == "completed"
    assert child["current_state"]["worker_context"]["max_cost"] == pytest.approx(500)


async def test_without_a_run_cap_a_subagent_still_stops_at_its_budget(
    skills, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "0")
    engine = _engine(
        fake_model,
        [
            fake_model.function_call(
                "call_d", "delegate_task", {"task": "Count the notes.", "budget_usd": 2}
            ),
            fake_model.text("Three.", usage=(2, 1)),
            fake_model.text("The subagent ran out of budget."),
        ],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate counting my notes.", principal=admin)

    outcome = _outcome(_tool_outputs(engine.model_requests[2])[0])
    assert outcome["status"] == "budget_exceeded"
    assert "Run budget exhausted" in (outcome["error"] or "")
    assert outcome["cost_usd"] == pytest.approx(3)
    assert result["messages"][0].content == "The subagent ran out of budget."


async def test_delegation_is_capped_per_run(skills, admin, fake_model, db_session_factory, monkeypatch):
    monkeypatch.setenv("AEHUB_RUN_MAX_SUBAGENTS", "1")
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "delegate_task", {"task": "First part."}),
            fake_model.text("First done."),
            fake_model.function_call("call_2", "delegate_task", {"task": "Second part."}),
            fake_model.text("Only the first part was delegated."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate both parts.", principal=admin)

    assert len(_children(db_session_factory, result["run_id"])) == 1
    refused = _tool_outputs(engine.model_requests[3])[-1]
    assert "already started 1 subagents" in refused


async def test_delegation_turned_off_hides_the_tool(skills, admin, fake_model, monkeypatch):
    monkeypatch.setenv("AEHUB_RUN_MAX_SUBAGENTS", "0")
    engine = _engine(fake_model, [fake_model.text("Done myself.")], [fake_model.accept()])

    await engine.run(session_id=SESSION_ID, task="Delegate a summary of my notes.", principal=admin)

    assert _tool_names(engine.model_requests[0]) == ["note"]


async def test_a_failed_subagent_is_reported_to_its_parent(skills, admin, fake_model, db_session_factory):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Do the impossible."}),
            fake_model.text("I tried.", usage=(1, 1)),
            fake_model.text("The subagent could not do it."),
        ],
        [_verdict("FAIL", "The task cannot be done."), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate the impossible.", principal=admin)

    outcome = _outcome(_tool_outputs(engine.model_requests[2])[0])
    assert outcome["status"] == "failed"
    assert outcome["answer"] is None
    # Even a failed subagent's spend counts for the parent.
    assert outcome["cost_usd"] == pytest.approx(2)
    assert _snapshot(db_session_factory, result["run_id"])["usage"]["subagent_cost"] == pytest.approx(2)


async def test_a_member_cannot_delegate(skills, fake_model, db_session_factory):
    member = Principal(id="member-f8", role=RoleEnum.MEMBER, workspace_id=WORKSPACE_ID)
    engine = _engine(fake_model, [fake_model.text("No delegation for me.")], [fake_model.accept()])

    result = await engine.run(session_id=SESSION_ID, task="Delegate a summary of my notes.", principal=member)

    # The PolicyEngine refuses agent:invoke to a member, so the tool is hidden.
    assert "delegate_task" not in _tool_names(engine.model_requests[0])
    assert _children(db_session_factory, result["run_id"]) == []


async def test_run_detail_lists_the_subagents(skills, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Summarise the notes.", "role": "fast_worker"}),
            fake_model.text("Summary."),
            fake_model.text("Here is the summary."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate a summary of my notes.", principal=admin)

    detail = run_detail(result["run_id"], WORKSPACE_ID)
    assert [(item["role"], item["status"], item["task"]) for item in detail["subagents"]] == [
        ("fast_worker", "completed", "Summarise the notes.")
    ]

    child = run_detail(detail["subagents"][0]["run_id"], WORKSPACE_ID)
    assert child["parent_run_id"] == result["run_id"]
    assert child["subagents"] == []

    # Another workspace sees neither of them.
    assert run_detail(result["run_id"], "elsewhere") is None


def test_the_limits_view_shows_the_subagent_cap(monkeypatch):
    monkeypatch.setenv("AEHUB_RUN_MAX_SUBAGENTS", "2")
    assert limits_view(RunLimits.from_env())["max_subagents"] == 2


# ==============================================================================
# THE CRITIC'S VERDICTS IN THE TIMELINE
# ==============================================================================


async def test_critic_verdicts_carry_the_attempt_and_the_instruction(skills, admin, fake_model, monkeypatch):
    seen: List[Any] = []
    monkeypatch.setattr(events_module, "broadcast", seen.append)

    engine = _engine(
        fake_model,
        [fake_model.text("A long answer."), fake_model.text("Short.")],
        [_verdict("RETRY", "Answer in one word."), fake_model.accept()],
    )

    await engine.run(session_id=SESSION_ID, task="Say it briefly.", principal=admin)

    verdicts = [event for event in seen if event.event_type.startswith("checker.")]
    assert [(event.event_type, event.attempt) for event in verdicts] == [
        ("checker.rejected", 1),
        ("checker.accepted", 2),
    ]
    assert verdicts[0].details == {"max_attempts": 3, "retry_instruction": "Answer in one word."}
    assert verdicts[1].details == {"max_attempts": 3}


async def test_a_critic_failure_is_in_the_timeline(skills, admin, fake_model, monkeypatch):
    seen: List[Any] = []
    monkeypatch.setattr(events_module, "broadcast", seen.append)

    engine = _engine(fake_model, [fake_model.text("Nonsense.")], [_verdict("FAIL", "Cannot be fixed.")])

    await engine.run(session_id=SESSION_ID, task="Say it briefly.", principal=admin)

    failed = [event for event in seen if event.event_type == "checker.failed"]
    assert len(failed) == 1
    assert failed[0].attempt == 1
    assert failed[0].details == {"max_attempts": 3, "reason": "Cannot be fixed."}


# ==============================================================================
# THE ROLE CHOSEN FOR ONE COMMAND
# ==============================================================================


def test_a_command_role_wins_over_triage_and_the_forced_role(monkeypatch):
    monkeypatch.setenv("AEHUB_FORCE_ROLE", "architect")

    assert triage_role("What time is it?", "research") is Role.RESEARCH
    assert triage_role("What time is it?") is Role.ARCHITECT
    assert command_role("") is None
    assert command_role(" Fast_Worker ") is Role.FAST_WORKER


def test_the_critic_is_never_a_command_role():
    with pytest.raises(ValueError):
        command_role("critic")

    with pytest.raises(ValueError):
        command_role("boss")


def test_the_router_serves_the_chosen_role(fake_model):
    asked: List[Role] = []

    def provider_for(role: Role) -> Any:
        asked.append(role)
        return fake_model.adapter([])

    engine = AgentEngine(
        router=SimpleNamespace(provider_for=provider_for),
        checker_provider=fake_model.checker([]),
        runtime=AgentRuntime(),
    )
    asked.clear()

    engine.worker_for("What time is it?", "architect")
    engine.worker_for("What time is it?")

    assert asked == [Role.ARCHITECT, Role.TRIAGE]


async def test_the_chosen_role_is_kept_with_the_task(skills, admin, fake_model, db_session_factory, monkeypatch):
    seen: List[Any] = []
    monkeypatch.setattr(events_module, "broadcast", seen.append)

    engine = _engine(fake_model, [fake_model.text("Done.")], [fake_model.accept()])

    state = await engine.ainvoke(
        {
            "messages": [{"content": "Plan the week."}],
            "session_id": SESSION_ID,
            "principal": admin,
            "role": "research",
            "run_id": "run_role",
        }
    )

    assert state["messages"][0].content == "Done."
    task = _snapshot(db_session_factory, "run_role")["current_state"]["worker_context"]["task"]
    assert task["role"] == "research"

    started = next(event for event in seen if event.event_type == "run.started")
    assert started.role == "research"


async def test_an_unknown_command_role_is_refused(skills, admin, fake_model):
    engine = _engine(fake_model, [], [])

    with pytest.raises(ValueError):
        await engine.ainvoke(
            {
                "messages": [{"content": "Plan the week."}],
                "session_id": SESSION_ID,
                "principal": admin,
                "role": "critic",
            }
        )

    assert engine.model_requests == []


async def test_the_history_shows_the_tree_and_the_roles(skills, admin, fake_model):
    from app.api.runs import run_history

    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_d", "delegate_task", {"task": "Summarise the notes.", "role": "research"}),
            fake_model.text("Summary."),
            fake_model.text("Here is the summary."),
        ],
        [fake_model.accept(), fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delegate a summary of my notes.", principal=admin)

    runs = {item["run_id"]: item for item in run_history(admin)["runs"]}
    parent = runs[result["run_id"]]
    (child,) = [item for item in runs.values() if item["parent_run_id"] == result["run_id"]]

    assert child["chosen_role"] == "research"
    assert parent["chosen_role"] is None
    assert parent["usage"]["subagents"] == 1
    assert parent["usage"]["subagent_cost"] == pytest.approx(child["usage"]["cost"])
