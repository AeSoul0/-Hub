"""
@file tests/security/test_frontend_coverage.py
@description F10 exit test: docs/frontend-coverage.md names every route and
every setting of the backend, so the 100% of the table cannot go stale.

The index at the end of the document maps each route, each setting changed
without a restart, each startup parameter and each secret to the row of the
table that covers it. A new route or a new variable read by the backend
fails this test until it gets its row, which is the moment to give it a
control in the interface or a read-only line on the SISTEMA page.
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.routing import Mount, WebSocketRoute

import main
from app.core.runtime_config import SPEC_BY_NAME
from app.system.status import STARTUP_PARAMETERS

REPO = Path(__file__).resolve().parents[2]
COVERAGE = REPO / "docs" / "frontend-coverage.md"
BACKEND = REPO / "backend"

# Variables of the operating system, not of ÆHub.
OS_VARIABLES = {"PATH", "LOCALAPPDATA", "USERNAME", "USERDOMAIN"}

_READ_FROM_ENV = re.compile(
    r"""(?:getenv|environ\.get|environ\[|config_value|_env_set)\(?\s*["']([A-Z][A-Z0-9_]+)["']"""
)
_INDEXED = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
_TABLE_ROW = re.compile(r"^\| (\d+|S\d+) \|.*\| (✓|◐|✗|⏸) \|", re.MULTILINE)


def _index() -> set[str]:
    text = COVERAGE.read_text(encoding="utf-8")
    _, _, index = text.partition("## Indice: ogni route e ogni impostazione")
    assert index, "the coverage document has no index"
    return set(_INDEXED.findall(index))


def _routes(routes, prefix: str = ""):
    for route in routes:
        included = getattr(route, "original_router", None)

        if included is not None:
            context = getattr(route, "include_context", None)
            yield from _routes(included.routes, prefix + getattr(context, "prefix", ""))
        elif isinstance(route, Mount):
            if route.path:  # the static frontend of the desktop app mounts at "/"
                yield f"MOUNT {prefix}{route.path}"
        elif isinstance(route, WebSocketRoute):
            yield f"WS {prefix}{route.path}"
        else:
            for method in route.methods - {"HEAD"}:
                yield f"{method} {prefix}{route.path}"


def _variables_read_by_the_backend() -> set[str]:
    names = set()

    for folder in (BACKEND / "app", BACKEND):
        files = folder.rglob("*.py") if folder.name == "app" else folder.glob("*.py")

        for path in files:
            names.update(_READ_FROM_ENV.findall(path.read_text(encoding="utf-8")))

    return names - OS_VARIABLES


def test_every_route_has_its_row():
    missing = set(_routes(main.app.routes)) - _index()
    assert not missing, f"Routes missing from the index of docs/frontend-coverage.md: {sorted(missing)}"


def test_every_setting_and_startup_parameter_has_its_row():
    expected = set(SPEC_BY_NAME) | {name for name, _ in STARTUP_PARAMETERS}
    missing = expected - _index()
    assert not missing, f"Settings missing from the index of docs/frontend-coverage.md: {sorted(missing)}"


def test_every_variable_the_backend_reads_has_its_row():
    missing = _variables_read_by_the_backend() - _index()
    assert not missing, (
        "The backend reads variables that docs/frontend-coverage.md does not name: "
        f"{sorted(missing)}. Give each a control, a read-only line on SISTEMA, or a row "
        "in 'Segreti e variabili interne'."
    )


def test_the_headline_count_matches_the_table():
    text = COVERAGE.read_text(encoding="utf-8")
    table, _, _ = text.partition("## Storia")
    rows = _TABLE_ROW.findall(table)
    counted = [status for _, status in rows if status != "⏸"]
    covered = sum(1.0 if status == "✓" else 0.5 if status == "◐" else 0.0 for status in counted)

    headline = re.search(r"\*\*Copertura:\*\* ([\d,]+) righe su (\d+)", text)
    assert headline, "the coverage headline is missing"
    assert float(headline.group(1).replace(",", ".")) == covered
    assert int(headline.group(2)) == len(counted)
