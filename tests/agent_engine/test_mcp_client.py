"""
@file tests/agent_engine/test_mcp_client.py
@description The MCP client (ADR-033) against a real MCP server over
Streamable HTTP on this computer.

- the tools of an allowlisted server are listed as mcp_<server>_<tool>,
  HIGH risk, approval on every call, output untrusted;
- a call returns the server's text; a tool error is a failed call;
- the owner lowers the risk per tool (AEHUB_MCP_TOOL_RISK);
- the token of a host is sent to that host only;
- a server that does not answer shows its error and keeps no tool;
- plain http leaves this computer never;
- through the real engine an MCP tool parks the run on an approval, and the
  server is not called before it.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any, Dict, List

import pytest
import uvicorn

from app.agent_engine.application import AgentEngine
from app.agent_engine.runtime import AgentRuntime
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum
from app.skills import mcp_bridge
from app.skills.base import RiskLevel
from app.skills.registry import SkillRegistry


# ==============================================================================
# A REAL MCP SERVER
# ==============================================================================


class Recorder:
    """
    ASGI wrapper that keeps the Authorization header of every request.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.authorization: List[str] = []
        self.calls: List[Dict[str, Any]] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            self.authorization.append(headers.get(b"authorization", b"").decode())
        await self.app(scope, receive, send)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def mcp_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("tickets")
    calls: List[Dict[str, Any]] = []

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        calls.append({"a": a, "b": b})
        return a + b

    @server.tool()
    def close_ticket(ticket_id: str) -> str:
        """Close a ticket."""
        calls.append({"ticket_id": ticket_id})
        return f"closed {ticket_id}"

    @server.tool()
    def broken() -> str:
        """Always fails."""
        raise ValueError("boom")

    app = Recorder(server.streamable_http_app())
    app.calls = calls
    port = _free_port()
    runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while not runner.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The test MCP server did not start.")
        time.sleep(0.05)

    app.url = f"http://127.0.0.1:{port}/mcp"
    app.port = port
    try:
        yield app
    finally:
        runner.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def registry():
    """A fresh registry with the `mcp` skill, and a clean skill after."""
    registry = SkillRegistry()
    registry.register_skill(mcp_bridge.get_skill())
    yield registry
    mcp_bridge.get_skill().load([], {})
    replace_stored({})


def _allow(*urls: str, **settings: str) -> None:
    replace_stored({"AEHUB_MCP_ALLOWED_SERVERS": ",".join(urls), **settings})


# ==============================================================================
# LISTING AND CALLING
# ==============================================================================


async def test_tools_are_listed_high_risk_and_untrusted(mcp_server, registry):
    _allow(mcp_server.url)

    status = await mcp_bridge.refresh_mcp_servers(registry)

    prefix = f"mcp_local{mcp_server.port}_"
    assert status == [
        {
            "url": mcp_server.url,
            "name": f"local{mcp_server.port}",
            "state": "connected",
            "tools": [prefix + "add", prefix + "broken", prefix + "close_ticket"],
            "error": None,
            "checked_at": status[0]["checked_at"],
            "token": False,
        }
    ]
    assert registry.get_skill_tool_names("mcp") == status[0]["tools"]

    metadata = registry.get_tool_metadata(prefix + "add")
    assert metadata.risk_level == RiskLevel.HIGH
    assert metadata.requires_approval is True
    assert metadata.untrusted_output is True
    assert metadata.network_access is True
    assert metadata.input_schema["required"] == ["a", "b"]
    assert metadata.description.startswith(f"[MCP local{mcp_server.port}] Add two numbers.")


async def test_a_call_returns_the_text_and_an_error_fails(mcp_server, registry):
    _allow(mcp_server.url)
    await mcp_bridge.refresh_mcp_servers(registry)
    prefix = f"mcp_local{mcp_server.port}_"

    add = registry.get_tool(prefix + "add")
    assert await add(a=2, b=3) == "5"
    assert mcp_server.calls == [{"a": 2, "b": 3}]

    with pytest.raises(RuntimeError, match="broken"):
        await registry.get_tool(prefix + "broken")()


async def test_the_owner_lowers_the_risk_of_one_tool(mcp_server, registry):
    prefix = f"mcp_local{mcp_server.port}_"
    _allow(mcp_server.url, AEHUB_MCP_TOOL_RISK=f"{prefix}add=low,{prefix}close_ticket=medium")
    await mcp_bridge.refresh_mcp_servers(registry)

    assert registry.get_tool_metadata(prefix + "add").risk_level == RiskLevel.LOW
    assert registry.get_tool_metadata(prefix + "add").requires_approval is False
    assert registry.get_tool_metadata(prefix + "close_ticket").risk_level == RiskLevel.MEDIUM
    assert registry.get_tool_metadata(prefix + "broken").requires_approval is True
    # Lowered or not, what a server returns stays third-party content.
    assert registry.get_tool_metadata(prefix + "add").untrusted_output is True

    # Back to high without reconnecting.
    _allow(mcp_server.url)
    mcp_bridge.refresh_mcp_risks(registry)
    assert registry.get_tool_metadata(prefix + "add").requires_approval is True


async def test_the_token_goes_to_its_host_only(mcp_server, registry, monkeypatch):
    _allow(mcp_server.url)
    monkeypatch.setenv(
        "AEHUB_MCP_TOKENS",
        f"mcp.notion.com=notion-token,127.0.0.1:{mcp_server.port}=local-token",
    )

    status = await mcp_bridge.refresh_mcp_servers(registry)

    assert status[0]["token"] is True
    assert mcp_server.authorization
    assert set(mcp_server.authorization) == {"Bearer local-token"}


async def test_a_server_that_does_not_answer_keeps_no_tool(mcp_server, registry):
    silent = f"http://127.0.0.1:{_free_port()}/mcp"
    _allow(silent, mcp_server.url)

    status = await mcp_bridge.refresh_mcp_servers(registry)

    assert status[0]["state"] == "error"
    assert status[0]["error"]
    assert status[0]["tools"] == []
    assert status[1]["state"] == "connected"
    assert all(name.startswith(f"mcp_local{mcp_server.port}_") for name in registry.get_skill_tool_names("mcp"))


async def test_a_server_left_out_of_the_allowlist_loses_its_tools(mcp_server, registry):
    _allow(mcp_server.url)
    await mcp_bridge.refresh_mcp_servers(registry)
    assert registry.get_skill_tool_names("mcp")

    _allow()
    mcp_bridge.refresh_mcp_risks(registry)

    assert registry.get_skill_tool_names("mcp") == []
    assert registry.get_tool(f"mcp_local{mcp_server.port}_add") is None


async def test_plain_http_stays_on_this_computer(registry):
    _allow("http://mcp.example.com/mcp")

    status = await mcp_bridge.refresh_mcp_servers(registry)

    assert status[0]["state"] == "error"
    assert "https" in status[0]["error"]


# ==============================================================================
# NAMES AND SETTINGS
# ==============================================================================


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("https://mcp.notion.com/mcp", "notion"),
        ("https://api.github-mcp.example.com/sse", "example"),
        ("https://calendar.example.org", "example"),
        ("http://localhost:8931/mcp", "local8931"),
        ("http://127.0.0.1/mcp", "local"),
    ],
)
def test_server_names(url, name):
    assert mcp_bridge.server_name(url) == name


def test_tool_names_are_safe_and_short():
    assert mcp_bridge.tool_name("notion", "search-Pages") == "mcp_notion_search_pages"
    assert len(mcp_bridge.tool_name("notion", "x" * 200)) == 64


def test_risk_and_token_settings_are_parsed():
    replace_stored({"AEHUB_MCP_TOOL_RISK": "mcp_a_b=low,mcp_c_d=high"})
    try:
        assert mcp_bridge.risk_overrides() == {"mcp_a_b": RiskLevel.LOW, "mcp_c_d": RiskLevel.HIGH}
    finally:
        replace_stored({})


def test_the_risk_setting_is_validated():
    from app.core.settings_service import SettingsValidationError, validate_changes

    assert validate_changes({"AEHUB_MCP_TOOL_RISK": "mcp_notion_search=low"})
    for bad in ("search=low", "mcp_notion_search=none", "mcp_a=low, mcp_b=high"):
        with pytest.raises(SettingsValidationError):
            validate_changes({"AEHUB_MCP_TOOL_RISK": bad})


# ==============================================================================
# THROUGH THE ENGINE
# ==============================================================================


async def test_an_mcp_tool_waits_for_approval_in_a_run(mcp_server, agent_infrastructure, fake_model):
    _allow(mcp_server.url)
    registry = agent_infrastructure.use_skills(mcp_bridge.get_skill())
    try:
        await mcp_bridge.refresh_mcp_servers(registry)
        tool = f"mcp_local{mcp_server.port}_close_ticket"

        engine = AgentEngine(
            model_provider=fake_model.adapter(
                [fake_model.function_call("call_close", tool, {"ticket_id": "T-1"})]
            ),
            checker_provider=fake_model.checker([]),
            runtime=AgentRuntime(),
        )
        owner = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-mcp")

        result = await engine.run(session_id="session-mcp", task="Close ticket T-1 in tickets.", principal=owner)

        parked = result["messages"][0].content
        assert parked["status"] == "WAITING_APPROVAL"
        assert parked["approval_id"]
        assert mcp_server.calls == []
    finally:
        mcp_bridge.get_skill().load([], {})
        replace_stored({})
