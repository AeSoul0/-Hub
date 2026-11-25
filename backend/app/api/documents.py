"""
@file backend/app/api/documents.py
@description Document index of the working folder (roadmap M13, extended in
F6, ADR-027).

GET  /api/documents           indexed files of the caller's workspace, the
                              folder, the size limit and the totals
POST /api/documents/sync      bring the index in line with the folder now
POST /api/documents/upload    put a file in the working folder (admin), then
                              sync
GET  /api/documents/search    search the index, for the DOCUMENTI page
GET  /api/documents/passage   the text a citation [doc: path#location]
                              points to, for the answers that cite it

The agent searches through its `search_documents` tool; what these routes
return goes to the user's screen only, never to a model. They read file
names and contents of the working folder, so they need the same
FILESYSTEM_ACCESS permission as the tool. An upload is written to the audit
chain before the file is written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.security import ROLE_PERMISSIONS, Permission, Principal, resolve_principal
from app.domain.models.identity import RoleEnum
from app.documents.index import SUPPORTED_SUFFIXES, DocumentIndex, max_file_bytes


router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)


def _index(principal: Principal) -> DocumentIndex:
    if Permission.FILESYSTEM_ACCESS not in ROLE_PERMISSIONS.get(principal.role, []):
        raise HTTPException(status_code=403, detail="Reading the working folder needs file access.")

    return DocumentIndex(workspace_id=principal.workspace_id)


@router.get("")
async def list_documents(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    index = _index(principal)
    files = await asyncio.to_thread(index.files)

    return {
        "root": str(index.root),
        "root_exists": index.root.is_dir(),
        "files": files,
        "max_file_mb": round(max_file_bytes() / (1024 * 1024), 2),
        "suffixes": sorted(SUPPORTED_SUFFIXES),
        "totals": {
            "files": len(files),
            "chunks": sum(item["chunks"] or 0 for item in files),
            "errors": sum(1 for item in files if item["error"]),
        },
        "stale_vectors": await asyncio.to_thread(index.stale_vectors),
    }


@router.post("/sync")
async def sync_documents(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    report = await asyncio.to_thread(_index(principal).sync)

    return report.to_dict()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    replace: bool = Form(default=False),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.runtime.audit_chain import append_audit_record

    index = _index(principal)

    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can add files to the working folder.")

    limit = max_file_bytes()
    data = await file.read(limit + 1)

    if len(data) > limit:
        raise HTTPException(status_code=413, detail="The file is larger than the document size limit.")

    # Checked before the audit entry, so a refused name is not recorded as
    # allowed; save_upload checks again right before writing.
    try:
        await asyncio.to_thread(index.upload_target, file.filename or "", len(data), replace)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="A file with this name is already in the working folder.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with SessionLocal() as db:
        append_audit_record(
            db,
            session_id="control-plane",
            principal_id=principal.id,
            workspace_id=principal.workspace_id,
            tool_name="document.upload",
            risk="medium",
            decision="ALLOW",
            success=True,
            execution_result=json.dumps(
                {
                    "name": file.filename,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "replace": replace,
                },
                sort_keys=True,
            ),
        )

    try:
        path = await asyncio.to_thread(index.save_upload, file.filename or "", data, replace)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="A file with this name is already in the working folder.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report = await asyncio.to_thread(index.sync)

    return {"path": path, "sync": report.to_dict()}


@router.get("/search")
async def search_documents(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    hits = await asyncio.to_thread(_index(principal).search, q, limit)

    return {"hits": [hit.to_dict() for hit in hits]}


@router.get("/passage")
async def citation_passage(
    path: str = Query(min_length=1, max_length=1024),
    locator: str = Query(pattern=r"^(L\d+-\d+|p\d+)$"),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    content = await asyncio.to_thread(_index(principal).passage, path, locator)

    if content is None:
        raise HTTPException(status_code=404, detail="This citation is not in the document index.")

    return {"path": path, "locator": locator, "content": content}
