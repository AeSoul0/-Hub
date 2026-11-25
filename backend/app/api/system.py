"""
@file backend/app/api/system.py
@description The SISTEMA page (F9, ADR-030). Admin only, every route.

- GET  /api/system: app, database, event bus, startup parameters (read
  only, passwords hidden), memory of ÆHub's processes, voice models loaded;
- POST /api/system/updates/check: the latest published desktop version;
- GET  /api/system/events: search the flight recorder of the workspace;
- GET  /api/system/events/export: the same events as a JSONL file;
- GET/POST /api/system/evals: the offline evaluation suite, in a child
  process (it never runs a tool of this server);
- POST /api/system/access-key/rotate: a new Control Plane access key;
- GET  /api/system/logs: the backend's recent warnings and errors.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.log_buffer import recent_logs
from app.core.security import Principal, resolve_principal
from app.domain.models.identity import RoleEnum
from app.system import access_key, evals, recorder, status

router = APIRouter(
    prefix="/api/system",
    tags=["system"],
)

SESSION_COOKIE = "aehub_session_token"


def _require_admin(principal: Principal) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner can see the system.")


@router.get("")
async def system_status(principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    import asyncio

    _require_admin(principal)

    database = await asyncio.to_thread(status.database_status)
    memory = await asyncio.to_thread(status.memory_status)

    return {
        "app": status.app_status(),
        "database": database,
        "event_bus": await status.bus_status(),
        "startup": status.startup_parameters(),
        "memory": memory,
        "access_key": {"can_rotate": access_key.can_rotate()},
    }


@router.post("/updates/check")
async def check_updates(principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    _require_admin(principal)
    return await status.check_updates()


def _query(
    principal: Principal,
    q: Optional[str],
    event_type: Optional[str],
    run_id: Optional[str],
    since: Optional[str],
    until: Optional[str],
) -> recorder.RecorderQuery:
    return recorder.query_from(
        principal.workspace_id,
        text=q,
        event_type=event_type,
        run_id=run_id,
        since=since,
        until=until,
    )


@router.get("/events")
async def search_events(
    q: Optional[str] = Query(default=None, max_length=200),
    event_type: Optional[str] = Query(default=None, max_length=80),
    run_id: Optional[str] = Query(default=None, max_length=80),
    since: Optional[str] = Query(default=None, max_length=40),
    until: Optional[str] = Query(default=None, max_length=40),
    limit: int = Query(default=recorder.SEARCH_LIMIT, ge=1, le=1000),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    import asyncio

    _require_admin(principal)
    query = _query(principal, q, event_type, run_id, since, until)
    return await asyncio.to_thread(recorder.search, query, limit)


@router.get("/events/export")
async def export_events(
    q: Optional[str] = Query(default=None, max_length=200),
    event_type: Optional[str] = Query(default=None, max_length=80),
    run_id: Optional[str] = Query(default=None, max_length=80),
    since: Optional[str] = Query(default=None, max_length=40),
    until: Optional[str] = Query(default=None, max_length=40),
    principal: Principal = Depends(resolve_principal),
) -> StreamingResponse:
    _require_admin(principal)
    query = _query(principal, q, event_type, run_id, since, until)
    name = f"aehub-flight-recorder-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.jsonl"

    return StreamingResponse(
        recorder.export_lines(query),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/evals")
async def eval_status(principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    _require_admin(principal)
    return evals.current()


@router.post("/evals", status_code=202)
async def start_evals(principal: Principal = Depends(resolve_principal)) -> Dict[str, Any]:
    _require_admin(principal)

    try:
        return await evals.start(principal.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class RotateRequest(BaseModel):
    confirm: bool = False


@router.post("/access-key/rotate")
async def rotate_access_key(
    payload: RotateRequest,
    request: Request,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    """
    The new key is in this answer only: it is not stored anywhere the API
    can show it again.
    """
    _require_admin(principal)

    if not payload.confirm:
        raise HTTPException(status_code=428, detail="Confirm the rotation: every other session will be closed.")

    from app.core.db import SessionLocal
    from app.runtime.audit_chain import append_audit_record

    with SessionLocal() as db:
        try:
            key, closed = access_key.rotate(db, request.cookies.get(SESSION_COOKIE))
        except access_key.KeyStoreUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        append_audit_record(
            db,
            session_id="control-plane",
            principal_id=principal.id,
            workspace_id=principal.workspace_id,
            tool_name="access_key.rotate",
            risk="high",
            decision="ALLOW",
            success=True,
            execution_result=json.dumps({"sessions_closed": closed}),
        )

    return {"key": key, "sessions_closed": closed}


@router.get("/logs")
async def backend_logs(
    level: Optional[str] = Query(default=None, pattern="^(warning|error|critical)$"),
    limit: int = Query(default=200, ge=1, le=300),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    _require_admin(principal)
    return {"logs": recent_logs(limit, level)}
