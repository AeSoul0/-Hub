"""
@file tests/desktop/test_desktop_runtime.py
@description M14 (ADR-020): the pieces of the desktop runtime, one by one.

- events and cache without Redis;
- loopback hardening: Host names and cross-origin writes;
- the one-time launch token and the routes that use it;
- provider keys saved to the keyring, never echoed;
- the sidecar's environment;
- the managed Postgres cluster: init, restart, stale postmaster.pid (needs
  PostgreSQL binaries, skipped without them).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import desktop as desktop_api
from app.core import cache as cache_module
from app.core.cache import CacheService, LocalCache
from app.core.db import get_db
from app.core.event_bus import EventBus
from app.core.security import (
    Principal,
    host_name,
    is_cross_origin_write,
    is_host_allowed,
    resolve_principal,
)
from app.desktop import launch
from app.domain.models.identity import Base, RoleEnum


BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import desktop as sidecar  # noqa: E402


ADMIN = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="default-workspace")
MEMBER = Principal(id="member", role=RoleEnum.MEMBER, workspace_id="default-workspace")


class MemoryStore:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self.values = dict(values or {})

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


@pytest.fixture(autouse=True)
def desktop_off():
    launch.disable()
    yield
    launch.disable()


# ==============================================================================
# NO REDIS
# ==============================================================================


async def test_local_cache_counts_and_expires(monkeypatch):
    # The calls CacheService.check_rate_limit makes: incr, then expire on the
    # first hit. (tests/test_auth.py replaces check_rate_limit for the whole
    # session, so the commands are tested here, not the method.)
    now = [100.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    store = LocalCache()

    assert await store.incr("rate_limit:x") == 1
    await store.expire("rate_limit:x", 10)
    assert await store.incr("rate_limit:x") == 2

    now[0] += 11
    assert await store.incr("rate_limit:x") == 1

    await store.set("k", '{"a": 1}', ex=5)
    assert await store.get("k") == '{"a": 1}'
    now[0] += 6
    assert await store.get("k") is None


async def test_cache_service_stays_in_process(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "memory://")
    monkeypatch.setattr(CacheService, "_local", None)

    client = await CacheService.get_client()
    assert isinstance(client, LocalCache)
    assert await CacheService.get_client() is client

    await CacheService.set("k", {"a": 1}, expire_seconds=5)
    assert await CacheService.get("k") == {"a": 1}


async def test_local_cache_delete():
    store = LocalCache()
    await store.set("k", "v")
    await store.delete("k")
    assert await store.get("k") is None


async def test_event_bus_in_process(monkeypatch):
    monkeypatch.setenv("AEHUB_EVENT_BUS", "memory")
    bus = EventBus()
    assert bus.local is True and bus.redis is None

    session_queue = bus.subscribe("s1")
    workspace_queue = bus.subscribe_workspace("w1")
    other = bus.subscribe("s2")

    await bus.publish("s1", "run.state", {"status": "done"}, workspace_id="w1")

    for queue in (session_queue, workspace_queue):
        message = json.loads(await asyncio.wait_for(queue.get(), 1))
        assert message == {"type": "run.state", "data": {"status": "done"}}
    assert other.empty()

    bus.unsubscribe("s1", session_queue)
    await bus.publish("s1", "again", {})
    assert session_queue.empty()


def test_event_bus_uses_redis_by_default(monkeypatch):
    monkeypatch.delenv("AEHUB_EVENT_BUS", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    assert EventBus().local is False


# ==============================================================================
# LOOPBACK HARDENING
# ==============================================================================


@pytest.mark.parametrize(
    "header,name",
    [
        ("127.0.0.1:3002", "127.0.0.1"),
        ("localhost", "localhost"),
        ("[::1]:8000", "::1"),
        ("LOCALHOST:1", "localhost"),
        ("", ""),
    ],
)
def test_host_name(header, name):
    assert host_name(header) == name


def test_only_known_hosts_are_allowed(monkeypatch):
    monkeypatch.setenv("AEHUB_ALLOWED_HOSTS", "aehub.lan")

    assert is_host_allowed("127.0.0.1:51234")
    assert is_host_allowed("[::1]:3002")
    assert is_host_allowed("aehub.lan:3002")
    # DNS rebinding: the attacker's name resolves to 127.0.0.1.
    assert not is_host_allowed("evil.example:3002")
    assert not is_host_allowed(None)


def test_cross_origin_writes(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "http://127.0.0.1:5000")
    monkeypatch.delenv("AEHUB_ALLOWED_ORIGINS", raising=False)

    # Another local page: same-site for cookies, so it must be refused.
    assert is_cross_origin_write("POST", "http://localhost:9999")
    assert is_cross_origin_write("DELETE", "http://evil.example")
    assert not is_cross_origin_write("POST", "http://127.0.0.1:5000")
    assert not is_cross_origin_write("GET", "http://evil.example")
    assert not is_cross_origin_write("POST", None)


def test_api_refuses_unknown_host_and_foreign_origin(monkeypatch):
    from main import app

    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    # The login route rate-limits through the cache: no Redis here.
    monkeypatch.setenv("REDIS_URL", "memory://")
    monkeypatch.setattr(CacheService, "_local", None)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400

    refused = client.post(
        "/api/auth/login",
        json={"key": "x"},
        headers={"Origin": "http://localhost:9999"},
    )
    assert refused.status_code == 403

    # Our own origin reaches the route (wrong key: 401, not 403).
    allowed = client.post(
        "/api/auth/login",
        json={"key": "wrong"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert allowed.status_code in (401, 429)


def test_pages_get_the_page_policy_and_the_api_the_strict_one():
    from app.core.security_middleware import API_CSP, PAGE_CSP

    assert "'unsafe-inline'" not in API_CSP
    assert "frame-ancestors 'none'" in PAGE_CSP and "object-src 'none'" in PAGE_CSP
    assert "connect-src 'self'" in PAGE_CSP


# ==============================================================================
# LAUNCH TOKEN
# ==============================================================================


def test_launch_token_is_single_use_and_expires(monkeypatch):
    with pytest.raises(RuntimeError):
        launch.issue_launch_token()

    launch.enable(MemoryStore())
    token = launch.issue_launch_token()

    assert not launch.consume_launch_token("not-the-token")
    assert launch.consume_launch_token(token)
    assert not launch.consume_launch_token(token)

    now = [0.0]
    monkeypatch.setattr(launch.time, "monotonic", lambda: now[0])
    expiring = launch.issue_launch_token(ttl_seconds=10)
    now[0] = 11
    assert not launch.consume_launch_token(expiring)

    first = launch.issue_launch_token()
    second = launch.issue_launch_token()
    assert not launch.consume_launch_token(first)
    assert launch.consume_launch_token(second)


@pytest.fixture
def identity_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            table
            for name, table in Base.metadata.tables.items()
            if name in {"users", "workspaces", "workspace_memberships", "sessions"}
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def desktop_client(identity_db, principal: Principal = ADMIN) -> TestClient:
    app = FastAPI()
    app.include_router(desktop_api.router)

    def db():
        session = identity_db()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[resolve_principal] = lambda: principal
    return TestClient(app)


def test_launch_route_exchanges_the_token_once(identity_db):
    launch.enable(MemoryStore())
    token = launch.issue_launch_token()
    client = desktop_client(identity_db)

    opened = client.get(f"/desktop/launch/{token}", follow_redirects=False)
    assert opened.status_code == 303
    assert opened.headers["location"] == "/control-plane"
    cookie = opened.headers["set-cookie"]
    assert "aehub_session_token=" in cookie and "HttpOnly" in cookie

    # A reload with the cookie still opens the app; without it, refused.
    reload = client.get(f"/desktop/launch/{token}", follow_redirects=False)
    assert reload.status_code == 303

    stranger = desktop_client(identity_db)
    assert stranger.get(f"/desktop/launch/{token}", follow_redirects=False).status_code == 403


def test_launch_route_refuses_outside_desktop_mode(identity_db):
    client = desktop_client(identity_db)

    assert client.get("/desktop/launch/anything", follow_redirects=False).status_code == 403


def test_provider_keys_go_to_the_keyring_only(identity_db, monkeypatch):
    rebuilt = []
    monkeypatch.setattr(desktop_api, "rebuild_engine", lambda: rebuilt.append(True))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    outside = desktop_client(identity_db).put("/api/desktop/secrets", json={"OPENROUTER_API_KEY": "sk-or-1"})
    assert outside.status_code == 404

    store = MemoryStore()
    launch.enable(store)
    client = desktop_client(identity_db)

    assert client.get("/api/desktop").json() == {"desktop": True, "keyring": True}

    saved = client.put("/api/desktop/secrets", json={"OPENROUTER_API_KEY": " sk-or-1 "})
    assert saved.status_code == 200
    assert saved.json() == {"saved": ["OPENROUTER_API_KEY"]}
    assert "sk-or-1" not in saved.text
    assert store.values == {"OPENROUTER_API_KEY": "sk-or-1"}
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-1"
    assert rebuilt == [True]

    for bad in ({"AEHUB_SECRET_KEY": "x"}, {"OPENAI_API_KEY": ""}, {"OPENAI_API_KEY": "a b"}, {}):
        assert client.put("/api/desktop/secrets", json=bad).status_code == 422

    member = desktop_client(identity_db, MEMBER)
    assert member.put("/api/desktop/secrets", json={"OPENAI_API_KEY": "sk-1"}).status_code == 403


# ==============================================================================
# SIDECAR ENVIRONMENT
# ==============================================================================


def test_sidecar_environment(tmp_path):
    store = MemoryStore({"OPENAI_API_KEY": "sk-from-keyring", "AEHUB_SECRET_KEY": "login"})
    env = sidecar.desktop_environment(
        store,
        ["OPENAI_API_KEY", "GROQ_API_KEY", "AEHUB_SECRET_KEY"],
        "postgresql://aehub:pw@127.0.0.1:5555/aehub",
        6000,
        tmp_path,
        base={"AEHUB_ALLOWED_DIRS": "/mine", "REDIS_URL": "redis://elsewhere"},
    )

    assert env["OPENAI_API_KEY"] == "sk-from-keyring"
    assert "GROQ_API_KEY" not in env
    assert env["AEHUB_ALLOWED_DIRS"] == "/mine"
    assert env["AEHUB_EMBEDDER"] == "hash"
    assert env["REDIS_URL"] == "memory://" and env["AEHUB_EVENT_BUS"] == "memory"
    assert env["FRONTEND_URL"] == "http://127.0.0.1:6000"
    assert env["AEHUB_FRONTEND_DIR"] == str(tmp_path)
    assert env["POSTGRES_URL"].endswith("@127.0.0.1:5555/aehub")


def _requirements(name: str) -> Dict[str, str]:
    lines = (BACKEND / name).read_text(encoding="utf-8").splitlines()
    entries = [line.split("#")[0].strip() for line in lines]
    return {
        entry.split(">")[0].split("=")[0].split("[")[0].lower(): entry
        for entry in entries
        if entry
    }


def test_desktop_requirements_follow_the_backend_ones():
    backend = _requirements("requirements.txt")
    desktop = _requirements("requirements-desktop.txt")
    # Left out on purpose (ADR-020): the embedder's torch, and dev tools.
    left_out = {"sentence-transformers", "torch", "pytest", "pytest-asyncio", "ruff"}

    assert set(desktop) == set(backend) - left_out
    # Same constraint on every shared package, so both stay in step.
    assert {name: backend[name] for name in desktop} == desktop


def test_generated_secret_is_created_once():
    store = MemoryStore()

    first = sidecar.secret(store, "AEHUB_DESKTOP_DB_PASSWORD")
    assert len(first) >= 32
    assert sidecar.secret(store, "AEHUB_DESKTOP_DB_PASSWORD") == first


# ==============================================================================
# MANAGED POSTGRES
# ==============================================================================


def _pg_bin() -> Optional[Path]:
    from app.desktop.postgres import PostgresError, find_bin_dir

    for explicit in (os.getenv("AEHUB_TEST_PG_BIN"), None):
        try:
            return find_bin_dir(explicit)
        except PostgresError:
            continue

    return None


needs_postgres = pytest.mark.skipif(_pg_bin() is None, reason="PostgreSQL binaries not found (AEHUB_TEST_PG_BIN)")


@needs_postgres
def test_managed_cluster_lifecycle(tmp_path):
    import psycopg2

    from app.desktop.postgres import EmbeddedPostgres

    cluster = EmbeddedPostgres(bin_dir=_pg_bin(), data_dir=tmp_path / "pgdata", password="p@ss w/rd:1")

    try:
        cluster.start()
        assert cluster.initialized()

        conf = (tmp_path / "pgdata" / "postgresql.conf").read_text(encoding="utf-8")
        assert "listen_addresses = '127.0.0.1'" in conf

        with psycopg2.connect(cluster.url()) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_user, current_database()")
            assert cursor.fetchone() == ("aehub", "aehub")

        # Password authentication: a wrong password is refused.
        wrong = EmbeddedPostgres(bin_dir=cluster.bin_dir, data_dir=cluster.data_dir, password="nope", port=cluster.port)
        with pytest.raises(psycopg2.OperationalError):
            psycopg2.connect(wrong.url()).close()

        cluster.stop()
        assert not cluster.running()

        # A crash leaves postmaster.pid behind: the next start removes it.
        (tmp_path / "pgdata" / "postmaster.pid").write_text("999999\n", encoding="utf-8")
        cluster.port = 0
        cluster.start()
        assert cluster.running()
    finally:
        cluster.stop()


@needs_postgres
def test_second_instance_on_the_same_data_is_refused(tmp_path):
    from app.desktop.postgres import EmbeddedPostgres, PostgresError

    cluster = EmbeddedPostgres(bin_dir=_pg_bin(), data_dir=tmp_path / "pgdata", password="pw")

    try:
        cluster.start()
        second = EmbeddedPostgres(bin_dir=cluster.bin_dir, data_dir=cluster.data_dir, password="pw")
        with pytest.raises(PostgresError, match="already"):
            second.start()
    finally:
        cluster.stop()


def test_missing_binaries_are_reported(tmp_path, monkeypatch):
    from app.desktop.postgres import PostgresError, find_bin_dir

    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("AEHUB_PG_BIN", raising=False)

    with pytest.raises(PostgresError, match="AEHUB_PG_BIN"):
        find_bin_dir(str(tmp_path))


def test_sidecar_reports_errors_as_one_json_line(tmp_path):
    launcher = tmp_path / "fake_launcher.py"
    launcher.write_text(
        "SECRETS = {}\n"
        "class Store:\n"
        "    def get(self, key): return None\n"
        "    def set(self, key, value): pass\n"
        "def open_store(): return Store()\n"
        "def ensure_login_key(store): return False\n",
        encoding="utf-8",
    )
    env = {**os.environ, "AEHUB_LAUNCHER": str(launcher), "PATH": str(tmp_path)}
    env.pop("AEHUB_PG_BIN", None)

    result = subprocess.run(
        [sys.executable, str(BACKEND / "desktop.py"), "--data-dir", str(tmp_path / "data"), "--pg-bin", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert result.returncode == 1
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0]["event"] == "error"
    assert "PostgreSQL binaries not found" in lines[0]["message"]
    assert shutil.which("initdb", path=str(tmp_path)) is None
