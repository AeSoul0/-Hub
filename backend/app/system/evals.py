"""
@file backend/app/system/evals.py
@description The evaluation suite started from the interface (F9, ADR-030).

The suite patches process-wide state (database sessions, the skill registry,
the event bus, the environment), so it never runs inside the API: it runs in
a child Python process, offline (scripted models, in-memory database, no
network and no cost), with the provider keys and the database URL removed
from its environment. One run at a time; the last result stays in memory
until a restart.

With evals/baseline.json next to the backend (a source checkout) the run is
the release gate; without it (the desktop bundle) it only reports.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_PATH = BACKEND_DIR.parent / "evals" / "baseline.json"
EVAL_TIMEOUT_SECONDS = 900
OUTPUT_CHARS = 4000

# Run in the child: the same entry as evals/run_evals.py.
_CHILD = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from app.evaluation.engine import run; sys.exit(run(sys.argv[2:]))"
)

# Never passed to the child: keys, tokens, passwords and URLs that hold them.
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|_URL)$", re.IGNORECASE)

_OFFLINE_ENV = {
    "GROQ_API_KEY": "offline-eval",
    "POSTGRES_URL": "postgresql://offline-eval@localhost:5432/offline-eval",
    "AEHUB_CHECKER_MODEL": "eval-critic",
    "AEHUB_TELEMETRY_CONSOLE": "0",
    "AEHUB_EVENT_BUS": "memory",
    "REDIS_URL": "memory://",
}


@dataclass
class EvalRun:
    status: str = "idle"  # idle, running, passed, failed, error
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    started_by: Optional[str] = None
    gate: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    cases: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    error: Optional[str] = None


_state = EvalRun()
_lock = threading.Lock()
# The background run, kept so it is not garbage collected mid-way.
_tasks: set = set()


def child_environment() -> Dict[str, str]:
    env = {name: value for name, value in os.environ.items() if not _SECRET_NAME.search(name)}
    env.update(_OFFLINE_ENV)
    # Settings() needs a login key; the child's own, thrown away.
    env["AEHUB_SECRET_KEY"] = secrets.token_urlsafe(32)
    return env


def _gate_problems(output: str) -> List[str]:
    if "RELEASE GATE FAILED:" not in output:
        return []

    tail = output.split("RELEASE GATE FAILED:", 1)[1]
    return [line.strip()[2:] for line in tail.splitlines() if line.strip().startswith("- ")]


def _summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "metrics": report.get("metrics") or {},
        "cases": [
            {
                "id": case.get("id"),
                "category": case.get("category"),
                "passed": bool(case.get("passed")),
                "critical": bool(case.get("critical")),
                "status": case.get("status"),
                "cost": case.get("cost"),
                "failures": list(case.get("failures") or []),
            }
            for case in report.get("cases") or []
        ],
    }


def run_suite_in_child(baseline: Optional[Path] = BASELINE_PATH) -> EvalRun:
    """
    Run the offline suite in a child process and read its JSON report.
    """
    gate = baseline is not None and baseline.is_file()
    result = EvalRun(gate=gate)

    with tempfile.TemporaryDirectory() as folder:
        report_path = Path(folder) / "report.json"
        args = ["--report", str(report_path)]

        if gate:
            args += ["--baseline", str(baseline)]

        try:
            done = subprocess.run(
                [sys.executable, "-c", _CHILD, str(BACKEND_DIR), *args],
                cwd=str(BACKEND_DIR),
                env=child_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=EVAL_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            result.status = "error"
            result.error = f"The suite did not finish in {EVAL_TIMEOUT_SECONDS} seconds."
            return result

        output = (done.stdout or "") + (done.stderr or "")

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result.status = "error"
            result.error = output[-OUTPUT_CHARS:] or f"The suite exited with code {done.returncode}."
            return result

    summary = _summary(report)
    result.metrics = summary["metrics"]
    result.cases = summary["cases"]
    result.problems = _gate_problems(output)
    result.status = "passed" if done.returncode == 0 else "failed"
    return result


def current() -> Dict[str, Any]:
    with _lock:
        return {**asdict(_state), "baseline": BASELINE_PATH.is_file()}


def _finish(outcome: EvalRun, started: EvalRun) -> None:
    global _state

    outcome.started_at = started.started_at
    outcome.started_by = started.started_by
    outcome.finished_at = datetime.utcnow().isoformat()

    with _lock:
        _state = outcome


async def start(principal_id: str) -> Dict[str, Any]:
    """
    Start a run in the background; RuntimeError while one is running.
    """
    global _state

    with _lock:
        if _state.status == "running":
            raise RuntimeError("An evaluation is already running.")

        _state = EvalRun(
            status="running",
            started_at=datetime.utcnow().isoformat(),
            started_by=principal_id,
            gate=BASELINE_PATH.is_file(),
        )
        started = _state

    async def work() -> None:
        try:
            outcome = await asyncio.to_thread(run_suite_in_child)
        except Exception as exc:
            outcome = EvalRun(status="error", error=f"{type(exc).__name__}: {exc}")

        _finish(outcome, started)

    task = asyncio.get_running_loop().create_task(work())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return current()


__all__ = ["BASELINE_PATH", "EvalRun", "child_environment", "current", "run_suite_in_child", "start"]
