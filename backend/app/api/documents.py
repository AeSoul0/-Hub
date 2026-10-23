"""
@file backend/app/api/documents.py
@description Document index of the working folder (roadmap M13).

GET  /api/documents        indexed files of the caller's workspace
POST /api/documents/sync   bring the index in line with the folder now

Searching happens only through the `search_documents` agent tool. These
routes read file names and contents of the working folder, so they need the
same FILESYSTEM_ACCESS permission as the tool.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import ROLE_PERMISSIONS, Permission, Principal, resolve_principal
from app.documents.index import DocumentIndex


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
    }


@router.post("/sync")
async def sync_documents(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    report = await asyncio.to_thread(_index(principal).sync)

    return report.to_dict()
