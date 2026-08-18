import os
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

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
            # TABLE: Chat history isolated by session_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_text TEXT NOT NULL,
                    ai_text TEXT NOT NULL
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

            # TABLE: A.U.R.O.R.A. Memory Layers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_semantic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_episodic (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    outcome TEXT NOT NULL,
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
            
            # Create indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_session_time ON chats (session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_semantic_session ON memory_semantic (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_episodic_session ON memory_episodic (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_procedural_session ON memory_procedural (session_id)")
            
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
