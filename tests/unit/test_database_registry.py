"""
@file tests/unit/test_database_registry.py
@description Unit tests for the shared SQLAlchemy model registry.

These tests verify that the application exposes exactly one declarative Base
and that runtime persistence models are registered on the same metadata object.
No database connection is required.
"""

from app.core.db import Base as DatabaseBase
from app.domain.models import (
    Base as DomainBase,
    Budget,
    IdempotencyKey,
    RuntimeAgentRun,
)


def test_database_and_domain_share_the_same_base() -> None:
    """
    The DB layer and domain registry must reference the exact same Base object.
    """
    assert DatabaseBase is DomainBase


def test_runtime_models_are_registered_on_shared_metadata() -> None:
    """
    Runtime persistence models must be visible through shared metadata.
    """
    tables = DatabaseBase.metadata.tables

    assert "agent_runs" in tables
    assert "idempotency_keys" in tables
    assert "budgets" in tables


def test_identity_tables_remain_registered() -> None:
    """
    Identity tables must remain part of the same metadata registry.
    """
    tables = DatabaseBase.metadata.tables

    assert "workspaces" in tables
    assert "users" in tables
    assert "workspace_memberships" in tables
    assert "sessions" in tables
    assert "refresh_tokens" in tables


def test_runtime_model_aliases_are_importable() -> None:
    """
    The public domain registry must expose runtime models without a naming
    collision with the Pydantic AgentRun model used by the engine.
    """
    assert RuntimeAgentRun.__tablename__ == "agent_runs"
    assert IdempotencyKey.__tablename__ == "idempotency_keys"
    assert Budget.__tablename__ == "budgets"