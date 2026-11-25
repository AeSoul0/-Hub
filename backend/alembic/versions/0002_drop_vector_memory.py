"""
@file backend/alembic/versions/0002_drop_vector_memory.py
@description Drop `vector_memory`, the table of the old AuroraMemoryManager.

Long-term memory lives in `memory_chunks` (app/memory/store.py, M6). Nothing
has read or written `vector_memory` since the engine moved to it; the manager
and its model are removed with this revision. Rows left in the table by an
old release are dropped with it: no code could reach them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = ("ix_vector_memory_memory_type", "ix_vector_memory_session_id", "ix_vector_memory_workspace_id")


def upgrade() -> None:
    """Drop the table and its indexes, when they are there."""
    for index in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index}")
    op.execute("DROP TABLE IF EXISTS vector_memory")


def downgrade() -> None:
    """Recreate the empty table as revision 0001 had it."""
    op.create_table(
        "vector_memory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("memory_type", sa.String(), nullable=False),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vector_memory_memory_type", "vector_memory", ["memory_type"], unique=False)
    op.create_index("ix_vector_memory_session_id", "vector_memory", ["session_id"], unique=False)
    op.create_index("ix_vector_memory_workspace_id", "vector_memory", ["workspace_id"], unique=False)
