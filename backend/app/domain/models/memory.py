"""
@file backend/app/domain/models/memory.py
@description Memory model: the long-term memory chunks of the agent (M6).
"""
import threading
import uuid
from datetime import datetime, timedelta
from sqlalchemy import DDL, Boolean, Column, String, DateTime, Text, event, func, literal_column
from pgvector.sqlalchemy import Vector
from app.domain.models.identity import Base

_last_stamp = datetime.min
_stamp_lock = threading.Lock()


def created_now() -> datetime:
    """
    The time of a new chunk, strictly later than the previous one of this
    process (N9). On Windows the clock of Python 3.12 moves in steps of about
    15 ms: the episodes of a fast conversation got the same time and came
    back in any order.
    """
    global _last_stamp
    with _stamp_lock:
        now = datetime.utcnow()
        _last_stamp = now if now > _last_stamp else _last_stamp + timedelta(microseconds=1)
        return _last_stamp


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
    created_at = Column(DateTime, default=created_now, index=True)


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
