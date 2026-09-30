"""
@file backend/app/memory/manager.py
@description Native workspace-scoped long-term memory manager.

This module provides durable semantic, episodic, procedural, and execution
memory using SQLAlchemy, pgvector-compatible embeddings, and a native
SentenceTransformers embedding provider.

No LangChain dependency is required by the memory subsystem.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from threading import Lock
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.db import SessionLocal
from app.domain.models.memory import MemoryType, VectorMemory


# ==============================================================================
# EMBEDDING PROVIDER
# ==============================================================================

_DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embedding_model: Optional[SentenceTransformer] = None
_embedding_lock = Lock()


def _get_embedding_model() -> SentenceTransformer:
    """
    Return the process-local embedding model singleton.

    The model is loaded lazily so importing the memory subsystem does not
    immediately allocate a large transformer model.
    """
    global _embedding_model

    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                model_name = os.getenv(
                    "AEHUB_EMBEDDING_MODEL",
                    _DEFAULT_EMBEDDING_MODEL,
                )

                _embedding_model = SentenceTransformer(
                    model_name
                )

    return _embedding_model


# ==============================================================================
# MEMORY MANAGER
# ==============================================================================


class AuroraMemoryManager:
    """
    Workspace- and session-scoped long-term memory manager.

    Every operation requires both session_id and workspace_id. There is no
    synthetic default workspace or session identity.
    """

    EMBEDDING_DIMENSION = 384

    def __init__(
        self,
        session_id: str,
        workspace_id: str,
    ) -> None:
        """
        Initialize the memory manager with an explicit security scope.
        """
        if not session_id:
            raise ValueError(
                "session_id is required."
            )

        if not workspace_id:
            raise ValueError(
                "workspace_id is required."
            )

        self.session_id = session_id
        self.workspace_id = workspace_id

    # ==========================================================================
    # EMBEDDINGS
    # ==========================================================================

    @classmethod
    def _get_embedding(
        cls,
        text: str,
    ) -> List[float]:
        """
        Generate a deterministic 384-dimensional embedding vector.

        The default model is all-MiniLM-L6-v2. The resulting vector is
        validated before persistence so database schema and runtime contracts
        remain aligned.
        """
        if not text or not text.strip():
            raise ValueError(
                "Text for embedding cannot be empty."
            )

        model = _get_embedding_model()

        vector = model.encode(
            text,
            normalize_embeddings=True,
        )

        values = np.asarray(
            vector,
            dtype=np.float32,
        ).reshape(-1)

        if len(values) != cls.EMBEDDING_DIMENSION:
            raise RuntimeError(
                "Embedding provider returned an unexpected vector dimension: "
                f"{len(values)}; expected {cls.EMBEDDING_DIMENSION}."
            )

        return values.astype(float).tolist()

    # ==========================================================================
    # WRITE OPERATIONS
    # ==========================================================================

    def save_memory(
        self,
        content: str,
        memory_type: MemoryType,
        importance: float = 1.0,
        confidence: float = 1.0,
        source: str = "agent",
    ) -> None:
        """
        Persist a memory record inside the authenticated scope.
        """
        if not content or not content.strip():
            raise ValueError(
                "Memory content cannot be empty."
            )

        if not isinstance(
            memory_type,
            MemoryType,
        ):
            raise ValueError(
                "memory_type must be a MemoryType value."
            )

        vector = self._get_embedding(
            content
        )

        with SessionLocal() as db:
            memory = VectorMemory(
                session_id=self.session_id,
                workspace_id=self.workspace_id,
                memory_type=memory_type.value,
                content=content,
                embedding=vector,
                importance=float(importance),
                confidence=float(confidence),
                source=source,
                created_at=datetime.utcnow(),
            )

            db.add(memory)
            db.commit()

    def save_semantic(
        self,
        fact: str,
        importance: float = 1.0,
    ) -> None:
        """
        Persist semantic user or project knowledge.
        """
        self.save_memory(
            fact,
            MemoryType.SEMANTIC,
            importance=importance,
            source="orchestrator",
        )

    def save_episodic(
        self,
        task_description: str,
        outcome: str,
        confidence: float = 1.0,
    ) -> None:
        """
        Persist a completed task outcome as episodic memory.
        """
        content = (
            f"Task: {task_description}. "
            f"Outcome: {outcome}"
        )

        self.save_memory(
            content,
            MemoryType.EPISODIC,
            confidence=confidence,
            source="checker",
        )

    def save_procedural(
        self,
        rule: str,
        importance: float = 2.0,
    ) -> None:
        """
        Persist a durable rule or user preference.
        """
        self.save_memory(
            rule,
            MemoryType.PROCEDURAL,
            importance=importance,
            source="human_feedback",
        )

    def save_execution(
        self,
        task_id: str,
        tools_used: list,
        checker_feedback: str,
        succeeded: bool,
    ) -> None:
        """
        Persist an execution trace useful for future runtime decisions.
        """
        content = (
            f"Execution {task_id}: "
            f"{'Succeeded' if succeeded else 'Failed'}. "
            f"Tools: {json.dumps(tools_used, ensure_ascii=False)}. "
            f"Feedback: {checker_feedback}"
        )

        self.save_memory(
            content,
            MemoryType.EXECUTION,
            importance=1.5,
            confidence=0.9,
            source="runtime",
        )

    # ==========================================================================
    # READ OPERATIONS
    # ==========================================================================

    def fetch_all_context(
        self,
        current_intent: str = "",
        top_k: int = 5,
    ) -> str:
        """
        Retrieve the highest-scoring memories within the authenticated scope.

        Scoring combines semantic relevance, importance, confidence, and
        recency. No records outside the current session/workspace pair are
        considered.
        """
        if top_k <= 0:
            return ""

        with SessionLocal() as db:
            memories = (
                db.query(VectorMemory)
                .filter(
                    VectorMemory.session_id == self.session_id,
                    VectorMemory.workspace_id == self.workspace_id,
                )
                .all()
            )

            if not memories:
                return ""

            query_vector = None

            if current_intent and current_intent.strip():
                query_vector = np.asarray(
                    self._get_embedding(
                        current_intent
                    ),
                    dtype=np.float32,
                )

            now = datetime.utcnow()
            scored_memories = []

            for memory in memories:
                relevance = 0.5

                if query_vector is not None:
                    memory_vector = np.asarray(
                        memory.embedding,
                        dtype=np.float32,
                    ).reshape(-1)

                    if (
                        len(memory_vector)
                        == self.EMBEDDING_DIMENSION
                        and np.linalg.norm(query_vector) > 0
                        and np.linalg.norm(memory_vector) > 0
                    ):
                        relevance = float(
                            np.dot(
                                query_vector,
                                memory_vector,
                            )
                            / (
                                np.linalg.norm(
                                    query_vector
                                )
                                * np.linalg.norm(
                                    memory_vector
                                )
                            )
                        )

                age_days = (
                    now - memory.created_at
                ).total_seconds() / 86400.0

                recency_multiplier = max(
                    0.1,
                    1.0
                    / (
                        1.0
                        + 0.1 * max(
                            0.0,
                            age_days,
                        )
                    ),
                )

                final_score = (
                    relevance
                    * (memory.importance or 1.0)
                    * (memory.confidence or 1.0)
                    * recency_multiplier
                )

                scored_memories.append(
                    (
                        final_score,
                        memory,
                    )
                )

            scored_memories.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            top_memories = [
                memory
                for _, memory in scored_memories[:top_k]
            ]

            if not top_memories:
                return ""

            return (
                "=== RECALLED MEMORIES ===\n- "
                + "\n- ".join(
                    (
                        f"[{memory.memory_type.upper()}] "
                        f"{memory.content}"
                    )
                    for memory in top_memories
                )
                + "\n\n"
            )


__all__ = [
    "AuroraMemoryManager",
]