"""
@file backend/app/api/skills.py
@description Skills imported as SKILL.md files (F5, ADR-026).

GET    /api/skills              the imported skills, without their text.
GET    /api/skills/{skill_id}   one skill with its whole SKILL.md text.
POST   /api/skills/import       import from an https link or from the text
                                of a file (admin). The skill starts disabled.
PUT    /api/skills/{skill_id}   turn a skill on or off (admin).
DELETE /api/skills/{skill_id}   remove a skill (admin).

Nothing here runs a skill: the agent reads an enabled skill through the
`use_skill` tool, as untrusted content, through the Tool Gateway. Every
change is written to the audit chain first.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, resolve_principal
from app.domain.models.identity import RoleEnum
from app.skills.skill_md import MAX_SKILL_CHARS


router = APIRouter(
    prefix="/api/skills",
    tags=["skills"],
)


class SkillImport(BaseModel):
    # Exactly one of the two.
    url: Optional[str] = Field(default=None, max_length=2048)
    content: Optional[str] = Field(default=None, max_length=MAX_SKILL_CHARS + 1_000)
    # The uploaded file's name, kept as the source.
    filename: Optional[str] = Field(default=None, max_length=255)


class SkillUpdate(BaseModel):
    enabled: bool


def _require_admin(principal: Principal) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can change skills.")


@router.get("")
async def list_skills(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.domain.models.skills import ImportedSkill
    from app.skills.imported_skills import skill_record

    del principal

    with SessionLocal() as db:
        rows = db.query(ImportedSkill).order_by(ImportedSkill.name.asc()).all()
        return {
            "skills": [skill_record(row) for row in rows],
            "max_chars": MAX_SKILL_CHARS,
        }


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.domain.models.skills import ImportedSkill
    from app.skills.imported_skills import skill_record

    del principal

    with SessionLocal() as db:
        row = db.get(ImportedSkill, skill_id[:32])

        if row is None:
            raise HTTPException(status_code=404, detail="Skill not found.")

        return skill_record(row, with_content=True)


@router.post("/import")
async def import_skill(
    request: SkillImport,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.skills import imported_skills
    from app.skills.skill_md import (
        SkillFetchError,
        SkillFormatError,
        fetch_skill_md,
        parse_skill_md,
    )

    _require_admin(principal)

    url = (request.url or "").strip()
    content = request.content

    if bool(url) == (content is not None):
        raise HTTPException(status_code=422, detail="Send either a link or the text of a SKILL.md file.")

    try:
        if url:
            text, _ = await fetch_skill_md(url)
            source = url
        else:
            text = content or ""
            name = (request.filename or "SKILL.md").replace("\\", "/").rsplit("/", 1)[-1]
            source = f"file:{name or 'SKILL.md'}"

        parsed = parse_skill_md(text)
    except SkillFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SkillFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with SessionLocal() as db:
        row, replaced, changed = imported_skills.import_skill(
            db,
            parsed,
            source=source,
            principal_id=principal.id,
            workspace_id=principal.workspace_id,
        )

        record = imported_skills.skill_record(row, with_content=True)
        record["replaced"] = replaced
        record["changed"] = changed
        return record


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    update: SkillUpdate,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.skills.imported_skills import set_skill_enabled, skill_record

    _require_admin(principal)

    with SessionLocal() as db:
        row = set_skill_enabled(
            db,
            skill_id[:32],
            update.enabled,
            principal_id=principal.id,
            workspace_id=principal.workspace_id,
        )

        if row is None:
            raise HTTPException(status_code=404, detail="Skill not found.")

        return skill_record(row)


@router.delete("/{skill_id}")
async def remove_skill(
    skill_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.skills.imported_skills import delete_skill

    _require_admin(principal)

    with SessionLocal() as db:
        if not delete_skill(
            db,
            skill_id[:32],
            principal_id=principal.id,
            workspace_id=principal.workspace_id,
        ):
            raise HTTPException(status_code=404, detail="Skill not found.")

    return {"deleted": skill_id}
