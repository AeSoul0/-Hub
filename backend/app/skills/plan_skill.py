"""
@file backend/app/skills/plan_skill.py
@description Plans in several steps for the long tasks (N7, ADR-047).

    plan_steps  LOW  write the plan of the task: 2 to 12 short steps
    plan_step   LOW  mark one step doing, done, failed or skipped, with a note

The plan lives in the run's own state (worker_context["plan"]), saved with
the run after every tool call: a run parked on an approval, retried after
the Critic, or resumed after a restart has it again, with the steps already
done, and goes on from the first one not done. The model sees it in its
context at every turn (level L1). Every change is a "plan.updated" event,
so the Nucleo shows the plan with the state of each step.

The tools only write the plan of the run that calls them; outside a run
they refuse. Every run sees them (tool_selection.ALWAYS_TOOLS).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List

from app.agent_engine.delegation import current_delegation_scope

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata

MAX_STEPS = 12
MIN_STEPS = 2
MAX_STEP_CHARS = 200
MAX_NOTE_CHARS = 300
STATUSES = ("pending", "doing", "done", "failed", "skipped")
# A step in one of these needs nothing more.
FINISHED = ("done", "skipped")


def _plan() -> Dict[str, Any]:
    scope = current_delegation_scope()
    if scope.plan is None:
        raise PermissionError("This run keeps no plan.")
    return scope.plan


def _publish(plan: Dict[str, Any]) -> None:
    from app.agent_engine.events import EventDispatcher

    scope = current_delegation_scope()
    EventDispatcher().dispatch(
        "plan.updated",
        run_id=scope.parent_run_id,
        session_id=scope.session_id,
        workspace_id=scope.workspace_id,
        details={"steps": plan.get("steps", [])},
    )


def render(plan: Dict[str, Any]) -> str:
    """The plan as the model reads it: one line per step, with its state."""
    lines = []
    for number, step in enumerate(plan.get("steps") or [], start=1):
        note = f" — {step['note']}" if step.get("note") else ""
        lines.append(f"{number}. [{step.get('status', 'pending')}] {step.get('text', '')}{note}")
    pending = next_step(plan)
    if pending:
        lines.append(f"Go on with step {pending}.")
    elif lines:
        lines.append("Every step is finished: give the final answer.")
    return "\n".join(lines)


def next_step(plan: Dict[str, Any]) -> int:
    """The number of the first step not finished, or 0."""
    for number, step in enumerate(plan.get("steps") or [], start=1):
        if step.get("status") not in FINISHED:
            return number
    return 0


async def plan_steps(steps: List[str]) -> str:
    """
    Write the plan of a task that needs several steps; a step already done keeps its state.
    """
    texts = [" ".join(str(step).split())[:MAX_STEP_CHARS] for step in steps if str(step).strip()]
    if not MIN_STEPS <= len(texts) <= MAX_STEPS:
        raise ValueError(f"A plan has {MIN_STEPS} to {MAX_STEPS} steps.")
    plan = _plan()
    before = {step.get("text"): step for step in plan.get("steps") or []}
    plan["steps"] = [
        {
            "text": text,
            "status": before.get(text, {}).get("status", "pending"),
            "note": before.get(text, {}).get("note", ""),
        }
        for text in texts
    ]
    plan["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    _publish(plan)
    return "Plan saved.\n" + render(plan)


async def plan_step(step: int, status: str, note: str = "") -> str:
    """
    Mark step N of the plan: doing, done, failed or skipped, with a short note of the result.
    """
    plan = _plan()
    steps = plan.get("steps") or []
    if not steps:
        raise ValueError("There is no plan yet: write it with plan_steps.")
    if not 1 <= step <= len(steps):
        raise ValueError(f"The plan has steps 1 to {len(steps)}.")
    if status not in STATUSES[1:]:
        raise ValueError(f"The state is one of {', '.join(STATUSES[1:])}.")
    steps[step - 1]["status"] = status
    steps[step - 1]["note"] = " ".join(note.split())[:MAX_NOTE_CHARS]
    plan["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    _publish(plan)
    return render(plan)


TOOLS = [plan_steps, plan_step]


class PlanSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="plan",
            description="A plan in steps for the long tasks, saved with the run and shown in the Nucleo.",
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable[..., Any]]:
        return list(TOOLS)

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        def meta(name: str, description: str, properties: Dict[str, Any], required: List[str], examples: List[str]) -> ToolMetadata:
            return ToolMetadata(
                name=name,
                examples=examples,
                description=description,
                risk_level=RiskLevel.LOW,
                permissions_required=["tool:execute:safe"],
                max_runtime=5,
                max_output=3000,
                # They change the plan: a cached answer would skip the change.
                idempotent=False,
                input_schema={"type": "object", "properties": properties, "required": required, "additionalProperties": False},
                output_schema={"type": "string"},
            )

        return {
            "plan_steps": meta(
                "plan_steps",
                (
                    "For a task that needs several steps (more than about three tool calls, or several "
                    "things to do), write its plan first: 2 to 12 short steps. Then do them in order and "
                    "mark each with plan_step. Not for a simple question."
                ),
                {"steps": {"type": "array", "minItems": MIN_STEPS, "maxItems": MAX_STEPS, "items": {"type": "string", "minLength": 1, "maxLength": MAX_STEP_CHARS}}},
                ["steps"],
                ["piano", "passi", "plan", "steps"],
            ),
            "plan_step": meta(
                "plan_step",
                "Mark step N of the plan: doing when you start it, done (or failed, skipped) when it ends, with a short note of the result.",
                {
                    "step": {"type": "integer", "minimum": 1, "maximum": MAX_STEPS},
                    "status": {"type": "string", "enum": list(STATUSES[1:])},
                    "note": {"type": "string", "maxLength": MAX_NOTE_CHARS},
                },
                ["step", "status"],
                ["passo fatto", "step done"],
            ),
        }


def get_skill() -> BaseSkill:
    return PlanSkill()


__all__ = ["FINISHED", "PlanSkill", "STATUSES", "get_skill", "next_step", "plan_step", "plan_steps", "render"]
