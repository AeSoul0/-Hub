"""
@file backend/app/domain/models/skills.py
@description Skills imported as SKILL.md files (F5, ADR-026).

One row per skill, keyed by an id; the name is unique. The whole SKILL.md
text is kept as imported, with its SHA-256, so what the agent reads is
exactly what the user was shown before turning the skill on. A new skill
starts disabled. A separate table, so existing databases get it through
create_all.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from app.domain.models.identity import Base


class ImportedSkill(Base):
    __tablename__ = "imported_skills"

    id = Column(
        String(32),
        primary_key=True,
    )

    name = Column(
        String(64),
        unique=True,
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    # The SKILL.md text, front matter included.
    content = Column(
        Text,
        nullable=False,
    )

    # The https link it came from, or "file:<name>" for an uploaded file.
    source = Column(
        String(2048),
        nullable=False,
    )

    sha256 = Column(
        String(64),
        nullable=False,
    )

    # JSON list of warning codes found at import (see app.skills.skill_md).
    warnings = Column(
        Text,
        nullable=False,
        default="[]",
    )

    enabled = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    imported_by = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


__all__ = ["ImportedSkill"]
