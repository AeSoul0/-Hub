"""
@file backend/app/core/db.py
@description Shared synchronous SQLAlchemy database infrastructure.

This module provides the engine, session factory, and FastAPI database
dependency used by the A.U.R.O.R.A. application.

The SQLAlchemy declarative Base is imported from the identity domain models
instead of being recreated here. The project must use one shared metadata
registry so identity, audit, memory, runtime-state, budget, and idempotency
models are visible to the same engine and migration lifecycle.
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models.identity import Base


POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db",
)

# Shared synchronous SQLAlchemy engine.
engine = create_engine(
    POSTGRES_URL,
    pool_pre_ping=True,
)

# Centralized session factory used by application services and persistence
# managers. Transaction ownership remains explicit at the service boundary.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session and guarantee deterministic cleanup.

    This function is suitable for FastAPI dependency injection.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


__all__ = [
    "Base",
    "POSTGRES_URL",
    "engine",
    "SessionLocal",
    "get_db",
]