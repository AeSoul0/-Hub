"""
@file backend/app/api/conversations.py
@description The Nucleo's past conversations (N6): list, search, resume.

GET /api/conversations          the caller's conversations, newest first,
                                with their first command as title; ?q=
                                searches the commands and the answers
GET /api/conversations/{id}     the turns of one conversation, oldest first
                                (/_ for the principal's own session)

A conversation is a session: the Nucleo sends its id with each command
(Form "conversation") and the engine runs it in the session
"<principal>~<id>", whose recent turns and summary are what the agents
remember of it (N3). A command sent without an id goes on in the principal's
own session, listed here with the id "" (its path is /_). Resuming a conversation is sending
the next command with its id.

The turns are the commands the user started (the top-level runs, never a
subagent's) with their answer, read from the runs of the caller's own
workspace and principal. Instant commands and approvals by voice run
without the engine and leave no run, so they are not listed. Nothing here
runs a tool or reaches a model.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.orchestrator import CONVERSATION_SEPARATOR, command_id_of
from app.core.security import Principal, resolve_principal

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
)

TITLE_CHARS = 120
ANSWER_CHARS = 4000
MAX_TURNS = 200
# The path of the principal's own session, the conversation with the id "".
OWN_SESSION = "_"


def _conversation_of(session_id: str, principal_id: str) -> Optional[str]:
    """The conversation id of a session of the principal, or None."""
    if session_id == principal_id:
        return ""
    prefix = principal_id + CONVERSATION_SEPARATOR
    if session_id.startswith(prefix):
        rest = session_id[len(prefix):]
        return rest if command_id_of(rest) == rest else None
    return None


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _answer(row: Any) -> str:
    """What the user read as the answer: the text, or one line for a run that did not end with one."""
    from app.agents.orchestrator import _stopped_note

    raw = row.result
    try:
        value: Any = json.loads(raw) if raw is not None else None
    except (TypeError, ValueError):
        value = raw
    if isinstance(value, str):
        return _cut(value, ANSWER_CHARS)
    note = _stopped_note(value)
    if note:
        return note
    if row.error:
        return _cut(f"Error: {row.error}", ANSWER_CHARS)
    return ""


def _turns(principal: Principal) -> Dict[str, List[Dict[str, Any]]]:
    """The principal's top-level runs by conversation, oldest first."""
    from app.api.runs import _snapshot
    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    with SessionLocal() as db:
        rows = (
            db.query(DbAgentRun)
            .filter(DbAgentRun.principal_id == principal.id)
            .order_by(DbAgentRun.created_at.asc())
            .all()
        )
        for row in rows:
            conversation = _conversation_of(str(row.session_id or ""), principal.id)
            if conversation is None:
                continue
            snapshot = _snapshot(row)
            if snapshot is None or snapshot.get("workspace_id") != principal.workspace_id:
                continue
            if snapshot.get("parent_run_id"):
                continue
            task = ((snapshot.get("current_state") or {}).get("worker_context") or {}).get("task")
            if isinstance(task, dict):
                channel = task.get("input_channel") or "text"
                task = task.get("description")
            else:
                channel = "text"
            if not isinstance(task, str) or not task.strip():
                continue
            grouped.setdefault(conversation, []).append(
                {
                    "run_id": row.id,
                    "task": _cut(task, ANSWER_CHARS),
                    "answer": _answer(row),
                    "status": str(row.status).lower(),
                    "channel": "voice" if channel == "voice" else "text",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
    return grouped


@router.get("")
async def list_conversations(
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    needle = (q or "").strip().lower()
    found: List[Dict[str, Any]] = []
    for conversation, turns in _turns(principal).items():
        match = None
        if needle:
            match = next(
                (
                    turn
                    for turn in turns
                    if needle in turn["task"].lower() or needle in turn["answer"].lower()
                ),
                None,
            )
            if match is None:
                continue
        found.append(
            {
                "id": conversation,
                "title": _cut(turns[0]["task"], TITLE_CHARS),
                "turns": len(turns),
                "started_at": turns[0]["created_at"],
                "updated_at": turns[-1]["created_at"],
                # The turn that matched the search, to show why it is listed.
                "match": _cut(match["task"], TITLE_CHARS) if match else None,
            }
        )
    found.sort(key=lambda item: item["updated_at"] or "", reverse=True)
    return {"conversations": found[:limit], "total": len(found)}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    # "_" (never a conversation id) stands for the principal's own session, whose id is "".
    wanted = "" if conversation_id == OWN_SESSION else command_id_of(conversation_id)
    if conversation_id != OWN_SESSION and not wanted:
        raise HTTPException(status_code=404, detail="No such conversation.")
    turns = _turns(principal).get(wanted)
    if not turns:
        raise HTTPException(status_code=404, detail="No such conversation.")
    return {"id": wanted, "turns": turns[-MAX_TURNS:], "total": len(turns)}


__all__ = ["router"]
