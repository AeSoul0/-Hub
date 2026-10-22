"""
@file backend/app/skills/mcp_bridge.py
@description Implements mcp_bridge.py. Core components: MCPSkillWrapper.

This module manages the internal business logic for MCPSkillWrapper.
It provides specialized functionality to handle: _initialize_mcp_tools, metadata, tools, get_tool_metadata, system_prompt_extension.
"""
import os
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlsplit

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
    comma-separated URLs). Empty means no MCP server is allowed.
    """
    configured = os.getenv("AEHUB_MCP_ALLOWED_SERVERS", "")
    return {
        _normalize_server_url(entry)
        for entry in configured.split(",")
        if entry.strip()
    }


def is_mcp_server_allowed(server_url: str) -> bool:
    return _normalize_server_url(server_url) in allowed_mcp_servers()


class MCPSkillWrapper(BaseSkill):
    """
    Represents the MCPSkillWrapper entity and its core operations.
    """
    """
    Dynamically wraps an MCP (Model Context Protocol) Server into an A.U.R.O.R.A. Skill.
    It fetches available tools from the MCP server and exposes them as Langchain tools.
    """
    
    def __init__(self, server_name: str, server_url: str, description: str):
        """
        Executes __init__ logic.
        """
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
        
        # Note: In a production environment, you would use `mcp.Client` (SSE or Stdio)
        # to connect to the server, call `list_tools()`, and map them to StructuredTool.
        # This is the Phase 6 bridge architecture.
        self._initialize_mcp_tools()
        
    def _initialize_mcp_tools(self):
        """
        Executes _initialize_mcp_tools logic.
        """
        """
        Placeholder for MCP `list_tools` mapping.
        Iterates through tools exposed by the MCP server and binds them to LangChain.
        """
        # Example dynamic tool generation logic:
        # async with sse_client(self._server_url) as streams:
        #     async with ClientSession(streams[0], streams[1]) as session:
        #         await session.initialize()
        #         mcp_tools = await session.list_tools()
        #         for t in mcp_tools.tools:
        #             lc_tool = self._create_langchain_tool(t, session)
        #             self._tools.append(lc_tool)
        pass

    @property
    def metadata(self) -> SkillMetadata:
        """
        Executes metadata logic.
        """
        return SkillMetadata(
            name=f"mcp_{self._server_name.lower().replace(' ', '_')}",
            description=f"MCP Integration: {self._description}",
            version="1.0.0",
            author="MCP Bridge"
        )
        
    @property
    def tools(self) -> List[Callable]:
        """
        Executes tools logic.
        """
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
        """
        Executes get_tool_metadata logic.
        """
        return self._tool_metadata
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Executes system_prompt_extension logic.
        """
        return f"You have access to the '{self._server_name}' MCP server tools. Use them when interacting with this external service."
