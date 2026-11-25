"""
@file backend/app/api/interface.py
@description The interface of the app (ADR-034).

GET /api/interface   the language of the pages, the language of the chosen
                     voice and whether the notice about the two is on.

Every page reads it at start and again on `interface.changed` (sent when the
settings change from IMPOSTAZIONI or by Aurora). Changes go through
PUT /api/settings (AEHUB_UI_LANGUAGE, AEHUB_VOICE_LANGUAGE_WARNING).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.interface import interface_state
from app.core.security import Principal, resolve_principal


router = APIRouter(
    prefix="/api/interface",
    tags=["interface"],
)


@router.get("")
async def get_interface(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del principal
    return interface_state()
