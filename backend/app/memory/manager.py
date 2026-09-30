"""
@file backend/app/memory/manager.py
@description Implements manager.py. Core components: AuroraMemoryManager.

This module manages the internal business logic for AuroraMemoryManager.
It provides specialized functionality to handle: _get_embedding, save_memory, save_semantic, save_episodic, save_procedural, save_execution, fetch_all_context.
"""
import json
from datetime import datetime
from app.core.db import SessionLocal
from app.domain.models.memory import VectorMemory, MemoryType
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
except ImportError:
    _embeddings = None

class AuroraMemoryManager:
    """
    Represents the AuroraMemoryManager entity and its core operations.
    """
    """
    Phase 6: Memory Engine v1.
    Advanced retrieval supporting Execution Memory and multi-factor scoring.
    """
    
    def __init__(self, session_id: str, workspace_id: str = "default"):
        """
        Executes __init__ logic.
        """
        self.session_id = session_id
        self.workspace_id = workspace_id

    def _get_embedding(self, text: str) -> list[float]:
        """
        Executes _get_embedding logic.
        """
        if not _embeddings:
            return [0.0] * 384
        return _embeddings.embed_query(text)

    def save_memory(self, content: str, memory_type: MemoryType, importance: float = 1.0, confidence: float = 1.0, source: str = "agent"):
        """
        Executes save_memory logic.
        """
        """Stores a persistent memory with advanced metadata."""
        vector = self._get_embedding(content)
        with SessionLocal() as db:
            memory = VectorMemory(
                session_id=self.session_id,
                workspace_id=self.workspace_id,
                memory_type=memory_type.value,
                content=content,
                embedding=vector,
                importance=importance,
                confidence=confidence,
                source=source,
                created_at=datetime.utcnow()
            )
            db.add(memory)
            db.commit()

    def save_semantic(self, fact: str, importance: float = 1.0):
        """
        Executes save_semantic logic.
        """
        self.save_memory(fact, MemoryType.SEMANTIC, importance=importance, source="orchestrator")
            
    def save_episodic(self, task_description: str, outcome: str, confidence: float = 1.0):
        """
        Executes save_episodic logic.
        """
        self.save_memory(f"Task: {task_description}. Outcome: {outcome}", MemoryType.EPISODIC, confidence=confidence, source="checker")

    def save_procedural(self, rule: str, importance: float = 2.0):
        """
        Executes save_procedural logic.
        """
        self.save_memory(rule, MemoryType.PROCEDURAL, importance=importance, source="human_feedback")

    def save_execution(self, task_id: str, tools_used: list, checker_feedback: str, succeeded: bool):
        """
        Executes save_execution logic.
        """
        """Stores detailed execution traces to avoid repeating past mistakes."""
        content = f"Execution {task_id}: {'Succeeded' if succeeded else 'Failed'}. Tools: {json.dumps(tools_used)}. Feedback: {checker_feedback}"
        self.save_memory(content, MemoryType.EXECUTION, importance=1.5, confidence=0.9, source="runtime")
            
    def fetch_all_context(self, current_intent: str = "", top_k: int = 5) -> str:
        """
        Executes fetch_all_context logic.
        """
        """
        Phase 6 Retrieval:
        Scoring = (Semantic Relevance) * (Importance) * (Confidence) * (Recency Decay)
        Strictly isolates by workspace.
        """
        context = ""
        with SessionLocal() as db:
            query = db.query(VectorMemory).filter(
                VectorMemory.session_id == self.session_id,
                VectorMemory.workspace_id == self.workspace_id
            )
            
            memories = query.all()
            if not memories:
                return ""
            
            # Hybrid Scoring in memory
            query_vector = self._get_embedding(current_intent) if current_intent else None
            
            scored_memories = []
            now = datetime.utcnow()
            
            for m in memories:
                # [Phase 6] 1. Semantic Relevance via Cosine Distance
                relevance = 0.5
                if query_vector and _embeddings:
                    import numpy as np
                    v1 = np.array(query_vector)
                    v2 = np.array(m.embedding)
                    if np.linalg.norm(v1) > 0 and np.linalg.norm(v2) > 0:
                        relevance = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                
                # [Phase 6] 2. Recency Decay: ensures older observations naturally lose priority over time
                age_days = (now - m.created_at).total_seconds() / 86400.0
                recency_multiplier = max(0.1, 1.0 / (1.0 + 0.1 * age_days))
                
                # 3. Composite Score
                final_score = relevance * (m.importance or 1.0) * (m.confidence or 1.0) * recency_multiplier
                scored_memories.append((final_score, m))
                
            scored_memories.sort(key=lambda x: x[0], reverse=True)
            top_memories = [m for score, m in scored_memories[:top_k]]
            
            if top_memories:
                context += "=== RECALLED MEMORIES ===\n- " + "\n- ".join([f"[{m.memory_type.upper()}] {m.content}" for m in top_memories]) + "\n\n"
                
        return context
