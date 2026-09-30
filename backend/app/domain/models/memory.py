"""
@file backend/app/domain/models/memory.py
@description Implements memory.py. Core components: MemoryType, VectorMemory.

This module manages the internal business logic for MemoryType, VectorMemory.
It provides specialized functionality to handle: utility operations.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Enum, Float
import enum
from pgvector.sqlalchemy import Vector
from app.domain.models.identity import Base

class DataClassification(str, enum.Enum):
    """
    Represents the DataClassification entity.
    """
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    CREDENTIAL = "credential-like"

class MemoryType(str, enum.Enum):
    """
    Represents the MemoryType entity and its core operations.
    """
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    EXECUTION = "execution"

class VectorMemory(Base):
    """
    Represents the VectorMemory entity and its core operations.
    """
    """
    Long-Term Memory Record (M4).
    Stores agent memories with vector embeddings for semantic retrieval.
    """
    __tablename__ = "vector_memory"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    memory_type = Column(String, nullable=False, index=True)
    classification = Column(String, nullable=False, default=DataClassification.INTERNAL.value)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384)) # 384 dimensions for all-MiniLM-L6-v2
    workspace_id = Column(String, nullable=False, index=True) # strict enforcement
    importance = Column(Float, default=1.0)
    confidence = Column(Float, default=1.0)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

