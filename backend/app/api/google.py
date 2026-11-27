"""
@file backend/app/api/google.py
@description The owner's Google account on STRUMENTI (N4, ADR-046).

GET    /api/google            whether the client keys are there, the account,
                              the redirect address to register at Google
                              (owner only)
POST   /api/google/connect    the URL of Google's consent page (owner only)
GET    /api/google/callback   where Google sends the browser back with a
                              one-time code; the state of the connection is
                              its proof, so it needs no session
DELETE /api/google            revoke the token and forget it (owner only)

Connecting and disconnecting are written to the audit chain. No tool runs
here: the agents use the account through the google skill and the Tool
Gateway.
"""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.core.security import Principal, RoleEnum, resolve_principal
from app.google import oauth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/google",
    tags=["google"],
)

RETURN_PATH = "/control-plane/tools"


def _owner(principal: Principal) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner can manage the Google account.")


def redirect_uri(request: Request) -> str:
    """The address Google sends the browser back to: AEHUB_GOOGLE_REDIRECT_URI, else this API's own."""
    configured = (os.getenv("AEHUB_GOOGLE_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    return f"{scheme}://{host}{oauth.CALLBACK_PATH}"


def _audit(owner_id: str, workspace_id: str, action: str, detail: Dict[str, Any]) -> None:
    from app.core.db import SessionLocal
    from app.runtime.audit_chain import append_audit_record

    with SessionLocal() as db:
        append_audit_record(
            db,
            session_id="control-plane",
            principal_id=owner_id or "owner",
            workspace_id=workspace_id,
            tool_name=f"google.{action}",
            risk="medium",
            decision="ALLOW",
            success=True,
            execution_result=json.dumps(detail, sort_keys=True),
        )


@router.get("")
async def google_status(request: Request, principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    _owner(principal)
    connected = bool(oauth.client_configured() and oauth.refresh_token())
    account = oauth.account()
    problem = None
    if connected and account is None:
        from app.google import api

        try:
            account = await api.profile()
        except (oauth.GoogleNotConnected, oauth.GoogleError) as exc:
            problem = str(exc)
        except Exception as exc:  # noqa: BLE001 - Google unreachable: the page says so
            problem = f"Google is not reachable: {exc}"
    return {
        "client_configured": oauth.client_configured(),
        "connected": connected,
        "account": account,
        "token_source": oauth.token_source(),
        "problem": problem,
        "redirect_uri": redirect_uri(request),
        "scopes": list(oauth.SCOPES),
        # Only once, and only where no keyring keeps it: to save as GOOGLE_REFRESH_TOKEN.
        "token_to_save": oauth.take_token_to_show(),
    }


class ConnectRequest(BaseModel):
    origin: str = ""


@router.post("/connect")
async def google_connect(body: ConnectRequest, request: Request, principal: Principal = Depends(resolve_principal)) -> Dict[str, str]:
    _owner(principal)
    # The page's own origin (checked by the origin guard for this POST).
    origin = (request.headers.get("origin") or body.origin or "").rstrip("/")
    if not origin.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="The page's origin is missing.")
    try:
        url = oauth.start(redirect_uri(request), origin + RETURN_PATH, principal.id, principal.workspace_id)
    except oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"url": url}


def _page(message: str) -> HTMLResponse:
    text = html.escape(message)
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>ÆHub · Google</title>"
        "<body style='background:#030714;color:#dce6ff;font-family:system-ui;padding:40px'>"
        f"<p>{text}</p><p>Torna su ÆHub → STRUMENTI → Google.</p></body>",
        status_code=400,
    )


@router.get("/callback")
async def google_callback(
    state: str = Query(default="", max_length=200),
    code: str = Query(default="", max_length=2000),
    error: str = Query(default="", max_length=200),
):
    flow = oauth.flow_of(state)
    if flow is None:
        return _page("Questo collegamento con Google è scaduto o è già stato usato.")
    if error or not code:
        # Refused at Google: the flow expires by itself; Connect starts another.
        separator = "&" if "?" in flow.return_to else "?"
        return RedirectResponse(f"{flow.return_to}{separator}google=refused", status_code=303)
    try:
        target, used = await oauth.finish(state, code)
    except (oauth.GoogleNotConnected, oauth.GoogleError) as exc:
        return _page(str(exc))
    account = None
    try:
        from app.google import api

        account = await api.profile()
    except Exception as exc:  # noqa: BLE001 - connected all the same; the page shows the problem
        logger.warning("Google profile not read: %s", exc)
    _audit(used.owner_id, used.workspace_id, "connect", {"account": account, "scopes": list(oauth.SCOPES)})
    return RedirectResponse(target, status_code=303)


@router.delete("")
async def google_disconnect(principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    _owner(principal)
    account = oauth.account()
    from_environment = oauth.token_source() == "environment"
    await oauth.disconnect()
    _audit(principal.id, principal.workspace_id, "disconnect", {"account": account})
    return {
        "disconnected": True,
        # A codespace or launcher secret comes back at the next start: remove it there too.
        "remove_secret": oauth.REFRESH_TOKEN if from_environment else None,
    }


__all__ = ["router"]
