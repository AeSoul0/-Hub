"""
@file backend/app/core/database.py
@description Legacy PostgreSQL persistence facade for chat, settings, academic
data, and memory-adjacent runtime records.

This module is retained for compatibility with existing application endpoints
that have not yet migrated to SQLAlchemy repositories.

Database invariants:
- SQL statements must match the actual schema created by init_db().
- Session-scoped records must remain isolated by session_id.
- Transactions must be committed only after successful statements.
- Connection-pool resources must always be returned to the pool.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Optional

from psycopg2.pool import ThreadedConnectionPool


POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db",
)

_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    """
    Return the process-wide PostgreSQL connection pool.
    """
    global _pool

    if _pool is None:
        _pool = ThreadedConnectionPool(
            1,
            20,
            POSTGRES_URL,
        )

    return _pool


@contextmanager
def get_connection() -> Generator:
    """
    Borrow one PostgreSQL connection and always return it to the pool.
    """
    pool = get_pool()
    connection = pool.getconn()

    try:
        yield connection
    finally:
        pool.putconn(connection)


def init_db() -> None:
    """
    Initialize compatibility tables and indexes used by legacy services.

    This function intentionally does not recreate tables that are already
    managed by the SQLAlchemy domain registry. It maintains only tables still
    consumed by legacy chat, settings, academic, and task services.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # The legacy memory tables use PostgreSQL vector columns.
            cursor.execute(
                "CREATE EXTENSION IF NOT EXISTS vector"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS academic (
                    session_id TEXT PRIMARY KEY,
                    gpa REAL,
                    cfu INTEGER,
                    exams INTEGER
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    session_id TEXT PRIMARY KEY,
                    temperature REAL DEFAULT 0.75,
                    max_tokens INTEGER DEFAULT 300,
                    deep_mode BOOLEAN DEFAULT FALSE
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_semantic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    fact TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_episodic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    event TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_procedural (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_task_id TEXT,
                    state TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    error_message TEXT,
                    version INTEGER DEFAULT 1,
                    attempt_number INTEGER DEFAULT 0,
                    worker_lease_id TEXT,
                    worker_lease_expires_at TIMESTAMP,
                    idempotency_key TEXT,
                    cancellation_requested BOOLEAN DEFAULT FALSE,
                    deadline TIMESTAMP,
                    max_retries INTEGER DEFAULT 3
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_attempts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL
                        REFERENCES tasks(id) ON DELETE CASCADE,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_trace TEXT
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_steps (
                    id TEXT PRIMARY KEY,
                    task_attempt_id TEXT NOT NULL
                        REFERENCES task_attempts(id) ON DELETE CASCADE,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    output_payload JSONB
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL
                        REFERENCES tasks(id) ON DELETE CASCADE,
                    state_snapshot JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL
                        REFERENCES tasks(id) ON DELETE CASCADE,
                    artifact_type TEXT NOT NULL,
                    uri_or_content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chats_session_time
                ON chats (session_id, timestamp)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_semantic_session
                ON memory_semantic (session_id)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_episodic_session
                ON memory_episodic (session_id)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_procedural_session
                ON memory_procedural (session_id)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_session_state
                ON tasks (session_id, state)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_attempts_task
                ON task_attempts (task_id)
                """
            )

        conn.commit()


def get_settings(session_id: str) -> dict:
    """
    Retrieve session-specific runtime settings.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT temperature, max_tokens, deep_mode
                FROM settings
                WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cursor.fetchone()

    if row:
        return {
            "temperature": row[0],
            "max_tokens": row[1],
            "deep_mode": bool(row[2]),
        }

    return {
        "temperature": 0.75,
        "max_tokens": 300,
        "deep_mode": False,
    }


def update_settings(
    session_id: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    deep_mode: Optional[bool] = None,
) -> None:
    """
    Upsert runtime settings for one execution session.
    """
    if not session_id:
        raise ValueError("session_id is required")

    current = get_settings(session_id)

    temp = (
        temperature
        if temperature is not None
        else current["temperature"]
    )
    token_limit = (
        max_tokens
        if max_tokens is not None
        else current["max_tokens"]
    )
    deep = (
        bool(deep_mode)
        if deep_mode is not None
        else current["deep_mode"]
    )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO settings (
                    session_id,
                    temperature,
                    max_tokens,
                    deep_mode
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    temperature = EXCLUDED.temperature,
                    max_tokens = EXCLUDED.max_tokens,
                    deep_mode = EXCLUDED.deep_mode
                """,
                (
                    session_id,
                    temp,
                    token_limit,
                    deep,
                ),
            )

        conn.commit()


def save_chat(
    session_id: str,
    user_text: str,
    ai_text: str,
) -> None:
    """
    Persist one chat exchange using the actual chats table column names.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chats (
                    session_id,
                    user_message,
                    bot_response
                )
                VALUES (%s, %s, %s)
                """,
                (
                    session_id,
                    user_text,
                    ai_text,
                ),
            )

        conn.commit()

    # Background summarization is intentionally triggered after the
    # conversation transaction has been committed.
    from app.core.celery_app import celery_app

    celery_app.send_task(
        "memory.summarize_and_forget",
        args=[session_id],
    )


def get_recent_chat(
    session_id: str,
    limit: int = 5,
) -> list:
    """
    Retrieve recent chat history in chronological order.
    """
    if not session_id:
        raise ValueError("session_id is required")

    if limit <= 0:
        return []

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_message, bot_response
                FROM (
                    SELECT
                        user_message,
                        bot_response,
                        timestamp
                    FROM chats
                    WHERE session_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                ) AS recent
                ORDER BY timestamp ASC
                """,
                (
                    session_id,
                    limit,
                ),
            )

            rows = cursor.fetchall()

    messages = []

    for user_text, ai_text in rows:
        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": ai_text,
            }
        )

    return messages


def clear_chat(session_id: str) -> None:
    """
    Remove chat history for one execution session only.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM chats WHERE session_id = %s",
                (session_id,),
            )

        conn.commit()


def get_academic_data(session_id: str) -> Optional[dict]:
    """
    Retrieve academic metrics for one execution session.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT gpa, cfu, exams
                FROM academic
                WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cursor.fetchone()

    if not row:
        return None

    return {
        "gpa": row[0],
        "cfu": row[1],
        "exams": row[2],
    }


def save_academic_data(
    session_id: str,
    gpa: float,
    cfu: int,
    exams: int,
) -> None:
    """
    Upsert academic synchronization metrics for one session.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO academic (
                    session_id,
                    gpa,
                    cfu,
                    exams
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    gpa = EXCLUDED.gpa,
                    cfu = EXCLUDED.cfu,
                    exams = EXCLUDED.exams
                """,
                (
                    session_id,
                    gpa,
                    cfu,
                    exams,
                ),
            )

        conn.commit()


def clear_academic_data(session_id: str) -> None:
    """
    Remove academic cache exclusively for one session.
    """
    if not session_id:
        raise ValueError("session_id is required")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM academic WHERE session_id = %s",
                (session_id,),
            )

        conn.commit()


__all__ = [
    "get_pool",
    "get_connection",
    "init_db",
    "get_settings",
    "update_settings",
    "save_chat",
    "get_recent_chat",
    "clear_chat",
    "get_academic_data",
    "save_academic_data",
    "clear_academic_data",
]