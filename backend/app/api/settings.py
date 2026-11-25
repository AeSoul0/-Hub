"""
@file backend/app/api/settings.py
@description Settings and first-run setup for the Control Plane (M12).

GET  /api/settings             model roles, prices and limits with where each
                               value comes from; which secrets are set (never
                               their values); configuration issues; whether
                               the first-run setup is done.
PUT  /api/settings             change settings without a restart (admin).
                               Invalid values are refused as a whole (422).
POST /api/settings/onboarding  mark the first-run setup done (admin). Refused
                               (409) while an error would stop every run.
GET  /api/settings/provider-models/{provider}
                               the models openai, openrouter or local offer,
                               for the role editor (F4); OpenRouter with
                               prices. Suggestions: nothing is saved.

Secrets are not editable here: the launcher keeps them in the OS keyring.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, resolve_principal
from app.domain.models.identity import RoleEnum


router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
)


class SettingsUpdate(BaseModel):
    # Setting name -> new value; null or "" goes back to the environment.
    values: Dict[str, Optional[str]] = Field(default_factory=dict, max_length=64)


def _require_admin(principal: Principal) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can change settings.")


@router.get("")
async def get_settings(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.core.settings_service import settings_view

    del principal

    with SessionLocal() as db:
        return settings_view(db)


@router.put("")
async def update_settings(
    update: SettingsUpdate,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.core.settings_service import (
        SettingsValidationError,
        save_settings,
        settings_view,
    )

    _require_admin(principal)

    with SessionLocal() as db:
        try:
            save_settings(
                db,
                update.values,
                principal_id=principal.id,
                workspace_id=principal.workspace_id,
            )
        except SettingsValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": "Settings not saved.", "errors": exc.errors},
            ) from exc

        _apply_mcp_changes(update.values)

        return settings_view(db)


_mcp_refreshes: set = set()


def _apply_mcp_changes(changes: Dict[str, Any]) -> None:
    """
    A new risk applies to the next run; a new allowlist reconnects in the
    background (ADR-033), so the save does not wait for the servers.
    """
    from app.skills.mcp_bridge import refresh_mcp_risks, refresh_mcp_servers

    if "AEHUB_MCP_TOOL_RISK" in changes or "AEHUB_MCP_ALLOWED_SERVERS" in changes:
        refresh_mcp_risks()

    if "AEHUB_MCP_ALLOWED_SERVERS" in changes:
        task = asyncio.create_task(refresh_mcp_servers())
        _mcp_refreshes.add(task)
        task.add_done_callback(_mcp_refreshes.discard)


@router.get("/provider-models/{provider}")
async def list_provider_models(
    provider: Literal["openai", "openrouter", "local", "groq", "anthropic", "google"],
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    from app.agent_engine.catalog import CatalogUnavailable, provider_models

    del principal

    try:
        models = await asyncio.to_thread(provider_models, provider)
    except CatalogUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"provider": provider, "models": models}


@router.post("/onboarding")
async def finish_onboarding(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.core.settings_service import (
        SettingsValidationError,
        complete_onboarding,
        settings_view,
    )

    _require_admin(principal)

    with SessionLocal() as db:
        try:
            complete_onboarding(db, principal.id)
        except SettingsValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": "Fix the configuration errors first.", "errors": exc.errors},
            ) from exc

        return settings_view(db)
