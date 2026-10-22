"""
@file backend/app/api/memory.py
@description Long-term memory API of the authenticated user (roadmap M6).

GET    /api/memory                list memories (optionally by kind)
POST   /api/memory/preferences    add a preference written by the user
DELETE /api/memory/{memory_id}    forget one memory

Every call is scoped to the caller's workspace and principal. Preferences
added here come from the user, so they are trusted and reach the Project
level (L2) of every later run. Deleting is how the user removes a memory
they do not want, including one quarantined as untrusted.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent_engine.guardrails import (
    GuardrailException,
    InputGuardrail,
    contains_secret,
)
from app.core.security import Principal, resolve_principal
from app.memory.store import MemoryKind, MemoryStore


router = APIRouter(
    prefix="/api/memory",
    tags=["memory"],
)

MAX_PREFERENCE_CHARS = 2000


class PreferenceIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PREFERENCE_CHARS)


def _store(principal: Principal) -> MemoryStore:
    return MemoryStore(
        workspace_id=principal.workspace_id,
        principal_id=principal.id,
    )


@router.get("")
async def list_memories(
    kind: Optional[MemoryKind] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    hits = await asyncio.to_thread(
        _store(principal).list,
        [kind.value] if kind else None,
        False,
        limit,
    )

    return {"memories": [hit.to_dict() for hit in hits]}


@router.post("/preferences", status_code=201)
async def add_preference(
    body: PreferenceIn,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    content = body.content.strip()

    # A preference is injected into every later prompt: no secrets, no
    # jailbreak patterns.
    try:
        InputGuardrail.validate(content)
    except GuardrailException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if contains_secret(content):
        raise HTTPException(
            status_code=400,
            detail="Preferences must not contain credentials or secrets.",
        )

    stored = await asyncio.to_thread(
        _store(principal).add,
        content,
        MemoryKind.PREFERENCE,
        True,
        "user",
    )

    return {"stored": stored, "content": content}


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    deleted = await asyncio.to_thread(_store(principal).delete, memory_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="No memory with this id in your scope.",
        )

    return {"deleted": memory_id}
