"""
@file backend/app/domain/models/documents.py
@description Files of the working folder indexed for document search (roadmap M13).

The chunks themselves live in memory_chunks (kind "document", untrusted), so
they share the hybrid retrieval of the long-term memory. This table records
what was indexed from each file, so a sync only re-reads files whose size,
modification time or content changed, and drops the chunks of deleted files.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from app.domain.models.identity import Base


class DocumentFile(Base):
    """
    One file of the working folder as last indexed for one workspace.

    `error` is set when the file could not be read (unsupported PDF, too
    large): the file then has no chunks until it changes.
    """

    __tablename__ = "document_files"
    __table_args__ = (UniqueConstraint("workspace_id", "path", name="uq_document_files_path"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False, index=True)
    # POSIX path relative to the working folder; also the citation name.
    path = Column(String(1024), nullable=False)
    sha256 = Column(String(64), nullable=False)
    size = Column(Integer, nullable=False)
    mtime = Column(Float, nullable=False)
    chunks = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    indexed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
