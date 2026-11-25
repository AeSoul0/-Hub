"""
@file backend/app/api/tools.py
@description Tools, skills and their boundaries for the Control Plane (F5,
ADR-026). Read only.

GET /api/tools   every registered skill with its tools: risk, approval,
                 network and file access, whether the output is untrusted,
                 whether the tool is enabled. Also the skill index, the
                 folders the tools may touch, the hosts the API answers to,
                 the allowed MCP servers and the sandbox.

Changes go through PUT /api/settings (AEHUB_DISABLED_TOOLS,
AEHUB_TOOL_SELECTION, AEHUB_TOOL_TOP_K, AEHUB_MCP_ALLOWED_SERVERS), so they
are validated and audited like every setting. The folders and hosts are
startup parameters: the launcher or the environment sets them.
"""

from __future__ import annotations

import shutil
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.core.security import Principal, resolve_principal


router = APIRouter(
    prefix="/api/tools",
    tags=["tools"],
)

TOOL_SETTINGS = (
    "AEHUB_DISABLED_TOOLS",
    "AEHUB_TOOL_SELECTION",
    "AEHUB_TOOL_TOP_K",
    "AEHUB_MCP_ALLOWED_SERVERS",
)


def untrusted_output(metadata: Any) -> bool:
    """
    The provenance rule of the engine: explicit metadata wins, otherwise
    whatever comes from the network or the filesystem is untrusted.
    """
    declared = getattr(metadata, "untrusted_output", None)

    if declared is not None:
        return bool(declared)

    return bool(metadata.network_access or metadata.filesystem_access)


def skill_source(name: str) -> str:
    if name == "imported_skills":
        return "imported"
    if name.startswith("mcp_"):
        return "mcp"
    return "builtin"


def tool_catalog(registry: Any, disabled: Any) -> List[Dict[str, Any]]:
    skills: List[Dict[str, Any]] = []

    for skill_name in registry.get_registered_skill_names():
        skill = registry.get_skill(skill_name)
        tools = []

        for tool_name in registry.get_skill_tool_names(skill_name):
            metadata = registry.get_tool_metadata(tool_name)
            if metadata is None:
                continue
            tools.append(
                {
                    "name": tool_name,
                    "description": metadata.description,
                    "risk": getattr(metadata.risk_level, "value", str(metadata.risk_level)),
                    "requires_approval": metadata.requires_approval,
                    "network": metadata.network_access,
                    "filesystem": metadata.filesystem_access,
                    "modifies_files": metadata.modifies_files,
                    "untrusted_output": untrusted_output(metadata),
                    "enabled": tool_name not in disabled,
                }
            )

        skills.append(
            {
                "name": skill_name,
                "description": skill.metadata.description,
                "version": skill.metadata.version,
                "source": skill_source(skill_name),
                "tools": tools,
            }
        )

    return skills


def sandbox_status() -> Dict[str, Any]:
    from app.workers.sandbox import sandbox_manager

    return {
        "docker": shutil.which("docker") is not None,
        "image": sandbox_manager.image,
        "memory_limit": sandbox_manager.memory_limit,
        "network": not sandbox_manager.network_disabled,
    }


@router.get("")
async def list_tools(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.agent_engine.guardrails import allowed_directories
    from app.agent_engine.tool_selection import selection_status
    from app.core.runtime_config import source_of
    from app.core.security import allowed_hosts, disabled_tools
    from app.skills.mcp_bridge import configured_mcp_servers
    from app.skills.registry import skill_registry

    del principal

    disabled = disabled_tools()

    return {
        "skills": tool_catalog(skill_registry, disabled),
        "disabled": sorted(disabled),
        "selection": selection_status(skill_registry),
        "boundaries": {
            "directories": [
                {"path": str(path), "exists": path.is_dir()}
                for path in allowed_directories()
            ],
            "api_hosts": allowed_hosts(),
            "mcp_servers": configured_mcp_servers(),
        },
        "sandbox": sandbox_status(),
        "sources": {name: source_of(name) for name in TOOL_SETTINGS},
    }
