"""
@file backend/app/core/db.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db")

# Synchronous engine for Identity/Security layer
engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency for FastAPI endpoints to yield a database session.
    Ensures safe resource teardown.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
