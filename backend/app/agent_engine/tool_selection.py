"""
@file backend/app/agent_engine/tool_selection.py
@description The skill index (roadmap M15, ADR-021): which tools a run sees.

A SQLite database of its own (AEHUB_SKILL_INDEX_PATH, default
~/.cache/aehub/skill_index.sqlite3), apart from the application database,
with an FTS5 table over each tool's name, description and examples. At the
start of a run, select_tools() picks from the user's task, and only from it,
the AEHUB_TOOL_TOP_K best tools (BM25); the model is shown those, and the
PolicyEngine refuses a call to any other tool in that run, so an injected
instruction cannot reach a tool the task never called for.

Tools disabled in the Control Plane (AEHUB_DISABLED_TOOLS, F5) are not
indexed. AEHUB_TOOL_SELECTION and AEHUB_TOOL_TOP_K are runtime settings:
a change applies to the next run.

Everything is exposed, as before, when:
- AEHUB_TOOL_SELECTION=off;
- the catalog has no more than k tools;
- no word of the task matches any tool (a request in other words must not
  lose the right tool);
- the index cannot be used (no FTS5, unreadable file).

The index is rebuilt when the registry's signature (names, descriptions,
examples) changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.runtime_config import config_value
from app.core.security import disabled_tools


logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 6

# Words that say nothing about which tool is needed.
_STOPWORDS = frozenset(
    """
    the and for with that this from what when where which about into your you
    please can could would should tell give show me my mine our are was were is
    il lo la le gli una uno del della dei delle che chi per con sul sulla nel
    nella mio mia miei mie tuo tua sono come cosa quando dove puoi vorrei
    """.split()
)


def _terms(text: str) -> List[str]:
    """
    Lowercase word stems of a task: a crude stemmer for Italian and English
    ("documenti" and "documento" share "documen").
    """
    words = re.findall(r"[^\W\d_]{3,}", text.lower())
    stems: List[str] = []

    for word in words:
        if word in _STOPWORDS:
            continue
        stem = word[: max(4, len(word) - 2)] if len(word) > 5 else word
        if stem not in stems:
            stems.append(stem)

    return stems[:32]


def _documents(registry: Any) -> List[Tuple[str, str]]:
    documents: List[Tuple[str, str]] = []
    disabled = disabled_tools()

    for name in registry.get_registered_tool_names():
        if name in disabled:
            continue
        metadata = registry.get_tool_metadata(name)
        if metadata is None:
            continue
        body = " ".join(
            [
                name.replace("_", " "),
                metadata.description,
                " ".join(getattr(metadata, "examples", []) or []),
            ]
        )
        documents.append((name, body))

    return documents


def _signature(documents: List[Tuple[str, str]]) -> str:
    return hashlib.sha256(json.dumps(documents, sort_keys=True).encode("utf-8")).hexdigest()


def index_path() -> str:
    configured = os.getenv("AEHUB_SKILL_INDEX_PATH", "").strip()

    if configured:
        return configured

    folder = Path.home() / ".cache" / "aehub"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / "skill_index.sqlite3")


class SkillIndex:
    """
    One SQLite file; rebuilt in place when the catalog changes.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS tools
                USING fts5(name UNINDEXED, body, tokenize = 'unicode61 remove_diacritics 2');
            """
        )

    def sync(self, documents: List[Tuple[str, str]]) -> None:
        signature = _signature(documents)

        with self._lock:
            row = self._connection.execute("SELECT value FROM meta WHERE key = 'signature'").fetchone()
            if row and row[0] == signature:
                return

            with self._connection:
                self._connection.execute("DELETE FROM tools")
                self._connection.executemany("INSERT INTO tools (name, body) VALUES (?, ?)", documents)
                self._connection.execute(
                    "INSERT INTO meta (key, value) VALUES ('signature', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (signature,),
                )

    def search(self, task: str, limit: int) -> List[str]:
        stems = _terms(task)
        if not stems:
            return []

        # Each stem is quoted (no FTS5 operators from the task) and matched
        # as a prefix.
        expression = " OR ".join('"{}"*'.format(stem.replace('"', "")) for stem in stems)

        with self._lock:
            rows = self._connection.execute(
                "SELECT name FROM tools WHERE tools MATCH ? ORDER BY bm25(tools) LIMIT ?",
                (expression, limit),
            ).fetchall()

        return [row[0] for row in rows]


_indexes: Dict[str, SkillIndex] = {}
_indexes_lock = threading.Lock()


def _index() -> SkillIndex:
    path = index_path()

    with _indexes_lock:
        if path not in _indexes:
            _indexes[path] = SkillIndex(path)
        return _indexes[path]


def top_k() -> int:
    try:
        return max(1, int(config_value("AEHUB_TOOL_TOP_K", str(DEFAULT_TOP_K)) or DEFAULT_TOP_K))
    except ValueError:
        return DEFAULT_TOP_K


def selection_enabled() -> bool:
    return (config_value("AEHUB_TOOL_SELECTION", "on") or "on").strip().lower() != "off"


def selection_status(registry: Any) -> Dict[str, Any]:
    """
    What the Control Plane shows of the index: on or off, k, how many tools
    it can pick from, and whether it narrows anything at all.
    """
    tools = len(_documents(registry))
    enabled = selection_enabled()
    limit = top_k()

    return {
        "enabled": enabled,
        "top_k": limit,
        "tools": tools,
        "active": enabled and tools > limit,
    }


def select_tools(registry: Any, task: str) -> Optional[List[str]]:
    """
    The tools a run with this task is shown, or None for all of them.
    """
    if not selection_enabled():
        return None

    documents = _documents(registry)
    limit = top_k()

    if len(documents) <= limit:
        return None

    try:
        index = _index()
        index.sync(documents)
        selected = index.search(task, limit)
    except sqlite3.Error as exc:
        logger.warning("Skill index unavailable, exposing every tool: %s", exc)
        return None

    return sorted(selected) or None


__all__ = [
    "DEFAULT_TOP_K",
    "SkillIndex",
    "index_path",
    "select_tools",
    "selection_enabled",
    "selection_status",
    "top_k",
]
