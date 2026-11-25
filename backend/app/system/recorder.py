"""
@file backend/app/system/recorder.py
@description Search and export the flight recorder (F9, ADR-030).

The recorder is the JSONL file every engine event is appended to
(app/agent_engine/events.py). Only the caller's workspace is ever read
back. A search keeps the newest matches; an export streams every match in
the order it was written. A damaged line is skipped.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterator, Optional

SEARCH_LIMIT = 200


@dataclass(frozen=True)
class RecorderQuery:
    workspace_id: str
    text: str = ""
    # An exact type ("tool.completed") or a family ("tool." or "tool").
    event_type: str = ""
    # The run itself, or a subagent of it.
    run_id: str = ""
    # ISO times, compared as text (the recorder writes naive UTC ISO).
    since: str = ""
    until: str = ""

    def matches(self, line: str, event: Dict[str, Any]) -> bool:
        if event.get("workspace_id") != self.workspace_id:
            return False

        if self.event_type:
            kind = str(event.get("event_type") or "")
            family = self.event_type.rstrip(".")
            if kind != self.event_type and not kind.startswith(family + "."):
                return False

        if self.run_id and self.run_id not in (event.get("run_id"), event.get("parent_run_id")):
            return False

        stamp = str(event.get("timestamp") or "")

        if self.since and stamp < self.since:
            return False

        if self.until and stamp > self.until:
            return False

        return not self.text or self.text.lower() in line.lower()


def recorder_path() -> str:
    # Read on every call: tests and the evals point it elsewhere.
    from app.agent_engine import events

    return events.FLIGHT_RECORDER_FILE


def _matching(query: RecorderQuery) -> Iterator[tuple[str, Dict[str, Any]]]:
    path = recorder_path()

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as recorder:
        for raw in recorder:
            line = raw.strip()

            if not line:
                continue

            try:
                event = json.loads(line)
            except ValueError:
                continue

            if isinstance(event, dict) and query.matches(line, event):
                yield line, event


def search(query: RecorderQuery, limit: int = SEARCH_LIMIT) -> Dict[str, Any]:
    """
    The newest `limit` matching events, newest first, and how many matched.
    """
    newest: Deque[Dict[str, Any]] = deque(maxlen=max(1, limit))
    matched = 0

    for _line, event in _matching(query):
        matched += 1
        newest.append(event)

    path = recorder_path()

    return {
        "matched": matched,
        "events": list(reversed(newest)),
        "truncated": matched > len(newest),
        "file_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
    }


def export_lines(query: RecorderQuery) -> Iterator[str]:
    """
    Every matching event as one JSONL line, oldest first.
    """
    for line, _event in _matching(query):
        yield line + "\n"


def query_from(workspace_id: str, **filters: Optional[str]) -> RecorderQuery:
    """
    A query from the API's optional filters, trimmed.
    """
    return RecorderQuery(
        workspace_id=workspace_id,
        **{name: (value or "").strip() for name, value in filters.items()},
    )


__all__ = ["RecorderQuery", "SEARCH_LIMIT", "export_lines", "query_from", "recorder_path", "search"]
