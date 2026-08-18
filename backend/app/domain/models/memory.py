"""
@file backend/app/domain/models/memory.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Enum
import enum
from pgvector.sqlalchemy import Vector
from app.domain.models.identity import Base

class MemoryType(str, enum.Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"

class VectorMemory(Base):
    """
    Long-Term Memory Record (M4).
    Stores agent memories with vector embeddings for semantic retrieval.
    """
    __tablename__ = "vector_memory"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    memory_type = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384)) # 384 dimensions for all-MiniLM-L6-v2
    created_at = Column(DateTime, default=datetime.utcnow)
