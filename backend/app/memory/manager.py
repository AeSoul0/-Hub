"""
@file backend/app/memory/manager.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from app.core.db import SessionLocal
from app.domain.models.memory import VectorMemory, MemoryType
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    # Load lightweight local embeddings model (all-MiniLM-L6-v2 is 384 dims)
    _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
except ImportError:
    _embeddings = None

class AuroraMemoryManager:
    """
    Manages A.U.R.O.R.A.'s Memory Architecture (M4).
    Uses pgvector for Long-Term Semantic retrieval.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id

    def _get_embedding(self, text: str) -> list[float]:
        if not _embeddings:
            return [0.0] * 384 # Fallback dummy if not installed
        return _embeddings.embed_query(text)

    def save_memory(self, content: str, memory_type: MemoryType):
        """Stores a persistent memory with vector embedding."""
        vector = self._get_embedding(content)
        with SessionLocal() as db:
            memory = VectorMemory(
                session_id=self.session_id,
                memory_type=memory_type.value,
                content=content,
                embedding=vector
            )
            db.add(memory)
            db.commit()

    def save_semantic(self, fact: str):
        self.save_memory(fact, MemoryType.SEMANTIC)
            
    def save_episodic(self, task_description: str, outcome: str):
        self.save_memory(f"Task: {task_description}. Outcome: {outcome}", MemoryType.EPISODIC)

    def save_procedural(self, rule: str):
        self.save_memory(rule, MemoryType.PROCEDURAL)
            
    def fetch_all_context(self, current_intent: str = "") -> str:
        """Retrieves semantically relevant memories based on current intent using pgvector."""
        context = ""
        
        with SessionLocal() as db:
            if current_intent and _embeddings:
                query_vector = self._get_embedding(current_intent)
                # Semantic search: get top 5 most relevant memories using cosine distance (<= operator in pgvector)
                relevant_memories = db.query(VectorMemory).filter(
                    VectorMemory.session_id == self.session_id
                ).order_by(VectorMemory.embedding.cosine_distance(query_vector)).limit(5).all()
                
                if relevant_memories:
                    context += "=== RECALLED MEMORIES ===\n- " + "\n- ".join([m.content for m in relevant_memories]) + "\n\n"
            else:
                # Fallback to recent procedural rules and semantic facts
                recent = db.query(VectorMemory).filter(
                    VectorMemory.session_id == self.session_id
                ).order_by(VectorMemory.created_at.desc()).limit(10).all()
                
                if recent:
                    context += "=== RECENT MEMORIES ===\n- " + "\n- ".join([m.content for m in recent]) + "\n\n"
                    
        return context
