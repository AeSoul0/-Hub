"""
@file evals/certify_100_100.py
@description Deterministic CI certification gate for A.U.R.O.R.A.

The certification step must fail when foundational security and reliability
invariants are missing. It is intentionally independent from external services
and does not silently return success.

The full runtime test suite remains the primary behavioral gate. This script
adds a fast structural certification layer for critical architecture rules.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "backend/app/core/security.py",
    "backend/app/core/db.py",
    "backend/app/core/database.py",
    "backend/app/domain/models/identity.py",
    "backend/app/domain/models/runtime_state.py",
    "backend/app/agent_engine/models.py",
    "backend/app/agent_engine/checker.py",
    "backend/app/agent_engine/state/manager.py",
    "backend/app/agent_engine/budget.py",
    "backend/app/runtime/tool_gateway.py",
    "tests/unit/test_tool_gateway.py",
    "tests/unit/test_policy_identity.py",
    "tests/unit/test_budget.py",
    "tests/unit/test_database_legacy.py",
)


def _read(path: str) -> str:
    """
    Read one repository-relative source file.
    """
    return (ROOT / path).read_text(encoding="utf-8")


def _python_files() -> Iterable[Path]:
    """
    Yield Python source files relevant to the certification scan.
    """
    for base in (
        ROOT / "backend" / "app",
        ROOT / "tests",
    ):
        if not base.exists():
            continue

        yield from base.rglob("*.py")


def _assert_required_files() -> list[str]:
    """
    Verify required architectural files exist.
    """
    failures = []

    for relative_path in REQUIRED_FILES:
        path = ROOT / relative_path

        if not path.is_file():
            failures.append(
                f"Missing required file: {relative_path}"
            )

    return failures


def _assert_single_sqlalchemy_base() -> list[str]:
    """
    Verify that only the identity module creates the shared declarative Base.
    """
    failures = []

    for path in _python_files():
        relative = path.relative_to(ROOT).as_posix()

        if relative == "backend/app/domain/models/identity.py":
            continue

        source = path.read_text(encoding="utf-8")

        if "declarative_base()" in source:
            failures.append(
                f"Duplicate SQLAlchemy declarative_base() in {relative}"
            )

    return failures


def _assert_checker_fails_closed() -> list[str]:
    """
    Verify that the Checker does not contain the historical fail-open pattern.
    """
    failures = []

    source = _read(
        "backend/app/agent_engine/checker.py"
    )

    if "status=CheckerDecisionEnum.ACCEPT" in source:
        failures.append(
            "Checker contains a direct ACCEPT fallback."
        )

    if "except Exception:\n            pass" in source:
        failures.append(
            "Checker silently suppresses exceptions."
        )

    return failures


def _assert_budget_authority() -> list[str]:
    """
    Verify that no second in-memory budget authority remains.
    """
    failures = []

    legacy_source = _read(
        "backend/app/budget/manager.py"
    )

    if "_budgets" in legacy_source:
        failures.append(
            "Legacy budget manager still contains in-memory budget state."
        )

    return failures


def _assert_root_test_layout() -> list[str]:
    """
    Verify that active tests live under the repository-root tests tree.
    """
    failures = []

    legacy_tests = ROOT / "backend" / "tests"

    if legacy_tests.exists():
        failures.append(
            "Legacy backend/tests directory must not be used as the active test suite."
        )

    return failures


def _assert_ast_health() -> list[str]:
    """
    Parse critical Python files to catch syntax corruption early.
    """
    failures = []

    for relative_path in REQUIRED_FILES:
        path = ROOT / relative_path

        if path.suffix != ".py" or not path.is_file():
            continue

        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=relative_path,
            )
        except SyntaxError as exc:
            failures.append(
                f"Syntax error in {relative_path}: {exc}"
            )

    return failures


def collect_failures() -> list[str]:
    """
    Execute all deterministic certification checks.
    """
    failures: list[str] = []

    checks = (
        _assert_required_files,
        _assert_single_sqlalchemy_base,
        _assert_checker_fails_closed,
        _assert_budget_authority,
        _assert_root_test_layout,
        _assert_ast_health,
    )

    for check in checks:
        failures.extend(check())

    return failures


def main() -> int:
    """
    Execute certification and return a process exit code.
    """
    print("A.U.R.O.R.A. structural certification")

    failures = collect_failures()

    if failures:
        print(
            f"CERTIFICATION FAILED: {len(failures)} issue(s)"
        )

        for failure in failures:
            print(f" - {failure}")

        return 1

    print("CERTIFICATION PASSED")
    print(
        "Critical structure, parser health, and fail-closed "
        "invariants verified."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())