"""
@file backend/app/core/database.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool

# POSTGRES_URL is injected by docker-compose or environment
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db")

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 20, POSTGRES_URL)
    return _pool

@contextmanager
def get_connection():
    """Establishes a connection to the PostgreSQL database from a thread-safe pool."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

def init_db():
    """
    Initializes the PostgreSQL database and creates the necessary schemas
    if they do not already exist. Enables thread-safe data separation.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # TABLE: Conversations / Event Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # TABLE: Academic data isolated by session_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS academic (
                    session_id TEXT PRIMARY KEY,
                    gpa REAL,
                    cfu INTEGER,
                    exams INTEGER
                )
            """)

            # TABLE: LLM Runtime configurations isolated by session_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    session_id TEXT PRIMARY KEY,
                    temperature REAL DEFAULT 0.75,
                    max_tokens INTEGER DEFAULT 300,
                    deep_mode BOOLEAN DEFAULT FALSE
                )
            """)

            # Phase 5: Contextual Retrieval Engine (pgvector)
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # TABLE: A.U.R.O.R.A. Memory Layers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_semantic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    fact TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_episodic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default-workspace',
                    event TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_procedural (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # TABLE: Durable Task Runtime (Phase 2)
            cursor.execute("""
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
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_attempts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_trace TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_steps (
                    id TEXT PRIMARY KEY,
                    task_attempt_id TEXT NOT NULL REFERENCES task_attempts(id) ON DELETE CASCADE,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    output_payload JSONB
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    state_snapshot JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    artifact_type TEXT NOT NULL,
                    uri_or_content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            
            # Create indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_session_time ON chats (session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_semantic_session ON memory_semantic (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_episodic_session ON memory_episodic (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_procedural_session ON memory_procedural (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session_state ON tasks (session_id, state)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_attempts_task ON task_attempts (task_id)")
            
        conn.commit()


# ==============================================================================
# SETTINGS MATRIX LAYER
# ==============================================================================


def get_settings(session_id: str) -> dict:
    """Retrieves session-specific configurations or fallback defaults."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT temperature, max_tokens, deep_mode FROM settings WHERE session_id = %s",
                (session_id,),
            )
            row = cursor.fetchone()

            if row:
                return {"temperature": row[0], "max_tokens": row[1], "deep_mode": bool(row[2])}
            return {"temperature": 0.75, "max_tokens": 300, "deep_mode": False}


def update_settings(
    session_id: str, temperature: float = None, max_tokens: int = None, deep_mode: bool = None
):
    """Upserts hyper-parameters specifically for the requested execution session."""
    current = get_settings(session_id)
    temp = temperature if temperature is not None else current["temperature"]
    mt = max_tokens if max_tokens is not None else current["max_tokens"]
    dm = bool(deep_mode) if deep_mode is not None else current["deep_mode"]

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO settings (session_id, temperature, max_tokens, deep_mode)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    temperature = EXCLUDED.temperature,
                    max_tokens = EXCLUDED.max_tokens,
                    deep_mode = EXCLUDED.deep_mode
                """,
                (session_id, temp, mt, dm),
            )
        conn.commit()


# ==============================================================================
# RECALL MATRIX & HISTORY MANAGEMENT
# ==============================================================================


def save_chat(session_id: str, user_text: str, ai_text: str):
    """Safely commits dialogue interactions to the session's ledger slice."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chats (session_id, user_text, ai_text)
                VALUES (%s, %s, %s)
                """,
                (session_id, user_text, ai_text),
            )
        conn.commit()
    
    # Trigger background auto-summarization (Phase 4)
    from app.core.celery_app import celery_app
    celery_app.send_task("memory.summarize_and_forget", args=[session_id])


def get_recent_chat(session_id: str, limit: int = 5) -> list:
    """Extracts short-term historical context specifically filtered by the user's session."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_text, ai_text FROM (
                    SELECT user_text, ai_text, timestamp 
                    FROM chats
                    WHERE session_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                ) sub
                ORDER BY timestamp ASC
                """,
                (session_id, limit),
            )
            rows = cursor.fetchall()

            messages = []
            for user_text, ai_text in rows:
                messages.append({"role": "user", "content": user_text})
                messages.append({"role": "assistant", "content": ai_text})
            return messages


def clear_chat(session_id: str):
    """Purges the dialogue history exclusively for the requesting session."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM chats WHERE session_id = %s", (session_id,))
        conn.commit()


# ==============================================================================
# ACADEMIC MODULE DATA LAYER ACQUISITION
# ==============================================================================


def get_academic_data(session_id: str) -> dict:
    """
    Retrieves session-specific academic metrics from the PostgreSQL persistence layer.
    Returns a dictionary of metrics if found, otherwise returns None.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT gpa, cfu, exams FROM academic WHERE session_id = %s", (session_id,))
            row = cursor.fetchone()
            if row:
                return {"gpa": row[0], "cfu": row[1], "exams": row[2]}
            return None


def save_academic_data(session_id: str, gpa: float, cfu: int, exams: int):
    """
    Upserts academic synchronization metrics into the database for the given
    session identifier, preventing multi-tenant data cross-contamination.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO academic (session_id, gpa, cfu, exams)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    gpa = EXCLUDED.gpa,
                    cfu = EXCLUDED.cfu,
                    exams = EXCLUDED.exams
                """,
                (session_id, gpa, cfu, exams),
            )
        conn.commit()


def clear_academic_data(session_id: str):
    """
    Purges the cached academic database record row exclusively for the specified session.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM academic WHERE session_id = %s", (session_id,))
        conn.commit()
