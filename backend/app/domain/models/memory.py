"""
@file backend/app/domain/models/memory.py
@description Memory models: the long-term memory chunks of the agent (M6) and the legacy vector records.
"""
import uuid
from datetime import datetime
from sqlalchemy import DDL, Boolean, Column, String, DateTime, Text, Enum, Float, event, func, literal_column
import enum
from pgvector.sqlalchemy import Vector
from app.domain.models.identity import Base

class DataClassification(str, enum.Enum):
    """
    How sensitive a legacy memory record is.
    """
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    CREDENTIAL = "credential-like"

class MemoryType(str, enum.Enum):
    """The kind of a legacy vector memory record."""
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
    classification = Column(String, nullable=False, default=DataClassification.INTERNAL.value)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384)) # 384 dimensions for all-MiniLM-L6-v2
    workspace_id = Column(String, nullable=False, index=True) # strict enforcement
    importance = Column(Float, default=1.0)
    confidence = Column(Float, default=1.0)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)



class MemoryChunk(Base):
    """
    Cross-session long-term memory chunk (roadmap M6).

    Scoped to the workspace and the principal, not to the login session, so a
    fact recorded in one session is recalled in the next. `trusted` is False
    when the content was written while untrusted data (web, files, MCP) was
    in the run context: such chunks never reach the Project level (L2) and
    are fenced as data when recalled.

    A separate table, as was the rule before migrations (D1, ADR-031). The
    lexical index is a GIN expression index on to_tsvector('simple', content),
    only on PostgreSQL: the baseline revision creates it, and the DDL event
    below creates it for `create_all` (the offline evals, some tests).
    """

    __tablename__ = "memory_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False, index=True)
    principal_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=True)
    run_id = Column(String, nullable=True)
    kind = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    embedding = Column(Vector(384), nullable=True)
    embedder = Column(String, nullable=True)
    trusted = Column(Boolean, nullable=False, default=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


def memory_tsvector(content_column):
    """
    The lexical document expression, identical to the GIN index expression
    below so the planner can use the index.
    """
    return func.to_tsvector(
        literal_column("'simple'::regconfig"),
        content_column,
    )


event.listen(
    MemoryChunk.__table__,
    "after_create",
    DDL(
        "CREATE INDEX IF NOT EXISTS ix_memory_chunks_fts ON memory_chunks "
        "USING gin (to_tsvector('simple'::regconfig, content))"
    ).execute_if(dialect="postgresql"),
)
