"""
@file backend/app/memory/store.py
@description Cross-session long-term memory with hybrid retrieval (roadmap M6).

Spec 4.3: chunking, automatic embedding of significant events, and hybrid
retrieval (lexical + vector) at prompt-building time, inside the token budget
of the Context Manager.

- Scope: workspace + principal. Memory follows the user across login
  sessions; the session id is kept only as provenance.
- Lexical ranking: PostgreSQL full-text search (tsvector, GIN index) on
  PostgreSQL, Okapi BM25 in Python on other databases (tests, SQLite).
- Vector ranking: pgvector cosine distance on PostgreSQL, Python cosine
  elsewhere. Only vectors from the current embedder are compared.
- Fusion: Reciprocal Rank Fusion (k=60).
- Poisoning: content written while the run context held untrusted data is
  stored with trusted=False. It is never used as a preference or rule, and
  the Context Manager fences it as data when it is recalled.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, literal_column

from app.core import db as core_db
from app.domain.models.memory import MemoryChunk, memory_tsvector
from app.memory.embeddings import Embedder, cosine_similarity, get_embedder


logger = logging.getLogger(__name__)

RRF_K = 60
DEFAULT_CANDIDATES = 20
DEFAULT_MIN_SIMILARITY = 0.25
CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP = 150
MAX_QUERY_TERMS = 32
# Rows scanned by the Python ranking path (non-PostgreSQL databases).
FALLBACK_SCAN_LIMIT = 2000

_QUERY_TERM_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)

# Function words that would match almost every chunk (English and Italian).
STOPWORDS = frozenset(
    """
    the and for are but not you all any can her was one our out has have
    had his how its who did get may him she too use that this with from
    they will would there their what when which while into than then them
    these those been being about after before over under also just only
    some such very your yours more most other each should could does doing
    please
    che non per una del della delle dei degli con sono come anche nel nella
    nelle negli alla alle agli dal dalla dai questo questa questi queste
    quello quella quelli quelle loro suo sua suoi sue mio mia miei mie tuo
    tua tuoi tue cosa essere stato stata hanno abbiamo avete fare fatto
    più piu già gia ancora molto poco tutto tutti tutte dove quando quale
    """.split()
)


class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    RULE = "rule"
    EPISODE = "episode"


# Kinds that shape behaviour: injected at the Project level (L2), and only
# when trusted.
DIRECTIVE_KINDS = (MemoryKind.PREFERENCE.value, MemoryKind.RULE.value)


@dataclass(frozen=True)
class MemoryHit:
    id: str
    kind: str
    content: str
    trusted: bool
    session_id: Optional[str]
    created_at: Optional[datetime]
    score: float = 0.0
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "trusted": self.trusted,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "score": self.score,
            "source": self.source,
        }


def memory_enabled() -> bool:
    """
    Long-term memory (indexing and recall) is on unless AEHUB_MEMORY_ENABLED
    is 0/false/off.
    """
    return os.getenv("AEHUB_MEMORY_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _min_similarity() -> float:
    try:
        return float(os.getenv("AEHUB_MEMORY_MIN_SIMILARITY", DEFAULT_MIN_SIMILARITY))
    except ValueError:
        return DEFAULT_MIN_SIMILARITY


# ==============================================================================
# PURE HELPERS
# ==============================================================================


def chunk_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into retrievable units of at most max_chars, preferring
    paragraph, then sentence, then word boundaries, with a small overlap so a
    fact cut at a boundary survives in one of the two chunks.
    """
    text = text.strip()

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        if end < len(text):
            window = text[start:end]
            cut = max(
                window.rfind("\n\n"),
                window.rfind(". "),
                window.rfind("\n"),
            )

            if cut < max_chars // 2:
                cut = window.rfind(" ")

            if cut >= max_chars // 2:
                end = start + cut + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


def query_terms(text: str) -> List[str]:
    """
    Distinct lexical query terms: alphanumeric, at least 3 characters, no
    stopwords. Safe to join into a to_tsquery expression.
    """
    terms: List[str] = []

    for token in _QUERY_TERM_PATTERN.findall(text.lower()):
        if len(token) < 3 or token in STOPWORDS or token in terms:
            continue

        terms.append(token)

        if len(terms) >= MAX_QUERY_TERMS:
            break

    return terms


def bm25_scores(
    terms: Sequence[str],
    documents: Dict[str, List[str]],
    k1: float = 1.2,
    b: float = 0.75,
) -> Dict[str, float]:
    """
    Okapi BM25 of each tokenized document for the query terms. Documents
    that match no term are left out.
    """
    if not terms or not documents:
        return {}

    count = len(documents)
    average_length = sum(len(tokens) for tokens in documents.values()) / count or 1.0
    frequencies = {doc_id: Counter(tokens) for doc_id, tokens in documents.items()}
    document_frequency = {
        term: sum(1 for counts in frequencies.values() if term in counts)
        for term in terms
    }

    scores: Dict[str, float] = {}

    for doc_id, counts in frequencies.items():
        length = len(documents[doc_id])
        score = 0.0

        for term in terms:
            tf = counts.get(term, 0)

            if not tf:
                continue

            df = document_frequency[term]
            idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / average_length))

        if score > 0:
            scores[doc_id] = score

    return scores


def rrf_fuse(
    rankings: Iterable[Sequence[str]],
    k: int = RRF_K,
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank).
    Ties keep the order of first appearance.
    """
    scores: Dict[str, float] = {}

    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def content_hash(kind: str, content: str) -> str:
    return hashlib.sha256(f"{kind}\n{content}".encode("utf-8")).hexdigest()


# ==============================================================================
# STORE
# ==============================================================================


class MemoryStore:
    """
    Long-term memory of one principal inside one workspace.
    """

    def __init__(
        self,
        workspace_id: str,
        principal_id: str,
        embedder: Optional[Embedder] = None,
        session_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required.")

        if not principal_id:
            raise ValueError("principal_id is required.")

        self.workspace_id = workspace_id
        self.principal_id = principal_id
        self._embedder = embedder
        self._session_factory = session_factory

    # ------------------------------------------------------------------ infra

    def _session(self) -> Any:
        factory = self._session_factory or core_db.SessionLocal
        return factory()

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder()

        return self._embedder

    def _embed(self, text: str) -> Tuple[Optional[List[float]], Optional[str]]:
        """
        Embed text, or return (None, None) when the embedder is unavailable:
        the chunk then stays reachable through lexical search.
        """
        try:
            embedder = self._get_embedder()
            return embedder.embed(text), embedder.name
        except Exception as exc:
            logger.warning("Memory embedding unavailable: %s", exc)
            return None, None

    def _scope(self, query: Any) -> Any:
        return query.filter(
            MemoryChunk.workspace_id == self.workspace_id,
            MemoryChunk.principal_id == self.principal_id,
        )

    @staticmethod
    def _hit(row: MemoryChunk, score: float = 0.0) -> MemoryHit:
        return MemoryHit(
            id=row.id,
            kind=row.kind,
            content=row.content,
            trusted=bool(row.trusted),
            session_id=row.session_id,
            created_at=row.created_at,
            score=score,
            source=row.source,
        )

    # ------------------------------------------------------------------ write

    def add(
        self,
        content: str,
        kind: MemoryKind | str,
        trusted: bool = True,
        source: str = "agent",
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> int:
        """
        Chunk, embed and store content. Chunks already stored for this scope
        and kind are skipped. Returns the number of new chunks.
        """
        kind_value = MemoryKind(kind).value
        chunks = chunk_text(content)

        if not chunks:
            return 0

        stored = 0

        with self._session() as db:
            for chunk in chunks:
                digest = content_hash(kind_value, chunk)

                exists = (
                    self._scope(db.query(MemoryChunk.id))
                    .filter(MemoryChunk.content_hash == digest)
                    .first()
                )

                if exists is not None:
                    continue

                vector, embedder_name = self._embed(chunk)

                db.add(
                    MemoryChunk(
                        workspace_id=self.workspace_id,
                        principal_id=self.principal_id,
                        session_id=session_id,
                        run_id=run_id,
                        kind=kind_value,
                        content=chunk,
                        content_hash=digest,
                        embedding=vector,
                        embedder=embedder_name,
                        trusted=bool(trusted),
                        source=source,
                        created_at=datetime.utcnow(),
                    )
                )
                stored += 1

            db.commit()

        return stored

    def delete(self, memory_id: str) -> bool:
        with self._session() as db:
            row = (
                self._scope(db.query(MemoryChunk))
                .filter(MemoryChunk.id == memory_id)
                .first()
            )

            if row is None:
                return False

            db.delete(row)
            db.commit()

            return True

    # ------------------------------------------------------------------ read

    def list(
        self,
        kinds: Optional[Sequence[str]] = None,
        trusted_only: bool = False,
        limit: int = 100,
    ) -> List[MemoryHit]:
        """
        Most recent memories of the scope, optionally filtered by kind.
        """
        with self._session() as db:
            query = self._scope(db.query(MemoryChunk))

            if kinds:
                query = query.filter(MemoryChunk.kind.in_(list(kinds)))

            if trusted_only:
                query = query.filter(MemoryChunk.trusted.is_(True))

            rows = query.order_by(MemoryChunk.created_at.desc()).limit(limit).all()

            return [self._hit(row) for row in rows]

    def preferences(self, limit: int = 50) -> List[MemoryHit]:
        """
        Trusted user preferences and rules, newest first (Project level, L2).
        """
        return self.list(kinds=DIRECTIVE_KINDS, trusted_only=True, limit=limit)

    def search(
        self,
        query: str,
        limit: int = 8,
        candidates: int = DEFAULT_CANDIDATES,
        exclude_kinds: Sequence[str] = (),
    ) -> List[MemoryHit]:
        """
        Hybrid retrieval: lexical and vector rankings fused with RRF.
        """
        if not query or not query.strip() or limit <= 0:
            return []

        terms = query_terms(query)
        vector, embedder_name = self._embed(query)

        with self._session() as db:
            base = self._scope(db.query(MemoryChunk))

            if exclude_kinds:
                base = base.filter(MemoryChunk.kind.notin_(list(exclude_kinds)))

            if db.get_bind().dialect.name == "postgresql":
                lexical, semantic = self._rank_postgres(
                    base, terms, vector, embedder_name, candidates
                )
            else:
                lexical, semantic = self._rank_python(
                    base, terms, vector, embedder_name, candidates
                )

            fused = rrf_fuse([lexical, semantic])[:limit]

            if not fused:
                return []

            rows = {
                row.id: row
                for row in db.query(MemoryChunk)
                .filter(MemoryChunk.id.in_([doc_id for doc_id, _ in fused]))
                .all()
            }

            return [
                self._hit(rows[doc_id], score)
                for doc_id, score in fused
                if doc_id in rows
            ]

    @staticmethod
    def _rank_postgres(
        base: Any,
        terms: List[str],
        vector: Optional[List[float]],
        embedder_name: Optional[str],
        candidates: int,
    ) -> Tuple[List[str], List[str]]:
        lexical: List[str] = []
        semantic: List[str] = []

        if terms:
            document = memory_tsvector(MemoryChunk.content)
            ts_query = func.to_tsquery(
                literal_column("'simple'::regconfig"),
                " | ".join(terms),
            )
            lexical = [
                row.id
                for row in base.with_entities(MemoryChunk.id)
                .filter(document.op("@@")(ts_query))
                .order_by(
                    func.ts_rank_cd(document, ts_query).desc(),
                    MemoryChunk.created_at.desc(),
                )
                .limit(candidates)
                .all()
            ]

        if vector is not None:
            distance = MemoryChunk.embedding.cosine_distance(vector)
            semantic = [
                row.id
                for row in base.with_entities(MemoryChunk.id)
                .filter(
                    MemoryChunk.embedder == embedder_name,
                    MemoryChunk.embedding.isnot(None),
                    distance <= 1.0 - _min_similarity(),
                )
                .order_by(distance)
                .limit(candidates)
                .all()
            ]

        return lexical, semantic

    @staticmethod
    def _rank_python(
        base: Any,
        terms: List[str],
        vector: Optional[List[float]],
        embedder_name: Optional[str],
        candidates: int,
    ) -> Tuple[List[str], List[str]]:
        rows = (
            base.order_by(MemoryChunk.created_at.desc())
            .limit(FALLBACK_SCAN_LIMIT)
            .all()
        )

        lexical_scores = bm25_scores(
            terms,
            {row.id: _QUERY_TERM_PATTERN.findall(row.content.lower()) for row in rows},
        )
        lexical = sorted(lexical_scores, key=lexical_scores.get, reverse=True)[:candidates]

        semantic: List[str] = []

        if vector is not None:
            minimum = _min_similarity()
            similarities: Dict[str, float] = {}

            for row in rows:
                if row.embedder != embedder_name or row.embedding is None:
                    continue

                similarity = cosine_similarity(
                    vector,
                    [float(component) for component in row.embedding],
                )

                if similarity >= minimum:
                    similarities[row.id] = similarity

            semantic = sorted(similarities, key=similarities.get, reverse=True)[:candidates]

        return lexical, semantic


__all__ = [
    "DIRECTIVE_KINDS",
    "MemoryHit",
    "MemoryKind",
    "MemoryStore",
    "bm25_scores",
    "chunk_text",
    "content_hash",
    "memory_enabled",
    "query_terms",
    "rrf_fuse",
]
