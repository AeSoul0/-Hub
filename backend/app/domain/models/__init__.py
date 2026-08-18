"""
@file backend/app/domain/models/__init__.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from .identity import Base, Workspace, User, WorkspaceMembership, Session, RefreshToken, RoleEnum
from .audit import AuditLog
from .memory import VectorMemory, MemoryType
