"""
@file backend/app/domain/models/memory.py
@description Database Models for Memory Engine.

Defines the VectorMemory schema and MemoryType enumerations (including the new EXECUTION type).
Provides the foundational persistence structure for the Phase 6 Memory System utilizing pgvector.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Enum, Float
import enum
from pgvector.sqlalchemy import Vector
from app.domain.models.identity import Base

class MemoryType(str, enum.Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    EXECUTION = "execution"

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
    workspace_id = Column(String, nullable=True, index=True)
    importance = Column(Float, default=1.0)
    confidence = Column(Float, default=1.0)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

