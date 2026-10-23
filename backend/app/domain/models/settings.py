"""
@file backend/app/domain/models/settings.py
@description Settings edited from the Control Plane (M12).

One row per edited setting, keyed by its environment name (see
app.core.runtime_config). A setting without a row falls back to the
environment. A separate table, so existing databases get it through
create_all.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.domain.models.identity import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(
        String(64),
        primary_key=True,
    )

    value = Column(
        Text,
        nullable=False,
    )

    updated_by = Column(
        String,
        nullable=True,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


__all__ = ["AppSetting"]
