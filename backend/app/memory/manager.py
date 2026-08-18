"""
@file backend/app/memory/manager.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import List, Dict, Any
from app.core.database import get_connection

class AuroraMemoryManager:
    """
    Manages A.U.R.O.R.A.'s Memory Architecture.
    - Working Memory: Handled natively by LangGraph state (messages array).
    - Conversation Memory: Handled by AsyncPostgresSaver Checkpoints.
    - Episodic Memory: Events and task outcomes.
    - Semantic Memory: Facts and knowledge about the user.
    - Procedural Memory: Preferences and rules.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        
    def save_semantic(self, fact: str):
        """Stores a persistent fact about the user or environment."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memory_semantic (session_id, fact) VALUES (%s, %s)",
                    (self.session_id, fact)
                )
            conn.commit()
            
    def save_episodic(self, task_description: str, outcome: str):
        """Stores the result of a completed task or significant event."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memory_episodic (session_id, task_description, outcome) VALUES (%s, %s, %s)",
                    (self.session_id, task_description, outcome)
                )
            conn.commit()

    def save_procedural(self, rule: str):
        """Stores a preference or operational rule the agent must follow."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memory_procedural (session_id, rule) VALUES (%s, %s)",
                    (self.session_id, rule)
                )
            conn.commit()
            
    def fetch_all_context(self) -> str:
        """Retrieves all context memory for injection into the prompt."""
        semantic = []
        procedural = []
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT fact FROM memory_semantic WHERE session_id = %s ORDER BY created_at DESC LIMIT 20", (self.session_id,))
                semantic = [row[0] for row in cursor.fetchall()]
                
                cursor.execute("SELECT rule FROM memory_procedural WHERE session_id = %s ORDER BY created_at DESC LIMIT 10", (self.session_id,))
                procedural = [row[0] for row in cursor.fetchall()]

        context = ""
        if semantic:
            context += "=== SEMANTIC MEMORY (Known Facts) ===\n- " + "\n- ".join(semantic) + "\n\n"
        if procedural:
            context += "=== PROCEDURAL MEMORY (Rules & Preferences) ===\n- " + "\n- ".join(procedural) + "\n\n"
            
        return context
