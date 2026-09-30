"""
@file backend/app/domain/models/identity.py
@description Implements identity.py. Core components: RoleEnum, Workspace, User, WorkspaceMembership, Session, RefreshToken.

This module manages the internal business logic for RoleEnum, Workspace, User, WorkspaceMembership, Session, RefreshToken.
It provides specialized functionality to handle: utility operations.
"""
import enum
import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class RoleEnum(str, enum.Enum):
    """
    Represents the RoleEnum entity and its core operations.
    """
    SYSTEM = "system"
    ADMIN = "admin"
    MEMBER = "member"
    USER = "user"
    GUEST = "guest"

class Workspace(Base):
    """
    Represents the Workspace entity and its core operations.
    """
    """
    Tenant-sensitive isolation boundary.
    """
    __tablename__ = "workspaces"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(16))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    """
    Represents the User entity and its core operations.
    """
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
    Represents the WorkspaceMembership entity and its core operations.
    """
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
    Represents the Session entity and its core operations.
    """
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
    Represents the RefreshToken entity and its core operations.
    """
    """
    Secure rotation artifact for active sessions.
    """
    __tablename__ = "refresh_tokens"
    
    id = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(32))
    user_id = Column(String, ForeignKey("users.id"))
    hashed_token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=30))
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
