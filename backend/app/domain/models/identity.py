"""
@file backend/app/domain/models/identity.py
@description Identity, workspace, membership, session, and token models.

This module defines the foundational SQLAlchemy models for tenant isolation,
authentication, authorization, and session management.

The declarative Base is intentionally defined here and shared by the complete
domain model registry. Other persistence modules must import this Base rather
than creating an independent SQLAlchemy metadata registry.
"""

from __future__ import annotations

import enum
import secrets
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
)
from sqlalchemy.orm import declarative_base, relationship


# Single shared metadata registry for all application ORM models.
Base = declarative_base()


class RoleEnum(str, enum.Enum):
    """
    Supported application-level roles.
    """

    SYSTEM = "system"
    ADMIN = "admin"
    MEMBER = "member"
    USER = "user"
    GUEST = "guest"


class Workspace(Base):
    """
    Tenant isolation boundary.

    Every workspace-scoped operation must resolve to an explicit workspace
    before accessing tenant-sensitive resources.
    """

    __tablename__ = "workspaces"

    id = Column(
        String,
        primary_key=True,
        default=lambda: secrets.token_urlsafe(16),
    )
    name = Column(
        String,
        nullable=False,
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class User(Base):
    """
    Persistent authentication principal.
    """

    __tablename__ = "users"

    id = Column(
        String,
        primary_key=True,
        default=lambda: secrets.token_urlsafe(16),
    )
    username = Column(
        String,
        unique=True,
        nullable=False,
    )
    hashed_password = Column(
        String,
        nullable=False,
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class WorkspaceMembership(Base):
    """
    RBAC membership linking a user to a workspace.
    """

    __tablename__ = "workspace_memberships"

    id = Column(
        String,
        primary_key=True,
        default=lambda: secrets.token_urlsafe(16),
    )
    user_id = Column(
        String,
        ForeignKey("users.id"),
        nullable=False,
    )
    workspace_id = Column(
        String,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    role = Column(
        SQLEnum(RoleEnum),
        default=RoleEnum.USER,
        nullable=False,
    )

    user = relationship("User")
    workspace = relationship("Workspace")


class Session(Base):
    """
    Persistent authenticated session bound to a user and workspace.
    """

    __tablename__ = "sessions"

    id = Column(
        String,
        primary_key=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    user_id = Column(
        String,
        ForeignKey("users.id"),
        nullable=False,
    )
    workspace_id = Column(
        String,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    role = Column(
        SQLEnum(RoleEnum),
        default=RoleEnum.USER,
        nullable=False,
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(days=7),
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class RefreshToken(Base):
    """
    Persisted refresh-token rotation artifact.

    Only a hash of the refresh token is stored. The plaintext token must never
    be persisted in the database.
    """

    __tablename__ = "refresh_tokens"

    id = Column(
        String,
        primary_key=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    user_id = Column(
        String,
        ForeignKey("users.id"),
        nullable=False,
    )
    hashed_token = Column(
        String,
        unique=True,
        nullable=False,
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(days=30),
    )
    revoked = Column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


__all__ = [
    "Base",
    "RoleEnum",
    "Workspace",
    "User",
    "WorkspaceMembership",
    "Session",
    "RefreshToken",
]