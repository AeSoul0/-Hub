"""
@file backend/app/domain/models/runtime_state.py
@description SQLAlchemy persistence models for native Agent Runtime state.

This module provides durable records for:
- Agent Runtime execution state,
- tool idempotency results,
- principal execution budgets.

Security invariant:
principal_id is an explicit identity binding and must never be implicitly
replaced by a generic system identity.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    String,
    Text,
)

from app.domain.models.identity import Base


# ==============================================================================
# NATIVE AGENT RUN
# ==============================================================================


class AgentRun(Base):
    """
    Durable persistence record for a native Agent Runtime execution.

    The input_data column stores the complete serialized AgentRun snapshot.
    """

    __tablename__ = "agent_runs"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(
            uuid.uuid4()
        ),
    )

    session_id = Column(
        String,
        nullable=False,
        index=True,
    )

    principal_id = Column(
        String,
        nullable=False,
    )

    role = Column(
        String,
        nullable=False,
        default="agent",
    )

    input_data = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String,
        nullable=False,
        default="queued",
        index=True,
    )

    result = Column(
        Text,
        nullable=True,
    )

    error = Column(
        Text,
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


# ==============================================================================
# IDEMPOTENCY STATE
# ==============================================================================


class IdempotencyKey(Base):
    """
    Durable storage for idempotent tool execution results.

    Expired entries are removed by IdempotencyManager during lookup.
    """

    __tablename__ = "idempotency_keys"

    key = Column(
        String,
        primary_key=True,
    )

    result = Column(
        Text,
        nullable=False,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
    )


# ==============================================================================
# PRINCIPAL BUDGET
# ==============================================================================


class Budget(Base):
    """
    Durable execution budget scoped to one principal.

    consumed_budget tracks cumulative usage while max_budget represents the
    configured spending ceiling.
    """

    __tablename__ = "budgets"

    principal_id = Column(
        String,
        primary_key=True,
    )

    max_budget = Column(
        Float,
        nullable=False,
    )

    consumed_budget = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    currency = Column(
        String,
        nullable=False,
        default="USD",
    )


__all__ = [
    "AgentRun",
    "IdempotencyKey",
    "Budget",
]