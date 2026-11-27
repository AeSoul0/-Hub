"""
@file backend/app/api/tools.py
@description Tools, skills and their boundaries for the Control Plane (F5,
ADR-026). Read only.

GET /api/tools   every registered skill with its tools: risk, approval,
                 network and file access, whether the output is untrusted,
                 whether the tool is enabled. Also the skill index, the
                 folders the tools may touch, the hosts the API answers to,
                 the allowed MCP servers and what each answered, and the
                 sandbox.
POST /api/tools/mcp/refresh   connect again to the MCP servers and list
                 their tools (ADR-033). Owner only.
GET    /api/tools/trash              what delete_path moved to ÆHub's trash (N5)
POST   /api/tools/trash/{id}/restore put an item back where it was
DELETE /api/tools/trash/{id}         remove one item for good
DELETE /api/tools/trash              empty the trash. Trash changes: owner only.

Changes go through PUT /api/settings (AEHUB_DISABLED_TOOLS,
AEHUB_TOOL_SELECTION, AEHUB_TOOL_TOP_K, AEHUB_MCP_ALLOWED_SERVERS,
AEHUB_MCP_TOOL_RISK), so they
are validated and audited like every setting. The folders and hosts are
startup parameters: the launcher or the environment sets them.
"""

from __future__ import annotations

import shutil
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import Principal, RoleEnum, resolve_principal


router = APIRouter(
    prefix="/api/tools",
    tags=["tools"],
)

TOOL_SETTINGS = (
    "AEHUB_DISABLED_TOOLS",
    "AEHUB_TOOL_SELECTION",
    "AEHUB_TOOL_TOP_K",
    "AEHUB_MCP_ALLOWED_SERVERS",
    "AEHUB_MCP_TOOL_RISK",
    "AEHUB_AGENT_FOLDERS",
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
    if name == "mcp" or name.startswith("mcp_"):
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
    from app.agent_engine.guardrails import agent_folders, working_directories
    from app.agent_engine.tool_selection import selection_status
    from app.core.runtime_config import source_of
    from app.core.security import allowed_hosts, disabled_tools
    from app.skills.mcp_bridge import configured_mcp_servers, get_skill as mcp_skill, risk_overrides
    from app.skills.registry import skill_registry

    del principal

    disabled = disabled_tools()

    return {
        "skills": tool_catalog(skill_registry, disabled),
        "disabled": sorted(disabled),
        "selection": selection_status(skill_registry),
        "boundaries": {
            # The working folders (AEHUB_ALLOWED_DIRS, set at start), then
            # the folders the owner chose for the agents (F11).
            "directories": [
                {"path": str(path), "exists": path.is_dir(), "kind": "working"}
                for path in working_directories()
            ]
            + [
                {"path": str(path), "exists": path.is_dir(), "kind": "agent"}
                for path in agent_folders()
            ],
            "api_hosts": allowed_hosts(),
            "mcp_servers": configured_mcp_servers(),
        },
        "mcp": {
            "servers": mcp_skill().status(),
            "risk": {name: level.value for name, level in sorted(risk_overrides().items())},
        },
        "sandbox": sandbox_status(),
        "sources": {name: source_of(name) for name in TOOL_SETTINGS},
    }


@router.post("/mcp/refresh")
async def refresh_mcp(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.skills.mcp_bridge import refresh_mcp_servers

    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner can reconnect the MCP servers.")

    return {"servers": await refresh_mcp_servers()}


# ==============================================================================
# TRASH (N5)
# ==============================================================================


def _owner(principal: Principal, action: str) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail=f"Only the owner can {action}.")


@router.get("/trash")
async def list_trash(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    from app.files import trash

    _owner(principal, "see the trash")
    items = await asyncio.to_thread(trash.list_items)
    return {"days": trash.keep_days(), "items": [item.to_dict() for item in items]}


@router.post("/trash/{item_id}/restore")
async def restore_trash_item(
    item_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    from app.files import trash

    _owner(principal, "restore from the trash")
    try:
        path = await asyncio.to_thread(trash.restore, item_id)
    except trash.TrashError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"restored": path}


@router.delete("/trash/{item_id}")
async def remove_trash_item(
    item_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    from app.files import trash

    _owner(principal, "empty the trash")
    try:
        await asyncio.to_thread(trash.remove, item_id)
    except trash.TrashError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"removed": item_id}


@router.delete("/trash")
async def empty_trash(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    from app.files import trash

    _owner(principal, "empty the trash")
    return {"removed": await asyncio.to_thread(trash.empty)}
