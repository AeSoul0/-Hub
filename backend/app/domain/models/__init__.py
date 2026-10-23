"""
@file backend/app/domain/models/__init__.py
@description Public model registry for the A.U.R.O.R.A. domain layer.

This module imports all SQLAlchemy model classes that must be registered on the
shared declarative Base before metadata creation. Keeping the imports centralized
ensures that runtime persistence models are included in database initialization
and migrations without introducing duplicate Base declarations.
"""

# Identity and workspace domain models.
from .identity import (
    Base,
    Workspace,
    User,
    WorkspaceMembership,
    Session,
    RefreshToken,
    RoleEnum,
)

# Audit and memory domain models.
from .audit import AuditLog
from .memory import MemoryChunk, VectorMemory, MemoryType

# Runtime persistence models.
# Aliasing AgentRun avoids a naming collision with the Pydantic AgentRun model
# used by the orchestration layer.
from .runtime_state import (
    AgentRun as RuntimeAgentRun,
    IdempotencyKey,
    Budget,
    MonthlySpend,
)

# Settings edited from the Control Plane (M12).
from .settings import AppSetting

# Files of the working folder indexed for document search (M13).
from .documents import DocumentFile

__all__ = [
    "Base",
    "Workspace",
    "User",
    "WorkspaceMembership",
    "Session",
    "RefreshToken",
    "RoleEnum",
    "AuditLog",
    "MemoryChunk",
    "VectorMemory",
    "MemoryType",
    "RuntimeAgentRun",
    "IdempotencyKey",
    "Budget",
    "MonthlySpend",
    "AppSetting",
    "DocumentFile",
]