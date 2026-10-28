"""
@file backend/app/api/memory.py
@description Long-term memory API of the authenticated user (roadmap M6,
extended in F6, ADR-027).

GET    /api/memory                list memories (by kind, trust, or a search
                                  with the hybrid retrieval of the engine),
                                  with counts and the memory's settings
POST   /api/memory                add a fact, preference or rule written by
                                  the user
POST   /api/memory/preferences    add a preference written by the user (M11)
PUT    /api/memory/{memory_id}    edit a memory: text, kind, trust
DELETE /api/memory/{memory_id}    forget one memory
DELETE /api/memory?scope=untrusted
                                  forget every memory written from untrusted
                                  content
POST   /api/memory/reembed        embed again, with the current embedder, the
                                  memories and document chunks whose vectors
                                  came from another one

Every call is scoped to the caller's workspace and principal. Text written
or edited here comes from the user: it passes the input guardrail and the
secret check, like a preference, because a preference or rule reaches the
Project level (L2) of every later run. Marking an untrusted memory as
trusted is written to the audit chain first.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent_engine.guardrails import (
    GuardrailException,
    InputGuardrail,
    contains_secret,
)
from app.core.security import Principal, resolve_principal
from app.memory.store import CHUNK_MAX_CHARS, MemoryKind, MemoryStore


router = APIRouter(
    prefix="/api/memory",
    tags=["memory"],
)

MAX_PREFERENCE_CHARS = 2000

# Kinds the user writes; episodes come from runs.
UserKind = Literal["fact", "preference", "rule"]


class PreferenceIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PREFERENCE_CHARS)


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=CHUNK_MAX_CHARS)
    kind: UserKind = "fact"


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=CHUNK_MAX_CHARS)
    kind: Optional[MemoryKind] = None
    trusted: Optional[bool] = None


def _store(principal: Principal) -> MemoryStore:
    return MemoryStore(
        workspace_id=principal.workspace_id,
        principal_id=principal.id,
    )


def _check_user_text(content: str) -> None:
    # Injected into later prompts: no secrets, no jailbreak patterns.
    try:
        InputGuardrail.validate(content)
    except GuardrailException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if contains_secret(content):
        raise HTTPException(
            status_code=400,
            detail="Memories must not contain credentials or secrets.",
        )


def _status(store: MemoryStore) -> Dict[str, Any]:
    from app.core.runtime_config import config_value
    from app.memory.store import memory_enabled, min_similarity

    return {
        "enabled": memory_enabled(),
        "embedder": store.current_embedder_name(),
        "embedder_kind": config_value("AEHUB_EMBEDDER", "sentence-transformers"),
        "min_similarity": min_similarity(),
        **store.stats(),
    }


@router.get("")
async def list_memories(
    kind: Optional[MemoryKind] = Query(default=None),
    trust: Literal["all", "trusted", "untrusted"] = Query(default="all"),
    q: Optional[str] = Query(default=None, max_length=500),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    store = _store(principal)

    if q and q.strip():
        hits = await asyncio.to_thread(store.search, q, limit, max(limit, 20))
        if kind:
            hits = [hit for hit in hits if hit.kind == kind.value]
    else:
        hits = await asyncio.to_thread(
            store.list,
            [kind.value] if kind else None,
            False,
            limit,
        )

    if trust != "all":
        hits = [hit for hit in hits if hit.trusted == (trust == "trusted")]

    return {
        "memories": [hit.to_dict() for hit in hits],
        "status": await asyncio.to_thread(_status, store),
    }


async def _add(principal: Principal, content: str, kind: MemoryKind) -> Dict[str, Any]:
    content = content.strip()
    _check_user_text(content)

    stored = await asyncio.to_thread(
        _store(principal).add,
        content,
        kind,
        True,
        "user",
    )

    return {"stored": stored, "content": content, "kind": kind.value}


@router.post("", status_code=201)
async def add_memory(
    body: MemoryIn,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return await _add(principal, body.content, MemoryKind(body.kind))


@router.post("/preferences", status_code=201)
async def add_preference(
    body: PreferenceIn,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return await _add(principal, body.content, MemoryKind.PREFERENCE)


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    body: MemoryUpdate,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    store = _store(principal)
    current = await asyncio.to_thread(store.get, memory_id)

    if current is None:
        raise HTTPException(status_code=404, detail="No memory with this id in your scope.")

    content = body.content.strip() if body.content is not None else current.content
    promote = body.trusted is True and not current.trusted

    # New text is the user's; a memory the user vouches for will steer later
    # runs. Both pass the same checks as a preference.
    if body.content is not None or promote:
        _check_user_text(content)

    if promote:
        from app.core.db import SessionLocal
        from app.runtime.audit_chain import append_audit_record

        with SessionLocal() as db:
            append_audit_record(
                db,
                session_id="control-plane",
                principal_id=principal.id,
                workspace_id=principal.workspace_id,
                tool_name="memory.trust",
                risk="high",
                decision="ALLOW",
                success=True,
                execution_result=json.dumps(
                    {"id": memory_id, "kind": (body.kind or MemoryKind(current.kind)).value},
                    sort_keys=True,
                ),
            )

    try:
        updated = await asyncio.to_thread(
            store.update,
            memory_id,
            body.content,
            body.kind,
            body.trusted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="No memory with this id in your scope.")

    return updated.to_dict()


@router.delete("")
async def forget_untrusted(
    scope: Literal["untrusted"] = Query(...),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del scope
    deleted = await asyncio.to_thread(_store(principal).delete_untrusted)

    return {"deleted": deleted}


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


@router.post("/reembed")
async def reembed(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.documents.index import DocumentIndex

    try:
        memories = await asyncio.to_thread(_store(principal).reembed)
        documents = await asyncio.to_thread(DocumentIndex(workspace_id=principal.workspace_id).reembed)
    except Exception as exc:
        # The model may be missing or the configuration invalid.
        raise HTTPException(status_code=503, detail=f"The embedder is not available: {exc}") from exc

    return {"memories": memories, "documents": documents}
