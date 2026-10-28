"""
@file backend/app/memory/embeddings.py
@description Embedding providers for the long-term memory store (roadmap M6).

AEHUB_EMBEDDER selects the provider (Control Plane, then environment; a
change applies to the next embedding, F6):
- "sentence-transformers" (default): all-MiniLM-L6-v2, or AEHUB_EMBEDDING_MODEL;
- "hash": deterministic feature hashing. No model download, weaker recall;
  meant for tests and minimal installs.

Every chunk stores the name of the embedder that produced its vector, and
vector search only compares vectors from the same embedder.
"""

from __future__ import annotations

import hashlib
import math
import re
from threading import Lock
from typing import Any, List, Optional, Protocol

from app.core.runtime_config import config_value


EMBEDDING_DIMENSION = 384

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> List[float]: ...


def tokenize(text: str) -> List[str]:
    """
    Lower-cased word tokens, shared by the hash embedder and lexical ranking.
    """
    return _TOKEN_PATTERN.findall(text.lower())


class HashingEmbedder:
    """
    Feature-hashing embedder: each token (and token bigram) adds a signed
    unit to one of EMBEDDING_DIMENSION buckets; the vector is L2-normalized.
    """

    name = "hash-v1"

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        tokens = tokenize(text)
        features = tokens + [
            f"{left} {right}" for left, right in zip(tokens, tokens[1:])
        ]

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            sign = 1.0 if value & 1 else -1.0
            vector[(value >> 1) % EMBEDDING_DIMENSION] += sign

        norm = math.sqrt(sum(component * component for component in vector))

        if norm == 0:
            return vector

        return [component / norm for component in vector]


class SentenceTransformerEmbedder:
    """
    Local transformer embedder. The model is loaded lazily, on first use.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.name = f"st:{model_name}"
        self._model: Optional[Any] = None
        self._lock = Lock()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name)

        return self._model

    def embed(self, text: str) -> List[float]:
        vector = self._load().encode(text, normalize_embeddings=True)
        values = [float(component) for component in vector]

        if len(values) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Embedding model {self.model_name} returned {len(values)} "
                f"dimensions; the memory store expects {EMBEDDING_DIMENSION}."
            )

        return values


_embedder: Optional[Embedder] = None
_embedder_key: Optional[str] = None
_embedder_lock = Lock()


def get_embedder() -> Embedder:
    """
    Return the process-wide embedder selected by AEHUB_EMBEDDER.
    """
    global _embedder, _embedder_key

    kind = (config_value("AEHUB_EMBEDDER", "sentence-transformers") or "sentence-transformers").strip().lower()
    model_name = config_value("AEHUB_EMBEDDING_MODEL", "all-MiniLM-L6-v2") or "all-MiniLM-L6-v2"
    key = f"{kind}:{model_name}"

    with _embedder_lock:
        if _embedder is None or _embedder_key != key:
            if kind == "hash":
                _embedder = HashingEmbedder()
            elif kind == "sentence-transformers":
                _embedder = SentenceTransformerEmbedder(model_name)
            else:
                raise ValueError(
                    f"Unknown AEHUB_EMBEDDER '{kind}': use "
                    "'sentence-transformers' or 'hash'."
                )
            _embedder_key = key

        return _embedder


def cosine_similarity(left: List[float], right: List[float]) -> float:
    if len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))

    return dot / norm if norm else 0.0


__all__ = [
    "EMBEDDING_DIMENSION",
    "Embedder",
    "HashingEmbedder",
    "SentenceTransformerEmbedder",
    "cosine_similarity",
    "get_embedder",
    "tokenize",
]
