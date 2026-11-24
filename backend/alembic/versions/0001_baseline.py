"""
@file backend/alembic/versions/0001_baseline.py
@description Baseline of the schema (D1, ADR-031): the 17 tables of ÆHub as
they were on 2026-11-24, when the schema still came from `create_all`.

Generated with `alembic revision --autogenerate` on an empty database, then
made safe for the databases that `create_all` already built:
- the `vector` extension first (pgvector, for the embedding columns);
- each table, with its indexes, only when it is missing: a database from an
  older release lacks the tables added after it (e.g. `imported_skills`,
  F5), and gets exactly those;
- the GIN index of the lexical memory search, which `autogenerate` does not
  see (it is an expression index, created by a DDL event in
  `app/domain/models/memory.py`).

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The same expression as `memory_tsvector` in app/domain/models/memory.py.
MEMORY_FTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_memory_chunks_fts ON memory_chunks "
    "USING gin (to_tsvector('simple'::regconfig, content))"
)


def upgrade() -> None:
    """Create what is missing: everything on an empty database."""
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"

    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    existing = set(sa.inspect(bind).get_table_names())

    if "agent_runs" not in existing:
        op.create_table('agent_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('input_data', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_runs_session_id'), 'agent_runs', ['session_id'], unique=False)
        op.create_index(op.f('ix_agent_runs_status'), 'agent_runs', ['status'], unique=False)

    if "app_settings" not in existing:
        op.create_table('app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
        )

    if "approvals" not in existing:
        op.create_table('approvals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('tool', sa.String(), nullable=False),
        sa.Column('arguments_hash', sa.String(), nullable=False),
        sa.Column('risk', sa.String(), nullable=False),
        sa.Column('requested_by', sa.String(), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('decision', sa.String(), nullable=True),
        sa.Column('decided_by', sa.String(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )

    if "audit_chain" not in existing:
        op.create_table('audit_chain',
        sa.Column('seq', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('audit_id', sa.String(), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('record_hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('seq')
        )
        op.create_index(op.f('ix_audit_chain_audit_id'), 'audit_chain', ['audit_id'], unique=True)

    if "audit_logs" not in existing:
        op.create_table('audit_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=True),
        sa.Column('tool_call_id', sa.String(), nullable=True),
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('risk', sa.String(), nullable=False),
        sa.Column('arguments_hash', sa.String(), nullable=True),
        sa.Column('decision', sa.String(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('execution_result', sa.Text(), nullable=True),
        sa.Column('duration', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_audit_logs_session_id'), 'audit_logs', ['session_id'], unique=False)

    if "budgets" not in existing:
        op.create_table('budgets',
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('max_budget', sa.Float(), nullable=False),
        sa.Column('consumed_budget', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('principal_id')
        )

    if "document_files" not in existing:
        op.create_table('document_files',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('mtime', sa.Float(), nullable=False),
        sa.Column('chunks', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'path', name='uq_document_files_path')
        )
        op.create_index(op.f('ix_document_files_workspace_id'), 'document_files', ['workspace_id'], unique=False)

    if "idempotency_keys" not in existing:
        op.create_table('idempotency_keys',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
        )
        op.create_index(op.f('ix_idempotency_keys_expires_at'), 'idempotency_keys', ['expires_at'], unique=False)

    if "imported_skills" not in existing:
        op.create_table('imported_skills',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=2048), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('warnings', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('imported_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )

    if "memory_chunks" not in existing:
        op.create_table('memory_chunks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('run_id', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column('embedder', sa.String(), nullable=True),
        sa.Column('trusted', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_memory_chunks_content_hash'), 'memory_chunks', ['content_hash'], unique=False)
        op.create_index(op.f('ix_memory_chunks_created_at'), 'memory_chunks', ['created_at'], unique=False)
        op.create_index(op.f('ix_memory_chunks_kind'), 'memory_chunks', ['kind'], unique=False)
        op.create_index(op.f('ix_memory_chunks_principal_id'), 'memory_chunks', ['principal_id'], unique=False)
        op.create_index(op.f('ix_memory_chunks_workspace_id'), 'memory_chunks', ['workspace_id'], unique=False)

    if "monthly_spend" not in existing:
        op.create_table('monthly_spend',
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('spent', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('principal_id', 'period')
        )

    if "users" not in existing:
        op.create_table('users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
        )

    if "vector_memory" not in existing:
        op.create_table('vector_memory',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('memory_type', sa.String(), nullable=False),
        sa.Column('classification', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('importance', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_vector_memory_memory_type'), 'vector_memory', ['memory_type'], unique=False)
        op.create_index(op.f('ix_vector_memory_session_id'), 'vector_memory', ['session_id'], unique=False)
        op.create_index(op.f('ix_vector_memory_workspace_id'), 'vector_memory', ['workspace_id'], unique=False)

    if "workspaces" not in existing:
        op.create_table('workspaces',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )

    if "refresh_tokens" not in existing:
        op.create_table('refresh_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('hashed_token', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hashed_token')
        )

    if "sessions" not in existing:
        op.create_table('sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('role', sa.Enum('SYSTEM', 'ADMIN', 'MEMBER', 'USER', 'GUEST', name='roleenum'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    if "workspace_memberships" not in existing:
        op.create_table('workspace_memberships',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('role', sa.Enum('SYSTEM', 'ADMIN', 'MEMBER', 'USER', 'GUEST', name='roleenum'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    if postgres:
        op.execute(MEMORY_FTS_INDEX)


def downgrade() -> None:
    """Drop every table: only for tests and a deliberate reset."""
    op.drop_table('workspace_memberships')
    op.drop_table('sessions')
    op.drop_table('refresh_tokens')
    op.drop_table('workspaces')
    op.drop_index(op.f('ix_vector_memory_workspace_id'), table_name='vector_memory')
    op.drop_index(op.f('ix_vector_memory_session_id'), table_name='vector_memory')
    op.drop_index(op.f('ix_vector_memory_memory_type'), table_name='vector_memory')
    op.drop_table('vector_memory')
    op.drop_table('users')
    op.drop_table('monthly_spend')
    op.drop_index(op.f('ix_memory_chunks_workspace_id'), table_name='memory_chunks')
    op.drop_index(op.f('ix_memory_chunks_principal_id'), table_name='memory_chunks')
    op.drop_index(op.f('ix_memory_chunks_kind'), table_name='memory_chunks')
    op.drop_index(op.f('ix_memory_chunks_created_at'), table_name='memory_chunks')
    op.drop_index(op.f('ix_memory_chunks_content_hash'), table_name='memory_chunks')
    op.drop_table('memory_chunks')
    op.drop_table('imported_skills')
    op.drop_index(op.f('ix_idempotency_keys_expires_at'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_index(op.f('ix_document_files_workspace_id'), table_name='document_files')
    op.drop_table('document_files')
    op.drop_table('budgets')
    op.drop_index(op.f('ix_audit_logs_session_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_audit_chain_audit_id'), table_name='audit_chain')
    op.drop_table('audit_chain')
    op.drop_table('approvals')
    op.drop_table('app_settings')
    op.drop_index(op.f('ix_agent_runs_status'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_session_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
    sa.Enum(name="roleenum").drop(op.get_bind(), checkfirst=True)
