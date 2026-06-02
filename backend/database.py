import sqlite3

# CONSTANT: Name of the local database file. SQLite will automatically create it.
DB_FILE = "hub.db"


def init_db():
    """
    Initializes the SQLite database and creates the necessary schemas
    if they do not already exist. Enables thread-safe data separation.
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # TABLE: Chat history isolated by session_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
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
                deep_mode INTEGER DEFAULT 0
            )
        """)
        conn.commit()


# ==============================================================================
# SETTINGS MATRIX LAYER
# ==============================================================================


def get_settings(session_id: str) -> dict:
    """Retrieves session-specific configurations or fallback defaults."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT temperature, max_tokens, deep_mode FROM settings WHERE session_id = ?",
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
    dm = int(deep_mode) if deep_mode is not None else int(current["deep_mode"])

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (session_id, temperature, max_tokens, deep_mode)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                temperature=excluded.temperature,
                max_tokens=excluded.max_tokens,
                deep_mode=excluded.deep_mode
        """,
            (session_id, temp, mt, dm),
        )
        conn.commit()


# ==============================================================================
# RECALL MATRIX & HISTORY MANAGEMENT
# ==============================================================================


def save_chat(session_id: str, user_text: str, ai_text: str):
    """Safely commits dialogue interactions to the session's ledger slice."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chats (session_id, user_text, ai_text)
            VALUES (?, ?, ?)
        """,
            (session_id, user_text, ai_text),
        )
        conn.commit()


def get_recent_chat(session_id: str, limit: int = 5) -> list:
    """Extracts short-term historical context specifically filtered by the user's session."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_text, ai_text FROM chats
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """,
            (session_id,),
        )
        rows = cursor.fetchall()

        recent = rows[-limit:] if rows else []
        messages = []
        for user_text, ai_text in recent:
            messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": ai_text})
        return messages


def clear_chat(session_id: str):
    """Purges the dialogue history exclusively for the requesting session."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chats WHERE session_id = ?", (session_id,))
        conn.commit()


# ==============================================================================
# ACADEMIC MODULE DATA LAYER ACQUISITION
# ==============================================================================


def get_academic_data(session_id: str) -> dict:
    """
    Retrieves session-specific academic metrics from the SQLite persistence layer.
    Returns a dictionary of metrics if found, otherwise returns None.
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT gpa, cfu, exams FROM academic WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return {"gpa": row[0], "cfu": row[1], "exams": row[2]}
        return None


def save_academic_data(session_id: str, gpa: float, cfu: int, exams: int):
    """
    Upserts academic synchronization metrics into the database for the given
    session identifier, preventing multi-tenant data cross-contamination.
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO academic (session_id, gpa, cfu, exams)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                gpa=excluded.gpa,
                cfu=excluded.cfu,
                exams=excluded.exams
        """,
            (session_id, gpa, cfu, exams),
        )
        conn.commit()


def clear_academic_data(session_id: str):
    """
    Purges the cached academic database record row exclusively for the specified session.
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM academic WHERE session_id = ?", (session_id,))
        conn.commit()
