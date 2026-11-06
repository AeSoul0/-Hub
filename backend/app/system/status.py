"""
@file backend/app/system/status.py
@description What the SISTEMA page shows (F9, ADR-030):
- the app: version, desktop or server, Python, uptime;
- the database and the event bus, checked when the page asks;
- the startup parameters, read only: they are read when the API starts, so
  they change only with a restart, and a password in a URL is never shown;
- the memory of ÆHub's processes, read with psutil;
- whether a newer desktop version is published (on request only).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.desktop.launch import desktop_mode

STARTED_AT = datetime.utcnow()
_STARTED = time.monotonic()

# The updater's endpoint (desktop/src-tauri/tauri.conf.json).
UPDATE_ENDPOINT = "https://github.com/AeSoul0/-Hub/releases/latest/download/latest.json"
UPDATE_TIMEOUT_SECONDS = 8.0
BUS_TIMEOUT_SECONDS = 2.0
ERROR_CHARS = 300
NOTES_CHARS = 2000

# Name -> default shown when the variable is not set (None: no default).
STARTUP_PARAMETERS: Tuple[Tuple[str, Optional[str]], ...] = (
    ("POSTGRES_URL", None),
    ("REDIS_URL", "redis://localhost:6379/0"),
    ("AEHUB_EVENT_BUS", "redis"),
    ("AEHUB_HOST", "127.0.0.1"),
    ("FRONTEND_URL", "http://localhost:3000"),
    ("AEHUB_ALLOWED_ORIGINS", None),
    ("AEHUB_DATA_DIR", None),
    ("AEHUB_ALLOWED_DIRS", None),
    ("AEHUB_VOICE_MODELS_DIR", "~/.cache/aehub/voice"),
    ("AEHUB_SKILL_INDEX_PATH", "~/.cache/aehub/skill_index.sqlite3"),
    ("AEHUB_FLIGHT_RECORDER_PATH", "flight_recorder.jsonl"),
    ("AEHUB_HOME_DEVICES", None),
    ("AEHUB_PG_BIN", None),
    ("AEHUB_FRONTEND_DIR", None),
)

_PASSWORD_IN_URL = re.compile(r"(//[^/:@\s]*:)[^/\s]*@")


def redact(text: str) -> str:
    """
    A URL without its password: postgresql://user:***@host/db.
    """
    return _PASSWORD_IN_URL.sub(r"\1***@", text)


def _short_error(exc: BaseException) -> str:
    return redact(f"{type(exc).__name__}: {exc}")[:ERROR_CHARS]


def startup_parameters() -> List[Dict[str, Any]]:
    items = []

    for name, default in STARTUP_PARAMETERS:
        value = os.environ.get(name)

        if value is not None and value.strip():
            items.append({"name": name, "value": redact(value), "source": "environment"})
        elif default is not None:
            items.append({"name": name, "value": default, "source": "default"})
        else:
            items.append({"name": name, "value": None, "source": "unset"})

    return items


def app_status() -> Dict[str, Any]:
    return {
        # Set by the desktop shell when it starts the engine.
        "version": os.getenv("AEHUB_APP_VERSION") or None,
        "desktop": desktop_mode(),
        "python": sys.version.split()[0],
        "pid": os.getpid(),
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": round(time.monotonic() - _STARTED, 1),
    }


def database_status() -> Dict[str, Any]:
    from sqlalchemy import text

    from app.core.db import engine

    started = time.perf_counter()

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        return {"ok": False, "dialect": engine.dialect.name, "latency_ms": None, "error": _short_error(exc)}

    return {
        "ok": True,
        "dialect": engine.dialect.name,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": None,
    }


async def bus_status() -> Dict[str, Any]:
    from app.core.event_bus import event_bus

    if event_bus.local:
        return {"kind": "memory", "ok": True, "error": None}

    try:
        await asyncio.wait_for(event_bus.redis.ping(), timeout=BUS_TIMEOUT_SECONDS)
    except Exception as exc:
        return {"kind": "redis", "ok": False, "error": _short_error(exc)}

    return {"kind": "redis", "ok": True, "error": None}


# ==============================================================================
# MEMORY
# ==============================================================================


def _postgres_pid() -> Optional[int]:
    """
    The embedded cluster's server (desktop): first line of postmaster.pid.
    """
    data_dir = os.getenv("AEHUB_DATA_DIR", "").strip()

    if not data_dir:
        return None

    try:
        first = (Path(data_dir) / "pgdata" / "postmaster.pid").read_text(encoding="utf-8").splitlines()[0]
        return int(first.strip())
    except (OSError, ValueError, IndexError):
        return None


def _kind_of(name: str) -> str:
    name = name.lower()

    if name.startswith("postgres"):
        return "postgres"

    if "msedgewebview2" in name:
        return "window"

    if any(part in name for part in ("chrome", "chromium", "headless_shell", "msedge")):
        return "browser"

    return "other"


def memory_status() -> Dict[str, Any]:
    """
    RAM (resident set) of ÆHub's processes by kind:
    - backend: this process, voice models included (they load in it);
    - postgres: the embedded server and its workers (desktop only);
    - browser: Chromium started for the browser tool;
    - window: the desktop window's WebView2 (desktop only);
    - other: anything else this process started.
    """
    import psutil

    groups: Dict[str, Dict[str, int]] = {
        kind: {"bytes": 0, "processes": 0} for kind in ("backend", "postgres", "browser", "window", "other")
    }

    def add(kind: str, process: Any) -> None:
        try:
            groups[kind]["bytes"] += int(process.memory_info().rss)
            groups[kind]["processes"] += 1
        except psutil.Error:
            pass

    me = psutil.Process()
    add("backend", me)
    seen = {me.pid}

    try:
        children = me.children(recursive=True)
    except psutil.Error:
        children = []

    for child in children:
        try:
            kind = _kind_of(child.name())
        except psutil.Error:
            continue
        seen.add(child.pid)
        add(kind, child)

    pid = _postgres_pid()

    if pid is not None and pid not in seen:
        try:
            server = psutil.Process(pid)
            for process in [server, *server.children(recursive=True)]:
                if process.pid not in seen:
                    seen.add(process.pid)
                    add("postgres", process)
        except psutil.Error:
            pass

    # The desktop window is the engine's parent: its WebView2 processes.
    if desktop_mode():
        try:
            parent = me.parent()
            for process in parent.children(recursive=True) if parent else []:
                if process.pid not in seen and _kind_of(process.name()) == "window":
                    seen.add(process.pid)
                    add("window", process)
        except psutil.Error:
            pass

    machine = psutil.virtual_memory()

    from app.voice.engines import loaded_engines

    return {
        "groups": groups,
        "total_bytes": sum(group["bytes"] for group in groups.values()),
        "machine": {"total_bytes": int(machine.total), "available_bytes": int(machine.available)},
        "voice": loaded_engines(),
    }


# ==============================================================================
# DESKTOP UPDATES
# ==============================================================================


def _version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split("-")[0])[:3])


async def check_updates(endpoint: str = UPDATE_ENDPOINT) -> Dict[str, Any]:
    """
    The latest published desktop version against this one. Installing stays
    with the desktop app, which asks the owner when it starts.
    """
    import httpx

    current = os.getenv("AEHUB_APP_VERSION") or None

    try:
        async with httpx.AsyncClient(timeout=UPDATE_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(endpoint)
        response.raise_for_status()
        data = response.json()
        latest = str(data["version"]).lstrip("v")
    except Exception as exc:
        return {"current": current, "latest": None, "newer": None, "published_at": None, "notes": None, "error": _short_error(exc)}

    newer = _version_key(latest) > _version_key(current) if current else None

    return {
        "current": current,
        "latest": latest,
        "newer": newer,
        "published_at": data.get("pub_date"),
        "notes": str(data.get("notes") or "")[:NOTES_CHARS] or None,
        "error": None,
    }


__all__ = [
    "STARTUP_PARAMETERS",
    "UPDATE_ENDPOINT",
    "app_status",
    "bus_status",
    "check_updates",
    "database_status",
    "memory_status",
    "redact",
    "startup_parameters",
]
