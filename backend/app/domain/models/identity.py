"""
@file backend/app/domain/models/identity.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import enum
import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class RoleEnum(str, enum.Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    MEMBER = "member"
    USER = "user"
    GUEST = "guest"

class Workspace(Base):
    """
    Tenant-sensitive isolation boundary.
    """
    __tablename__ = "workspaces"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(16))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    """
    Authentication principal.
    """
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(16))
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class WorkspaceMembership(Base):
    """
    RBAC linkage between a User and a Workspace.
    """
    __tablename__ = "workspace_memberships"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(16))
    user_id = Column(String, ForeignKey("users.id"))
    workspace_id = Column(String, ForeignKey("workspaces.id"))
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.USER)
    
    user = relationship("User")
    workspace = relationship("Workspace")

class Session(Base):
    """
    Persistent session mapping to a user context.
    """
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(32))
    user_id = Column(String, ForeignKey("users.id"))
    workspace_id = Column(String, ForeignKey("workspaces.id"))
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.USER)
    expires_at = Column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7))
    created_at = Column(DateTime, default=datetime.utcnow)

class RefreshToken(Base):
    """
    Secure rotation artifact for active sessions.
    """
    __tablename__ = "refresh_tokens"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(32))
    user_id = Column(String, ForeignKey("users.id"))
    token = Column(String, unique=True, nullable=False, default=lambda: secrets.token_urlsafe(64))
    expires_at = Column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=30))
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
