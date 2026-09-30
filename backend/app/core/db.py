"""
@file backend/app/core/db.py
@description Implements db.py. Core components: general logic modules.

This module manages the internal business logic for general logic modules.
It provides specialized functionality to handle: get_db.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db")

# Synchronous engine for Identity/Security layer
engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Executes get_db logic.
    """
    """
    Dependency for FastAPI endpoints to yield a database session.
    Ensures safe resource teardown.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
