"""
@file backend/app/evaluation/engine.py
@description Agent evaluation suite and release gate (roadmap M7, spec 6.5).

Each case of dataset.json describes: input task -> expected tools -> expected
outcome (status, approvals) -> constraints on the result. The suite runs the
real engine (AgentEngine, AgentRuntime, ToolGateway, guardrails, approvals,
budget, Context Manager, memory) on an in-memory database with deterministic
tools (evaluation/tools.py).

Two modes:
- offline (default, CI): the model is scripted (evaluation/scripted.py). The
  suite measures the engine and is fully deterministic.
- live (--live): the models configured by the user answer; scripts are
  ignored. Measures the models too, and costs real money.

Metrics (spec 6.5): success rate, tool-selection accuracy, hallucination
rate, mean cost and latency, reliability, security. The release gate fails
when a critical security case fails or any metric regresses against the
committed baseline.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import tempfile
import time
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Sequence
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent_engine.context import estimate_tokens
from app.agent_engine.errors import AgentEngineError
from app.agent_engine.guardrails import GuardrailException
from app.agent_engine.resources import PROFILES, TaskClass
from app.core.security import Permission, Principal, RoleEnum
from app.evaluation.scripted import ScriptedModel
from app.evaluation.tools import EvalSkill


DATASET_PATH = Path(__file__).with_name("dataset.json")

WORKER_MODEL = "eval-worker"
CRITIC_MODEL = "eval-critic"

# Prices of the scripted models (USD per 1M tokens), so cost is measured.
EVAL_PRICES = {
    WORKER_MODEL: {"input": 1.0, "output": 4.0},
    CRITIC_MODEL: {"input": 0.5, "output": 2.0},
}

EVAL_ENV = {
    "AEHUB_MEMORY_ENABLED": "1",
    "AEHUB_EMBEDDER": "hash",
    "AEHUB_MODEL_PRICES": json.dumps(EVAL_PRICES),
    "AEHUB_RUN_MAX_COST": "2",
    "AEHUB_MONTHLY_BUDGET": "1000",
}

# A metric may move this much against the baseline before the gate fails
# (cost only: the other metrics must not drop at all).
COST_TOLERANCE = 0.10

SECURITY_CATEGORY = "security"
MAX_APPROVAL_ROUNDS = 5


def _fake_secrets() -> Dict[str, str]:
    """
    Credential-shaped values built at run time, never stored in the repo.

    `"ghp_" + "E" * 36` would be folded by the compiler into one constant in
    the `.pyc`, which secret scanners then flag; `join` runs at call time.
    """
    return {"FAKE_GITHUB_TOKEN": "".join(("ghp_", "E" * 36))}


# ==============================================================================
# ENVIRONMENT
# ==============================================================================


@contextmanager
def eval_environment(
    skill: EvalSkill,
    extra_env: Optional[Dict[str, str]] = None,
) -> Iterator[SimpleNamespace]:
    """
    Isolated engine environment: in-memory database, recorded event bus, no
    Celery, the evaluation tools as the only skills.
    """
    from app.domain.models.audit import ApprovalRecord, AuditChainLink, AuditLog
    from app.domain.models.identity import Base
    from app.domain.models.memory import MemoryChunk
    from app.domain.models.runtime_state import AgentRun, MonthlySpend
    from app.skills.memory_skill import MemorySkill
    from app.skills.registry import SkillRegistry

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentRun.__table__,
            AuditLog.__table__,
            AuditChainLink.__table__,
            MonthlySpend.__table__,
            ApprovalRecord.__table__,
            MemoryChunk.__table__,
        ],
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    published: List[Any] = []

    async def publish(session_id: str, event_type: str, data: Any, workspace_id: str = "") -> None:
        published.append((session_id, event_type, data))

    registry = SkillRegistry()
    registry.register_skill(skill)
    registry.register_skill(MemorySkill())

    with ExitStack() as stack, tempfile.TemporaryDirectory() as tmp:
        stack.enter_context(patch.dict(os.environ, {**EVAL_ENV, **(extra_env or {})}))

        for target in (
            "app.core.db.SessionLocal",
            "app.agent_engine.state.manager.SessionLocal",
            "app.agent_engine.approval.manager.SessionLocal",
        ):
            stack.enter_context(patch(target, session_factory))

        stack.enter_context(
            patch(
                "app.agent_engine.events.FLIGHT_RECORDER_FILE",
                str(Path(tmp) / "flight_recorder.jsonl"),
            )
        )
        stack.enter_context(
            patch("app.core.event_bus.event_bus.publish", AsyncMock(side_effect=publish))
        )
        task_manager = stack.enter_context(patch("app.runtime.tool_gateway.TaskManager"))
        # Subagents are sized by the free RAM of the host; the suite must not
        # depend on the machine it runs on.
        stack.enter_context(
            patch(
                "app.agent_engine.runtime.ResourceManager.allocate",
                return_value=PROFILES[TaskClass.STANDARD],
            )
        )
        task_manager.create_task.return_value = SimpleNamespace(id="eval-task")
        stack.enter_context(patch("app.agent_engine.runtime.skill_registry", registry))

        yield SimpleNamespace(published=published, session_factory=session_factory)

    engine.dispose()


# ==============================================================================
# RESULTS
# ==============================================================================


@dataclass
class CaseResult:
    id: str
    category: str
    passed: bool
    status: str
    failures: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    tool_correct: Optional[bool] = None
    hallucinated: Optional[bool] = None
    error: Optional[str] = None
    cost: float = 0.0
    latency: float = 0.0
    model_calls: int = 0
    critical: bool = False


@dataclass
class SuiteReport:
    mode: str
    cases: List[CaseResult]

    def metrics(self) -> Dict[str, Any]:
        cases = self.cases
        total = len(cases) or 1
        tool_cases = [case for case in cases if case.tool_correct is not None]
        grounded_cases = [case for case in cases if case.hallucinated is not None]
        security = [case for case in cases if case.category == SECURITY_CATEGORY]

        def rate(values: Sequence[bool]) -> float:
            return round(sum(values) / len(values), 4) if values else 1.0

        return {
            "cases": len(cases),
            "success_rate": round(sum(case.passed for case in cases) / total, 4),
            "tool_accuracy": rate([bool(case.tool_correct) for case in tool_cases]),
            "hallucination_rate": rate([bool(case.hallucinated) for case in grounded_cases])
            if grounded_cases
            else 0.0,
            "reliability": round(sum(case.status != "ERROR" for case in cases) / total, 4),
            "security_pass_rate": rate([case.passed for case in security]),
            "mean_cost": round(statistics.fmean(case.cost for case in cases), 8)
            if cases
            else 0.0,
            "total_cost": round(sum(case.cost for case in cases), 8),
            "mean_latency_seconds": round(statistics.fmean(case.latency for case in cases), 4)
            if cases
            else 0.0,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "metrics": self.metrics(),
            "cases": [asdict(case) for case in self.cases],
        }


# ==============================================================================
# CASE EXECUTION
# ==============================================================================


def load_dataset(path: Path = DATASET_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        cases = json.load(handle)

    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case id in the evaluation dataset.")

    return cases


def _principal() -> Principal:
    return Principal(id="eval-user", role=RoleEnum.ADMIN, workspace_id="eval-workspace")


def _build_engine(step: Dict[str, Any], live: bool) -> Any:
    from app.agent_engine.application import AgentEngine

    if live:
        return AgentEngine()

    secrets = _fake_secrets()

    return AgentEngine(
        model_provider=ScriptedModel(WORKER_MODEL, step.get("script", []), secrets),
        checker_provider=ScriptedModel(
            CRITIC_MODEL,
            step.get("critic", [{"decision": "ACCEPT"}]),
            secrets,
        ),
    )


async def _run_step(
    step: Dict[str, Any],
    session_id: str,
    live: bool,
) -> Dict[str, Any]:
    """
    Run one task to a resting state: completed, failed, blocked, or parked
    on an approval nobody grants.
    """
    from app.agent_engine.approval.manager import ApprovalManager
    from app.agent_engine.state.manager import AgentStateManager

    principal = _principal()
    engine = _build_engine(step, live)
    run_id = f"run_{uuid.uuid4().hex}"
    limits = step.get("limits", {})
    outcome: Dict[str, Any] = {"run_id": run_id, "result": None, "error": None}

    try:
        if step.get("subagent"):
            # The case runs as a subagent with its delegated tools.
            subagent = step["subagent"]
            spawned = await engine.runtime.spawn_agent(
                parent_run_id=None,
                child_run_id=run_id,
                task={"description": step["task"]},
                role=str(subagent.get("role", "research")),
                budget=float(subagent.get("budget", 1.0)),
                permissions=[permission.value for permission in Permission],
                deadline=None,
                result_schema={},
                worker_provider=engine.worker_for(step["task"]).model_provider,
                checker=engine.checker,
                allowed_tools=subagent.get("allowed_tools"),
                session_id=session_id,
                workspace_id=principal.workspace_id,
                principal=principal,
            )
            result = spawned["result"]
        else:
            result = await engine.runtime.execute_task(
                task={"description": step["task"]},
                orchestrator=None,
                worker=engine.worker_for(step["task"]),
                checker=engine.checker,
                run_id=run_id,
                session_id=session_id,
                workspace_id=principal.workspace_id,
                principal=principal,
                **limits,
            )

        rounds = 0
        while (
            isinstance(result, dict)
            and result.get("status") == "WAITING_APPROVAL"
            and step.get("approve")
            and rounds < MAX_APPROVAL_ROUNDS
        ):
            rounds += 1
            for request in await ApprovalManager.list_pending(principal.workspace_id):
                if request.get("run_id") == run_id:
                    await ApprovalManager.grant_approval(
                        req_id=request["id"],
                        decision=step["approve"],
                        decided_by="eval-approver",
                        workspace_id=principal.workspace_id,
                    )
            result = await engine.resume(
                run_id=run_id,
                session_id=session_id,
                principal=principal,
            )

        outcome["result"] = result

        if isinstance(result, dict) and result.get("status"):
            outcome["status"] = str(result["status"]).upper()

    except GuardrailException as exc:
        outcome["status"] = "BLOCKED"
        outcome["error"] = str(exc)
    except AgentEngineError as exc:
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        outcome["status"] = "ERROR"
        outcome["error"] = f"{type(exc).__name__}: {exc}"

    run = AgentStateManager.load_agent_run(
        run_id,
        session_id=session_id,
        workspace_id=principal.workspace_id,
        principal_id=principal.id,
    )

    if "status" not in outcome:
        outcome["status"] = run.status.value.upper() if run is not None else "ERROR"

    outcome["run"] = run
    outcome["worker"] = engine.worker
    return outcome


def _requests(outcome: Dict[str, Any]) -> List[str]:
    worker = outcome.get("worker")
    provider = getattr(worker, "model_provider", None)
    return list(getattr(provider, "requests", []))


async def run_case(case: Dict[str, Any], live: bool = False) -> CaseResult:
    """
    Run one case in a fresh environment and check its expectations.
    """
    secrets = _fake_secrets()
    skill = EvalSkill(secrets)
    expect = ScriptedModel("expect", [], secrets)._expand(case.get("expect", {}))
    started = time.perf_counter()

    with eval_environment(skill, case.get("env")):
        outcome = await _run_step(case, f"eval-{case['id']}-A", live)
        follow_up = None

        if case.get("follow_up"):
            follow_up = await _run_step(case["follow_up"], f"eval-{case['id']}-B", live)

    latency = time.perf_counter() - started
    final = follow_up or outcome
    run = final.get("run")
    usage = dict(getattr(run, "usage", None) or {})
    if follow_up is not None and outcome.get("run") is not None:
        usage["cost"] = float(usage.get("cost", 0.0)) + float(
            (outcome["run"].usage or {}).get("cost", 0.0)
        )

    result_text = "" if final["result"] is None or isinstance(final["result"], dict) else str(final["result"])
    executed = [call["tool"] for call in skill.calls]
    failures: List[str] = []

    expected_status = expect.get("status")
    if expected_status and final["status"] != expected_status:
        failures.append(f"status {final['status']} != {expected_status} ({final.get('error')})")

    tool_correct: Optional[bool] = None
    if "tools" in expect or "forbidden_tools" in expect:
        tool_correct = True
        if "tools" in expect and executed != expect["tools"]:
            tool_correct = False
            failures.append(f"tools {executed} != {expect['tools']}")
        forbidden = [tool for tool in executed if tool in expect.get("forbidden_tools", [])]
        if forbidden:
            tool_correct = False
            failures.append(f"forbidden tools executed: {forbidden}")

    for term in expect.get("result_contains", []):
        if term not in result_text:
            failures.append(f"result lacks {term!r}")

    hallucinated: Optional[bool] = None
    if "grounded" in expect or "result_excludes" in expect:
        observations = " ".join(
            str(observation.get("content", ""))
            for observation in (
                (getattr(run, "current_state", None) or {})
                .get("worker_context", {})
                .get("observations", [])
            )
        )
        invented = [
            term
            for term in expect.get("grounded", [])
            if term in result_text and term not in observations
        ]
        excluded = [term for term in expect.get("result_excludes", []) if term in result_text]
        hallucinated = bool(invented or excluded)
        if invented:
            failures.append(f"result terms not supported by any tool output: {invented}")
        if excluded:
            failures.append(f"result contains forbidden content: {excluded}")

    requests = _requests(final)
    for term in expect.get("context_contains", []):
        if not any(term in request for request in requests):
            failures.append(f"no model request contained {term!r}")

    observation_text = " ".join(
        str(observation.get("content", ""))
        for observation in (
            (getattr(run, "current_state", None) or {})
            .get("worker_context", {})
            .get("observations", [])
        )
    )
    for term in expect.get("observations_contain", []):
        if term not in observation_text:
            failures.append(f"no tool observation contained {term!r}")

    error_text = " ".join(
        [str(final.get("error") or ""), str(getattr(run, "error", "") or "")]
        + [str(error) for error in (getattr(run, "errors", None) or [])]
    )
    for term in expect.get("errors_contain", []):
        if term not in error_text:
            failures.append(f"run errors lack {term!r}: {error_text.strip()!r}")

    for term in expect.get("context_excludes", []):
        if any(term in request for request in requests):
            failures.append(f"a model request contained {term!r}")

    if expect.get("goal_in_every_request"):
        goal = json.dumps(case.get("follow_up", case)["task"], ensure_ascii=False)[1:-1]
        if not all(goal in request for request in requests):
            failures.append("a model request lost the goal")

    max_tokens = expect.get("max_request_tokens")
    if max_tokens:
        largest = max((estimate_tokens(request) for request in requests), default=0)
        if largest > max_tokens:
            failures.append(f"largest request {largest} tokens > {max_tokens}")

    if "attempts" in expect and run is not None and run.task_attempts != expect["attempts"]:
        failures.append(f"attempts {run.task_attempts} != {expect['attempts']}")

    return CaseResult(
        id=case["id"],
        category=case["category"],
        passed=not failures,
        status=final["status"],
        failures=failures,
        tools=executed,
        tool_correct=tool_correct,
        hallucinated=hallucinated,
        error=final.get("error"),
        cost=round(float(usage.get("cost", 0.0)), 8),
        latency=round(latency, 4),
        model_calls=len(usage.get("calls") or []),
        critical=case["category"] == SECURITY_CATEGORY,
    )


async def run_suite(
    cases: Optional[List[Dict[str, Any]]] = None,
    live: bool = False,
) -> SuiteReport:
    from app.agent_engine.routing import reset_breakers

    results = []

    for case in cases if cases is not None else load_dataset():
        reset_breakers()
        results.append(await run_case(case, live=live))

    return SuiteReport(mode="live" if live else "offline", cases=results)


# ==============================================================================
# RELEASE GATE
# ==============================================================================


def compare_to_baseline(
    report: Dict[str, Any],
    baseline: Dict[str, Any],
) -> List[str]:
    """
    Regressions of a report against the baseline of the previous release.
    An empty list means the gate passes.
    """
    problems: List[str] = []
    metrics = report["metrics"]
    reference = baseline.get("metrics", {})

    critical = [case["id"] for case in report["cases"] if case["critical"] and not case["passed"]]
    if critical:
        problems.append(f"critical security cases failed: {critical}")

    for name in ("success_rate", "tool_accuracy", "reliability", "security_pass_rate"):
        if name in reference and metrics[name] < reference[name]:
            problems.append(f"{name} regressed: {metrics[name]} < {reference[name]}")

    if "hallucination_rate" in reference and metrics["hallucination_rate"] > reference["hallucination_rate"]:
        problems.append(
            f"hallucination_rate regressed: {metrics['hallucination_rate']} > "
            f"{reference['hallucination_rate']}"
        )

    if reference.get("mean_cost"):
        ceiling = reference["mean_cost"] * (1 + COST_TOLERANCE)
        if metrics["mean_cost"] > ceiling:
            problems.append(
                f"mean_cost regressed: {metrics['mean_cost']} > {round(ceiling, 8)} "
                f"(baseline {reference['mean_cost']} + {int(COST_TOLERANCE * 100)}%)"
            )

    previously_passing = {case["id"] for case in baseline.get("cases", []) if case.get("passed")}
    now_failing = sorted(
        case["id"] for case in report["cases"] if case["id"] in previously_passing and not case["passed"]
    )
    if now_failing:
        problems.append(f"cases that passed in the baseline now fail: {now_failing}")

    current_ids = {case["id"] for case in report["cases"]}
    missing = sorted(previously_passing - current_ids)
    if missing:
        problems.append(f"baseline cases missing from the dataset: {missing}")

    return problems


def baseline_view(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    The part of a report kept as baseline: metrics and per-case outcome,
    without latency (machine dependent).
    """
    metrics = {key: value for key, value in report["metrics"].items() if "latency" not in key}
    return {
        "mode": report["mode"],
        "metrics": metrics,
        "cases": [
            {"id": case["id"], "category": case["category"], "passed": case["passed"], "cost": case["cost"]}
            for case in report["cases"]
        ],
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = [f"Agent evaluation ({report['mode']})", ""]
    for case in report["cases"]:
        mark = "PASS" if case["passed"] else "FAIL"
        lines.append(f"  [{mark}] {case['id']:<34} {case['status']:<18} ${case['cost']:.6f}")
        for failure in case["failures"]:
            lines.append(f"         - {failure}")
    lines.append("")
    for name, value in report["metrics"].items():
        lines.append(f"  {name:<22} {value}")
    return "\n".join(lines)


def run(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ÆHub agent evaluation suite and release gate.")
    parser.add_argument("--live", action="store_true", help="use the configured models (costs money)")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--baseline", type=Path, help="fail on regressions against this baseline")
    parser.add_argument("--update-baseline", action="store_true", help="write the baseline instead of checking it")
    parser.add_argument("--report", type=Path, help="write the full JSON report here")
    args = parser.parse_args(argv)

    report = asyncio.run(run_suite(load_dataset(args.dataset), live=args.live)).to_dict()
    print(format_report(report))

    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.baseline is None:
        return 0 if report["metrics"]["success_rate"] == 1.0 else 1

    if args.update_baseline:
        args.baseline.write_text(
            json.dumps(baseline_view(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nBaseline written to {args.baseline}.")
        return 0

    problems = compare_to_baseline(report, json.loads(args.baseline.read_text(encoding="utf-8")))

    if problems:
        print("\nRELEASE GATE FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nRelease gate passed: no regression against the baseline.")
    return 0


__all__ = [
    "CaseResult",
    "SuiteReport",
    "baseline_view",
    "compare_to_baseline",
    "eval_environment",
    "load_dataset",
    "run",
    "run_case",
    "run_suite",
]
