"""
@file tests/agent_engine/test_system.py
@description F9 (ADR-030): the SISTEMA page's backend.

- status: passwords never leave a URL, startup parameters say where they
  come from, the database and bus checks, process memory, desktop updates;
- the flight recorder: search and export, one workspace only;
- the evals in a child process, without secrets;
- the access key rotation and the sessions it closes;
- the recent warnings and errors;
- voice: a runtime switch, and models let go after a time without use.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent_engine import events as events_module
from app.api import system as system_api
from app.core.config import settings
from app.core.log_buffer import RecentLogHandler
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum, hash_session_token, resolve_principal
from app.desktop import launch
from app.domain.models.identity import Base, Session as SessionModel, User, Workspace, WorkspaceMembership
from app.system import access_key, evals, recorder, status
from app.voice import engines

WORKSPACE = "workspace-f9"
ADMIN = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id=WORKSPACE)
MEMBER = Principal(id="member", role=RoleEnum.MEMBER, workspace_id=WORKSPACE)


@pytest.fixture(autouse=True)
def clean_settings():
    replace_stored({})
    yield
    replace_stored({})


def _client(principal: Principal = ADMIN) -> TestClient:
    app = FastAPI()
    app.include_router(system_api.router)
    app.dependency_overrides[resolve_principal] = lambda: principal
    return TestClient(app)


# ==============================================================================
# STATUS
# ==============================================================================


def test_a_password_never_leaves_a_url():
    assert status.redact("postgresql://aehub:s3cret@127.0.0.1:5432/aehub") == "postgresql://aehub:***@127.0.0.1:5432/aehub"
    assert status.redact("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert status.redact("redis://:p@ss@host:6379") == "redis://:***@host:6379"


def test_startup_parameters_say_where_each_comes_from(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:pw@db:5432/x")
    monkeypatch.delenv("AEHUB_HOST", raising=False)
    monkeypatch.delenv("AEHUB_PG_BIN", raising=False)

    items = {item["name"]: item for item in status.startup_parameters()}

    assert items["POSTGRES_URL"] == {"name": "POSTGRES_URL", "value": "postgresql://u:***@db:5432/x", "source": "environment"}
    assert items["AEHUB_HOST"] == {"name": "AEHUB_HOST", "value": "127.0.0.1", "source": "default"}
    assert items["AEHUB_PG_BIN"]["source"] == "unset"
    # Only the parameters read at startup: no key is ever listed.
    assert not any("KEY" in name for name in items)


def test_the_database_check_reports_without_the_password(monkeypatch):
    import app.core.db as db_module

    monkeypatch.setattr(db_module, "engine", create_engine("sqlite://", poolclass=StaticPool))
    good = status.database_status()
    assert good["ok"] is True and good["dialect"] == "sqlite" and good["latency_ms"] >= 0

    class Broken:
        dialect = type("D", (), {"name": "postgresql"})()

        def connect(self):
            raise RuntimeError("could not connect to postgresql://aehub:hunter2@db:5432/aehub")

    monkeypatch.setattr(db_module, "engine", Broken())
    bad = status.database_status()
    assert bad["ok"] is False
    assert "hunter2" not in bad["error"] and "***" in bad["error"]


async def test_the_bus_check(monkeypatch):
    from app.core.event_bus import event_bus

    monkeypatch.setattr(event_bus, "local", True)
    assert await status.bus_status() == {"kind": "memory", "ok": True, "error": None}

    class DownRedis:
        async def ping(self):
            raise ConnectionError("redis://:topsecret@cache:6379 refused")

    monkeypatch.setattr(event_bus, "local", False)
    monkeypatch.setattr(event_bus, "redis", DownRedis())
    down = await status.bus_status()
    assert down["kind"] == "redis" and down["ok"] is False
    assert "topsecret" not in down["error"]


def test_memory_counts_this_process():
    memory = status.memory_status()

    assert memory["groups"]["backend"]["bytes"] > 0
    assert memory["groups"]["backend"]["processes"] == 1
    assert memory["total_bytes"] >= memory["groups"]["backend"]["bytes"]
    assert memory["machine"]["total_bytes"] >= memory["machine"]["available_bytes"] > 0
    assert set(memory["groups"]) == {"backend", "postgres", "browser", "window", "other"}


def test_process_kinds():
    assert status._kind_of("postgres.exe") == "postgres"
    assert status._kind_of("msedgewebview2.exe") == "window"
    assert status._kind_of("chrome-headless-shell") == "browser"
    assert status._kind_of("python.exe") == "other"


REAL_CLIENT = httpx.AsyncClient


def _released(monkeypatch, handler) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs))


async def test_a_newer_desktop_version_is_found(monkeypatch):
    monkeypatch.setenv("AEHUB_APP_VERSION", "1.0.0")
    _released(monkeypatch, lambda request: httpx.Response(200, json={"version": "v1.2.0", "notes": "Fix", "pub_date": "2026-11-05T10:00:00Z"}))

    found = await status.check_updates()

    assert found == {
        "current": "1.0.0",
        "latest": "1.2.0",
        "newer": True,
        "published_at": "2026-11-05T10:00:00Z",
        "notes": "Fix",
        "error": None,
    }

    _released(monkeypatch, lambda request: httpx.Response(200, json={"version": "1.0.0"}))
    assert (await status.check_updates())["newer"] is False


async def test_an_update_check_that_fails_says_why(monkeypatch):
    monkeypatch.delenv("AEHUB_APP_VERSION", raising=False)
    _released(monkeypatch, lambda request: httpx.Response(404))

    found = await status.check_updates()

    assert found["latest"] is None and found["newer"] is None
    assert "404" in found["error"]


def test_the_status_route_is_for_the_owner(monkeypatch):
    import app.core.db as db_module
    from app.core.event_bus import event_bus

    monkeypatch.setattr(db_module, "engine", create_engine("sqlite://", poolclass=StaticPool))
    monkeypatch.setattr(event_bus, "local", True)

    body = _client().get("/api/system").json()
    assert body["database"]["ok"] is True
    assert body["event_bus"]["kind"] == "memory"
    assert body["access_key"] == {"can_rotate": False}
    assert {item["name"] for item in body["startup"]} >= {"POSTGRES_URL", "AEHUB_EVENT_BUS"}

    for method, path in (
        ("get", "/api/system"),
        ("post", "/api/system/updates/check"),
        ("get", "/api/system/events"),
        ("get", "/api/system/events/export"),
        ("get", "/api/system/evals"),
        ("post", "/api/system/evals"),
        ("post", "/api/system/access-key/rotate"),
        ("get", "/api/system/logs"),
    ):
        response = getattr(_client(MEMBER), method)(path, **({"json": {"confirm": True}} if method == "post" else {}))
        assert response.status_code == 403, path


# ==============================================================================
# FLIGHT RECORDER
# ==============================================================================


def _event(event_type: str, run_id: str, at: str, workspace: str = WORKSPACE, **extra: Any) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "run_id": run_id,
        "session_id": "s",
        "workspace_id": workspace,
        "timestamp": at,
        **extra,
    }


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    path = tmp_path / "flight_recorder.jsonl"
    monkeypatch.setattr(events_module, "FLIGHT_RECORDER_FILE", str(path))
    lines = [
        json.dumps(_event("run.started", "run-a", "2026-11-05T10:00:00")),
        json.dumps(_event("tool.proposed", "run-a", "2026-11-05T10:00:01", tool="web_search")),
        "not json at all",
        json.dumps(_event("tool.completed", "run-a", "2026-11-05T10:00:02", tool="web_search")),
        json.dumps(_event("subagent.spawned", "run-b", "2026-11-05T10:00:03", parent_run_id="run-a")),
        json.dumps(_event("run.started", "run-x", "2026-11-05T10:00:04", workspace="elsewhere")),
        json.dumps(_event("run.completed", "run-a", "2026-11-05T10:00:05")),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _found(**filters: str) -> List[str]:
    result = recorder.search(recorder.query_from(WORKSPACE, **filters))
    return [f"{event['event_type']}:{event['run_id']}" for event in result["events"]]


def test_the_recorder_search_stays_in_the_workspace(recorded):
    result = recorder.search(recorder.query_from(WORKSPACE))

    assert result["matched"] == 5
    assert result["truncated"] is False
    assert result["file_bytes"] == recorded.stat().st_size
    # Newest first; the damaged line and the other workspace are skipped.
    assert [event["event_type"] for event in result["events"]] == [
        "run.completed",
        "subagent.spawned",
        "tool.completed",
        "tool.proposed",
        "run.started",
    ]


def test_the_recorder_filters(recorded):
    assert _found(event_type="tool") == ["tool.completed:run-a", "tool.proposed:run-a"]
    assert _found(event_type="tool.completed") == ["tool.completed:run-a"]
    assert _found(run_id="run-b") == ["subagent.spawned:run-b"]
    # A run's own events and the announcements of its subagents.
    assert len(_found(run_id="run-a")) == 5
    assert _found(text="WEB_SEARCH") == ["tool.completed:run-a", "tool.proposed:run-a"]
    assert _found(since="2026-11-05T10:00:03", until="2026-11-05T10:00:04") == ["subagent.spawned:run-b"]


def test_the_search_keeps_the_newest(recorded):
    result = recorder.search(recorder.query_from(WORKSPACE), limit=2)

    assert result["matched"] == 5 and result["truncated"] is True
    assert [event["event_type"] for event in result["events"]] == ["run.completed", "subagent.spawned"]


def test_the_export_is_jsonl_oldest_first(recorded):
    response = _client().get("/api/system/events/export", params={"event_type": "tool"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["content-disposition"].startswith('attachment; filename="aehub-flight-recorder-')
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [line["event_type"] for line in lines] == ["tool.proposed", "tool.completed"]

    search = _client().get("/api/system/events", params={"q": "spawned"}).json()
    assert search["matched"] == 1


def test_no_recorder_file_is_no_event(tmp_path, monkeypatch):
    monkeypatch.setattr(events_module, "FLIGHT_RECORDER_FILE", str(tmp_path / "missing.jsonl"))
    assert recorder.search(recorder.query_from(WORKSPACE)) == {"matched": 0, "events": [], "truncated": False, "file_bytes": 0}


# ==============================================================================
# EVALS
# ==============================================================================


def test_the_eval_child_gets_no_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-real")
    monkeypatch.setenv("AEHUB_SECRET_KEY", "login-real")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:pw@db/x")
    monkeypatch.setenv("AEHUB_MQTT_PASSWORD", "mqtt-real")
    monkeypatch.setenv("AEHUB_STT_MODEL", "small")

    env = evals.child_environment()

    assert "OPENAI_API_KEY" not in env and "ELEVENLABS_API_KEY" not in env and "AEHUB_MQTT_PASSWORD" not in env
    assert env["AEHUB_SECRET_KEY"] != "login-real"
    assert "pw" not in env["POSTGRES_URL"]
    assert env["AEHUB_EVENT_BUS"] == "memory"
    # Ordinary settings pass through.
    assert env["AEHUB_STT_MODEL"] == "small"


def _fake_child(monkeypatch, code: str) -> None:
    monkeypatch.setattr(evals, "_CHILD", code)


def test_a_suite_run_reads_the_report_and_the_gate(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    _fake_child(
        monkeypatch,
        "import json, sys; args = sys.argv[2:]; "
        "path = args[args.index('--report') + 1]; "
        "json.dump({'metrics': {'success_rate': 0.5}, 'cases': ["
        "{'id': 'a', 'category': 'tools', 'passed': True, 'critical': False, 'status': 'COMPLETED', 'cost': 0.0, 'failures': []}, "
        "{'id': 'b', 'category': 'security', 'passed': False, 'critical': True, 'status': 'FAILED', 'cost': 0.0, 'failures': ['leaked']}"
        "]}, open(path, 'w')); "
        "print('RELEASE GATE FAILED:'); print('  - critical security cases failed: [b]'); sys.exit(1)",
    )

    result = evals.run_suite_in_child(baseline)

    assert result.status == "failed" and result.gate is True
    assert result.metrics == {"success_rate": 0.5}
    assert [(case["id"], case["passed"], case["failures"]) for case in result.cases] == [("a", True, []), ("b", False, ["leaked"])]
    assert result.problems == ["critical security cases failed: [b]"]


def test_a_suite_that_writes_no_report_is_an_error(monkeypatch):
    _fake_child(monkeypatch, "import sys; print('boom'); sys.exit(2)")

    result = evals.run_suite_in_child(None)

    assert result.status == "error" and result.gate is False
    assert "boom" in result.error


async def test_one_evaluation_at_a_time(monkeypatch):
    monkeypatch.setattr(evals, "_state", evals.EvalRun(status="running"))

    with pytest.raises(RuntimeError):
        await evals.start("owner")

    assert _client().post("/api/system/evals").status_code == 409
    monkeypatch.setattr(evals, "_state", evals.EvalRun())
    assert _client().get("/api/system/evals").json()["status"] == "idle"


# ==============================================================================
# ACCESS KEY
# ==============================================================================


class KeyStore:
    def __init__(self) -> None:
        self.values: Dict[str, str] = {"AEHUB_SECRET_KEY": "old-key"}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


@pytest.fixture
def identity_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        engine,
        tables=[Workspace.__table__, User.__table__, WorkspaceMembership.__table__, SessionModel.__table__],
    )
    factory = sessionmaker(bind=engine)

    with factory() as db:
        for token in ("mine", "other-1", "other-2"):
            db.add(
                SessionModel(
                    id=hash_session_token(token),
                    user_id="u1",
                    workspace_id=WORKSPACE,
                    role=RoleEnum.ADMIN,
                    expires_at=datetime.utcnow() + timedelta(days=1),
                )
            )
        db.commit()

    return factory


@pytest.fixture
def key_store():
    previous = settings.AEHUB_SECRET_KEY
    store = KeyStore()
    launch.enable(store)
    yield store
    launch.disable()
    settings.AEHUB_SECRET_KEY = previous


def test_a_rotation_needs_the_keyring(identity_db):
    with identity_db() as db, pytest.raises(access_key.KeyStoreUnavailable):
        access_key.rotate(db, "mine")

    assert access_key.can_rotate() is False


def test_a_rotation_saves_the_key_and_closes_the_other_sessions(identity_db, key_store):
    with identity_db() as db:
        key, closed = access_key.rotate(db, "mine")
        left = [row.id for row in db.query(SessionModel).all()]

    assert closed == 2
    assert left == [hash_session_token("mine")]
    assert key_store.values["AEHUB_SECRET_KEY"] == key != "old-key"
    assert settings.AEHUB_SECRET_KEY == key
    assert len(key) >= 32


def test_the_rotate_route_wants_a_confirmation(agent_infrastructure, key_store, identity_db, monkeypatch):
    monkeypatch.setattr("app.core.db.SessionLocal", identity_db)
    audited: List[Dict[str, Any]] = []
    monkeypatch.setattr("app.runtime.audit_chain.append_audit_record", lambda db, **fields: audited.append(fields))

    client = _client()
    assert client.post("/api/system/access-key/rotate", json={}).status_code == 428
    assert audited == []

    client.cookies.set("aehub_session_token", "mine")
    body = client.post("/api/system/access-key/rotate", json={"confirm": True}).json()

    assert body["sessions_closed"] == 2
    assert body["key"] == key_store.values["AEHUB_SECRET_KEY"]
    assert [entry["tool_name"] for entry in audited] == ["access_key.rotate"]
    assert body["key"] not in json.dumps(audited)


def test_without_the_keyring_the_route_says_where_the_key_is():
    response = _client().post("/api/system/access-key/rotate", json={"confirm": True})

    assert response.status_code == 409
    assert "AEHUB_SECRET_KEY" in response.json()["detail"]


# ==============================================================================
# RECENT WARNINGS AND ERRORS
# ==============================================================================


def test_the_log_keeps_warnings_and_errors_newest_first():
    handler = RecentLogHandler(capacity=2)
    logger = logging.getLogger("aehub.test.f9")
    logger.addHandler(handler)
    logger.propagate = False

    try:
        logger.info("not kept")
        logger.warning("first %s", "warning")
        logger.error("an error")
        logger.critical("a critical one")
    finally:
        logger.removeHandler(handler)

    assert [(item["level"], item["message"]) for item in handler.recent(10)] == [
        ("critical", "a critical one"),
        ("error", "an error"),
    ]
    assert [item["message"] for item in handler.recent(10, "error")] == ["an error"]


# ==============================================================================
# VOICE
# ==============================================================================


class FakeEngine:
    def __init__(self, config):
        self.config = config


@pytest.fixture
def voice_engines(monkeypatch):
    monkeypatch.setattr(engines, "_engines", {})
    monkeypatch.setattr(engines, "_last_used", {})
    monkeypatch.setattr(engines, "_model_loaded", lambda engine: True)
    return engines


def test_voice_is_a_runtime_switch(monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE", "local")
    assert engines.voice_enabled() is True

    replace_stored({"AEHUB_VOICE": "off"})
    assert engines.voice_enabled() is False


def test_idle_voice_models_are_let_go(voice_engines, monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE_IDLE_MINUTES", "10")
    voice_engines._engines.update({"stt": FakeEngine(("base", "it")), "tts": FakeEngine(("piper", "paola"))})
    voice_engines._last_used.update({"stt": 0.0, "tts": 500.0})

    assert [item["kind"] for item in voice_engines.loaded_engines(now=599.0)] == ["stt", "tts"]
    assert voice_engines.loaded_engines(now=599.0)[0]["idle_seconds"] == 599.0

    # Ten minutes after its last sentence Whisper goes; Piper stays.
    assert voice_engines.release_idle_engines(now=600.0) == ["stt"]
    assert list(voice_engines._engines) == ["tts"]


def test_zero_keeps_the_voice_models(voice_engines, monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE_IDLE_MINUTES", "0")
    voice_engines._engines["stt"] = FakeEngine(("base", "it"))
    voice_engines._last_used["stt"] = 0.0

    assert voice_engines.release_idle_engines(now=1_000_000.0) == []
    assert list(voice_engines._engines) == ["stt"]


def test_an_engine_in_use_is_fresh(voice_engines, monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE", "local")
    monkeypatch.setenv("AEHUB_VOICE_IDLE_MINUTES", "1")
    monkeypatch.setattr(engines, "missing_packages", lambda: [])
    monkeypatch.setattr(engines, "_build", lambda kind, config: FakeEngine(config))

    engines.speech_to_text()

    assert "stt" in voice_engines._last_used
    assert voice_engines.release_idle_engines() == []
