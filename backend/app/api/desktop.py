"""
@file backend/app/api/desktop.py
@description Desktop app routes (roadmap M14, ADR-020).

GET /desktop/launch/{token}   one-time token -> owner session cookie -> app
GET /api/desktop              whether this is the desktop app, which keys are set
PUT /api/desktop/secrets      provider keys into the OS keyring (admin only)

In the desktop app there is no terminal for `scripts/aehub.py setup`, so the
setup page saves provider keys here. Values are written to the keyring and
to this process's environment, never to the database or a file, and are
never returned.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth import open_admin_session, set_session_cookie
from app.core.db import get_db
from app.core.security import IdentityService, Principal, RoleEnum, resolve_principal
from app.core.settings_service import SECRETS, rebuild_engine
from app.desktop.launch import consume_launch_token, desktop_mode, secret_store


router = APIRouter(tags=["desktop"])

SECRET_NAMES = {name for name, _label, _purpose in SECRETS}
MAX_SECRET_LENGTH = 512
APP_PATH = "/control-plane"

_EXPIRED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>ÆHub</title>"
    "<p>This launch link has already been used or has expired. Close ÆHub and open it again.</p>"
)


@router.get("/desktop/launch/{token}", include_in_schema=False)
async def launch(token: str, request: Request, db: Session = Depends(get_db)):
    if consume_launch_token(token):
        response = RedirectResponse(APP_PATH, status_code=303)
        set_session_cookie(response, open_admin_session(db))
        return response

    # A reload of the launch page after the exchange: the cookie is there.
    session_token = request.cookies.get("aehub_session_token")
    if desktop_mode() and session_token and IdentityService.validate_session(db, session_token):
        return RedirectResponse(APP_PATH, status_code=303)

    return HTMLResponse(_EXPIRED_PAGE, status_code=403)


@router.get("/api/desktop")
async def desktop_status(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del principal

    return {
        "desktop": desktop_mode(),
        "keyring": secret_store() is not None,
    }


@router.put("/api/desktop/secrets")
async def save_secrets(
    payload: Dict[str, Any],
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner can change keys.")

    store = secret_store()
    if not desktop_mode() or store is None:
        raise HTTPException(
            status_code=404,
            detail="Keys are set with: python scripts/aehub.py setup",
        )

    errors: Dict[str, str] = {}
    values: Dict[str, str] = {}

    for name, value in payload.items():
        if name not in SECRET_NAMES:
            errors[name] = "Unknown key."
        elif not isinstance(value, str) or not value.strip():
            errors[name] = "Must be a non-empty string."
        elif len(value) > MAX_SECRET_LENGTH or any(ch.isspace() for ch in value.strip()):
            errors[name] = "Does not look like a key."
        else:
            values[name] = value.strip()

    if errors or not values:
        raise HTTPException(status_code=422, detail=errors or {"": "No key given."})

    for name, value in values.items():
        store.set(name, value)
        os.environ[name] = value

    # Adapters read their key when the engine is built.
    rebuild_engine()

    return {"saved": sorted(values)}
