"""
@file tests/agent_engine/test_evals.py
@description Agent evaluation suite and release gate (roadmap M7).

The full offline suite runs as its own CI step (evals/run_evals.py against
evals/baseline.json). These tests cover the gate logic and prove that the
suite catches a real engine regression.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.evaluation.engine import (
    DATASET_PATH,
    baseline_view,
    compare_to_baseline,
    load_dataset,
    run_case,
    run_suite,
)


BASELINE_PATH = Path(__file__).resolve().parents[2] / "evals" / "baseline.json"


def _case(case_id: str) -> dict:
    return next(case for case in load_dataset() if case["id"] == case_id)


@pytest.fixture
def report() -> dict:
    return {
        "mode": "offline",
        "metrics": {
            "cases": 2,
            "success_rate": 1.0,
            "tool_accuracy": 1.0,
            "hallucination_rate": 0.0,
            "reliability": 1.0,
            "security_pass_rate": 1.0,
            "mean_cost": 0.01,
            "total_cost": 0.02,
            "mean_latency_seconds": 0.1,
        },
        "cases": [
            {"id": "a", "category": "success", "passed": True, "critical": False, "cost": 0.01},
            {"id": "s", "category": "security", "passed": True, "critical": True, "cost": 0.01},
        ],
    }


def test_dataset_is_well_formed():
    cases = load_dataset(DATASET_PATH)
    categories = {case["category"] for case in cases}

    assert len(cases) >= 25
    assert {"success", "tool_selection", "hallucination", "reliability", "hitl",
            "security", "memory", "long_context", "budget"} <= categories
    assert all(case.get("expect") for case in cases)


def test_committed_baseline_covers_the_dataset():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert {case["id"] for case in baseline["cases"]} == {case["id"] for case in load_dataset()}
    assert baseline["metrics"]["security_pass_rate"] == 1.0


def test_identical_report_passes(report):
    assert compare_to_baseline(report, baseline_view(report)) == []


def test_failed_security_case_blocks_the_release(report):
    baseline = baseline_view(report)
    report["cases"][1]["passed"] = False
    report["metrics"]["security_pass_rate"] = 0.0

    problems = compare_to_baseline(report, baseline)

    assert any("critical security cases failed: ['s']" in problem for problem in problems)


def test_metric_regressions_are_reported(report):
    baseline = baseline_view(report)
    worse = copy.deepcopy(report)
    worse["metrics"].update(success_rate=0.5, tool_accuracy=0.9, hallucination_rate=0.1)
    worse["cases"][0]["passed"] = False

    problems = " ".join(compare_to_baseline(worse, baseline))

    assert "success_rate regressed" in problems
    assert "tool_accuracy regressed" in problems
    assert "hallucination_rate regressed" in problems
    assert "now fail: ['a']" in problems


def test_cost_has_a_ten_percent_tolerance(report):
    baseline = baseline_view(report)

    report["metrics"]["mean_cost"] = 0.0109
    assert compare_to_baseline(report, baseline) == []

    report["metrics"]["mean_cost"] = 0.0111
    assert any("mean_cost regressed" in problem for problem in compare_to_baseline(report, baseline))


def test_removing_a_case_does_not_hide_a_regression(report):
    baseline = baseline_view(report)
    report["cases"] = report["cases"][:1]

    assert any("missing from the dataset: ['s']" in problem for problem in compare_to_baseline(report, baseline))


async def test_suite_catches_a_disabled_guardrail():
    """
    Regression drill: with the input guardrail switched off, the direct
    injection case no longer ends BLOCKED and the gate fails.
    """
    case = _case("security-direct-injection")
    assert (await run_case(case)).passed

    with patch("app.agent_engine.guardrails.InputGuardrail.DISALLOWED", []):
        broken = await run_suite([case])

    report = broken.to_dict()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline["cases"] = [entry for entry in baseline["cases"] if entry["id"] == case["id"]]

    assert not report["cases"][0]["passed"]
    assert any("critical security cases failed" in problem for problem in compare_to_baseline(report, baseline))


async def test_suite_catches_an_unapproved_high_tool():
    """
    Regression drill: if HIGH tools stopped asking for approval, the email
    would be sent and the case fails.
    """
    from app.evaluation import tools as eval_tools

    case = _case("grounding-no-false-claim-of-action")

    # Make send_email look harmless to the policy: no approval, LOW risk.

    original = eval_tools.EvalSkill.get_tool_metadata

    def harmless(self):
        metadata = original(self)
        metadata["send_email"] = metadata["send_email"].model_copy(
            update={"risk_level": eval_tools.RiskLevel.LOW, "requires_approval": False}
        )
        return metadata

    with patch.object(eval_tools.EvalSkill, "get_tool_metadata", harmless):
        result = await run_case(case)

    assert not result.passed
    assert "send_email" in result.tools
