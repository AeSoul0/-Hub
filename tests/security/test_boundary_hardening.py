"""
@file tests/security/test_boundary_hardening.py
@description Session, WebSocket and MCP boundary hardening (roadmap M3).

- session tokens are stored hashed, and the stored hash is not a credential;
- the X-Session-ID header is no longer accepted as a credential;
- the WebSocket rejects foreign or missing Origins and scopes its runs to
  the login session, not to the user id;
- the MCP bridge only connects to allowlisted servers and marks every MCP
  tool output as untrusted.
"""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.api import realtime
from app.core.db import get_db
from app.core.security import (
    SESSION_COOKIE,
    IdentityService,
    Principal,
    hash_session_token,
    is_origin_allowed,
    resolve_principal,
)
from app.domain.models.identity import (
    Base,
    RoleEnum,
    Session as SessionModel,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.skills.base import ToolMetadata
from app.skills.mcp_bridge import MCPSkillWrapper


FRONTEND = "http://localhost:3000"


# ==============================================================================
# FIXTURES
# ==============================================================================


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
            Workspace.__table__,
            User.__table__,
            WorkspaceMembership.__table__,
            SessionModel.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def login(identity_db):
    """
    Create a user, a workspace membership and a session; return the token.
    """
    with identity_db() as db:
        db.add(Workspace(id="ws-1", name="ws"))
        user = User(username="alice", hashed_password="x")
        db.add(user)
        db.flush()
        db.add(
            WorkspaceMembership(
                user_id=user.id,
                workspace_id="ws-1",
                role=RoleEnum.ADMIN,
            )
        )
        db.commit()
        user_id = user.id

        token = IdentityService.create_session(
            db=db,
            user_id=user_id,
            workspace_id="ws-1",
            role=RoleEnum.ADMIN,
        )

    return {"token": token, "user_id": user_id}


@pytest.fixture(autouse=True)
def frontend_origin(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", FRONTEND)
    monkeypatch.delenv("AEHUB_ALLOWED_ORIGINS", raising=False)


# ==============================================================================
# SESSION TOKENS
# ==============================================================================


def test_session_token_is_stored_hashed(identity_db, login):
    token = login["token"]

    with identity_db() as db:
        rows = db.query(SessionModel).all()

        assert [row.id for row in rows] == [
            hashlib.sha256(token.encode()).hexdigest()
        ]
        assert token not in {row.id for row in rows}

        assert IdentityService.validate_session(db, token) is not None
        # A leaked row id is not a usable cookie.
        assert IdentityService.validate_session(db, rows[0].id) is None


def test_invalidate_session_uses_the_hash(identity_db, login):
    with identity_db() as db:
        IdentityService.invalidate_session(db, login["token"])
        assert db.query(SessionModel).count() == 0


def _principal_app(identity_db) -> TestClient:
    app = FastAPI()

    def override_db():
        with identity_db() as db:
            yield db

    @app.get("/whoami")
    def whoami(principal: Principal = Depends(resolve_principal)):
        return {"id": principal.id}

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_x_session_id_header_is_not_a_credential(identity_db, login):
    client = _principal_app(identity_db)

    response = client.get("/whoami", headers={"X-Session-ID": login["token"]})

    assert response.status_code == 401


def test_session_cookie_is_the_credential(identity_db, login):
    client = _principal_app(identity_db)
    client.cookies.set(SESSION_COOKIE, login["token"])

    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"id": login["user_id"]}


# ==============================================================================
# WEBSOCKET
# ==============================================================================


def test_origin_allowlist(monkeypatch):
    monkeypatch.setenv("AEHUB_ALLOWED_ORIGINS", "https://hub.example, http://127.0.0.1:3000/")

    assert is_origin_allowed(FRONTEND)
    assert is_origin_allowed("https://hub.example")
    assert is_origin_allowed("http://127.0.0.1:3000")
    assert not is_origin_allowed("https://evil.example")
    assert not is_origin_allowed("null")
    assert not is_origin_allowed(None)


def _ws_client() -> TestClient:
    app = FastAPI()
    app.include_router(realtime.router)
    return TestClient(app)


@pytest.mark.parametrize("origin", ["https://evil.example", None])
def test_websocket_rejects_foreign_or_missing_origin(identity_db, login, origin):
    headers = {"cookie": f"{SESSION_COOKIE}={login['token']}"}
    if origin:
        headers["origin"] = origin

    with patch("app.core.db.SessionLocal", identity_db):
        with pytest.raises(WebSocketDisconnect) as closed:
            with _ws_client().websocket_connect("/ws/orchestrator", headers=headers) as ws:
                ws.receive_text()

    assert closed.value.code == 1008


def test_websocket_scopes_runs_to_the_login_session(identity_db, login):
    respond = AsyncMock(return_value={"transcription": "ok"})

    # The real event bus starts a Redis listener inside the TestClient loop,
    # which can hang its shutdown; this test is about session scoping.
    bus = SimpleNamespace(
        subscribe=lambda session_id: asyncio.Queue(),
        unsubscribe=lambda session_id, queue: None,
    )

    with (
        patch("app.core.db.SessionLocal", identity_db),
        patch("app.agents.orchestrator.generate_ai_response", respond),
        patch("app.api.realtime.event_bus", bus),
    ):
        headers = {
            "origin": FRONTEND,
            "cookie": f"{SESSION_COOKIE}={login['token']}",
        }

        with _ws_client().websocket_connect("/ws/orchestrator", headers=headers) as ws:
            ws.send_json({"type": "text_input", "data": "hello"})
            assert ws.receive_json() == {"type": "status", "data": "thinking"}
            assert ws.receive_json()["type"] == "stream_end"

    session_id = respond.await_args.args[3]

    assert session_id == hash_session_token(login["token"])
    assert session_id != login["user_id"]
    assert respond.await_args.kwargs["principal"].id == login["user_id"]


# ==============================================================================
# MCP ALLOWLIST
# ==============================================================================


def test_mcp_bridge_rejects_unlisted_server(monkeypatch):
    monkeypatch.delenv("AEHUB_MCP_ALLOWED_SERVERS", raising=False)

    with pytest.raises(PermissionError, match="AEHUB_MCP_ALLOWED_SERVERS"):
        MCPSkillWrapper("tickets", "https://mcp.example/sse", "Tickets")


def test_mcp_bridge_accepts_allowlisted_server(monkeypatch):
    monkeypatch.setenv(
        "AEHUB_MCP_ALLOWED_SERVERS",
        "https://other.example/sse, HTTPS://MCP.example/sse/",
    )

    bridge = MCPSkillWrapper("tickets", "https://mcp.example/sse", "Tickets")

    assert bridge.metadata.name == "mcp_tickets"

    with pytest.raises(PermissionError):
        MCPSkillWrapper("evil", "https://mcp.example.evil/sse", "Evil")


def test_mcp_tools_are_always_untrusted(monkeypatch):
    monkeypatch.setenv("AEHUB_MCP_ALLOWED_SERVERS", "https://mcp.example/sse")
    bridge = MCPSkillWrapper("tickets", "https://mcp.example/sse", "Tickets")

    def list_tickets() -> str:
        return "[]"

    bridge.register_tool(
        list_tickets,
        ToolMetadata(
            name="list_tickets",
            description="List tickets.",
            untrusted_output=False,
        ),
    )

    assert bridge.tools == [list_tickets]
    assert bridge.get_tool_metadata()["list_tickets"].untrusted_output is True
