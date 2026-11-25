"""
@file scripts/check_headers.py
@description R1 check, run in CI: every source file opens with the project
header (`@file` with its own path, then `@description`), and no placeholder
docstring of the old generator is left ("Executes … logic.", "Represents the
… entity", "This module manages the internal business logic…").

    python scripts/check_headers.py            # exit 1 and list what is wrong

Only the standard library is used.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tracked sources of the project (generated and vendored files excluded).
SUFFIXES = {".py", ".js", ".mjs", ".mts", ".ts", ".tsx", ".rs"}
SKIP = (
    "frontend/next-env.d.ts",
    "backend/alembic/script.py.mako",
)
SKIP_PARTS = ("node_modules", "/gen/", "__pycache__")

# Only the first lines count as the header.
HEADER_LINES = 12

PLACEHOLDERS = re.compile(
    r"Executes (the )?[\w.]+ logic\."
    r"|Represents the \w+ entity"
    r"|This module manages the internal business logic"
    r"|It provides specialized functionality to handle"
    r"|Implements [\w.]+\. Core components"
    r"|Core module for A\.U\.R\.O\.R\.A\. System"
    r"|Implements core logic and architectural definitions"
)


def tracked_sources() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [
        ROOT / name
        for name in listed
        if Path(name).suffix in SUFFIXES
        and name not in SKIP
        and not any(part in f"/{name}" for part in SKIP_PARTS)
    ]


def problems(path: Path) -> list[str]:
    relative = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:HEADER_LINES])
    found = []

    match = re.search(r"@file\s+(\S+)", head)
    if not match:
        found.append("no @file in the header")
    elif match.group(1) != relative:
        found.append(f"@file says {match.group(1)}")

    if "@description" not in head:
        found.append("no @description in the header")

    # This script quotes the placeholders it looks for.
    if path == Path(__file__).resolve():
        return found

    for number, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDERS.search(line):
            found.append(f"line {number}: placeholder text")

    return found


def main() -> int:
    report = {
        path.relative_to(ROOT).as_posix(): issues
        for path in tracked_sources()
        if (issues := problems(path))
    }

    for name, issues in sorted(report.items()):
        print(f"{name}: {'; '.join(issues)}")

    if report:
        print(f"\n{len(report)} file(s) without the project header or with placeholder text.")
        return 1

    print("Every source file has its header.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
