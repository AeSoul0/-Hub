"""
@file backend/app/skills/mcp_bridge.py
@description Bridge to MCP servers: only allowlisted servers (AEHUB_MCP_ALLOWED_SERVERS), every tool through the Tool Gateway, every output untrusted.
"""
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlsplit

from app.core.runtime_config import config_value

from .base import BaseSkill, SkillMetadata, ToolMetadata


def _normalize_server_url(url: str) -> str:
    """
    Canonical form used to compare a server URL with the allowlist.
    """
    parts = urlsplit(url.strip())
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def allowed_mcp_servers() -> Set[str]:
    """
    MCP servers the bridge may connect to (AEHUB_MCP_ALLOWED_SERVERS,
    comma-separated URLs, editable in the Control Plane since F5). Empty
    means no MCP server is allowed.
    """
    return {
        _normalize_server_url(entry)
        for entry in configured_mcp_servers()
    }


def configured_mcp_servers() -> List[str]:
    """
    The allowlist as written, for the Control Plane.
    """
    configured = config_value("AEHUB_MCP_ALLOWED_SERVERS", "") or ""
    return [entry.strip() for entry in configured.split(",") if entry.strip()]


def is_mcp_server_allowed(server_url: str) -> bool:
    return _normalize_server_url(server_url) in allowed_mcp_servers()


class MCPSkillWrapper(BaseSkill):
    """
    Dynamically wraps an MCP (Model Context Protocol) Server into an A.U.R.O.R.A. Skill.
    The connection is a stub (after V1): today the server is checked against
    the allowlist and exposes no tool; its output will be untrusted.
    """
    
    def __init__(self, server_name: str, server_url: str, description: str):
        """Refuse a server outside AEHUB_MCP_ALLOWED_SERVERS, then list its tools."""
        # Fail closed: only explicitly allowlisted servers are bridged.
        if not is_mcp_server_allowed(server_url):
            raise PermissionError(
                f"MCP server '{server_name}' ({server_url}) is not in "
                "AEHUB_MCP_ALLOWED_SERVERS."
            )

        self._server_name = server_name
        self._server_url = server_url
        self._description = description
        self._tools: List[Callable] = []
        self._tool_metadata: Dict[str, ToolMetadata] = {}
        
        # The real client (`mcp` over SSE or stdio: `list_tools()`, then one
        # tool per entry, through the Tool Gateway) comes after V1.
        self._initialize_mcp_tools()
        
    def _initialize_mcp_tools(self):
        """
        Map the server's tools to this skill: not connected yet (after V1),
        so the skill exposes no tool.
        """

    @property
    def metadata(self) -> SkillMetadata:
        """The skill's name and description, derived from the server name."""
        return SkillMetadata(
            name=f"mcp_{self._server_name.lower().replace(' ', '_')}",
            description=f"MCP Integration: {self._description}",
            version="1.0.0",
            author="MCP Bridge"
        )
        
    @property
    def tools(self) -> List[Callable]:
        """The tools listed by the MCP server and bound with register_tool."""
        return self._tools
        
    def register_tool(self, tool: Callable, metadata: ToolMetadata) -> None:
        """
        Bind one tool listed by the MCP server.

        MCP output is third-party content: it is always marked untrusted,
        whatever the server declares.
        """
        self._tools.append(tool)
        self._tool_metadata[metadata.name] = metadata.model_copy(
            update={"untrusted_output": True}
        )

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """Risk and schema of each bound tool; their output is always untrusted."""
        return self._tool_metadata
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """One line telling the model that this server's tools exist."""
        return f"You have access to the '{self._server_name}' MCP server tools. Use them when interacting with this external service."
