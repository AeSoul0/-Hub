"""
@file backend/app/memory/embeddings.py
@description Embedding providers for the long-term memory store (roadmap M6).

AEHUB_EMBEDDER selects the provider (Control Plane, then environment; a
change applies to the next embedding, F6):
- "sentence-transformers" (default): all-MiniLM-L6-v2, or AEHUB_EMBEDDING_MODEL,
  run with ONNX Runtime (O1): an ONNX export (onnx/model.onnx) and its
  tokenizer, mean pooling and L2 normalization as sentence-transformers
  does, without torch (about 750 MB of RAM less). The name stays
  "st:<model>": same model, same vectors, so the vectors already stored keep
  matching. Downloads are pinned: the default model comes from one commit of
  Xenova/all-MiniLM-L6-v2 and each file is checked against its SHA-256;
  another model is named with its commit, "owner/name@<commit>";
- "hash": deterministic feature hashing. No model download, weaker recall;
  meant for tests and minimal installs.

Every chunk stores the name of the embedder that produced its vector, and
vector search only compares vectors from the same embedder. The model
leaves memory after AEHUB_VOICE_IDLE_MINUTES without use, like the voice
models, and loads again with the next embedding.
"""

from __future__ import annotations

import gc
import hashlib
import math
import re
import time
from threading import Lock
from typing import Any, Dict, List, Optional, Protocol

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


# sentence-transformers' own setting for all-MiniLM-L6-v2: longer texts are cut.
MAX_TOKENS = 256
ONNX_FILE = "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"

# The default model, pinned (O1): the fp32 ONNX export of
# sentence-transformers/all-MiniLM-L6-v2 at one commit, each file checked.
# The CI checks this commit and these hashes against the hub.
PINNED_MODELS: Dict[str, Dict[str, Any]] = {
    "all-MiniLM-L6-v2": {
        "repository": "Xenova/all-MiniLM-L6-v2",
        "revision": "751bff37182d3f1213fa05d7196b954e230abad9",
        "files": {
            ONNX_FILE: "759c3cd2b7fe7e93933ad23c4c9181b7396442a2ed746ec7c1d46192c469c46e",
            TOKENIZER_FILE: "da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0",
        },
    },
}

_COMMIT = re.compile(r"[0-9a-f]{7,40}")
# Files already checked in this process: a reload after release skips the hash.
_verified: set = set()


def model_source(model_name: str) -> Dict[str, Any]:
    """
    Where a model comes from: repository, commit and, for the pinned default,
    the SHA-256 of each file. Another model must name its commit,
    "owner/name@<commit>": a download is never "whatever main is today".
    """
    if model_name in PINNED_MODELS:
        return PINNED_MODELS[model_name]

    repository, _, revision = model_name.partition("@")
    if not _COMMIT.fullmatch(revision):
        raise RuntimeError(
            f"Embedding model {model_name}: name it with its commit, as owner/name@<commit>, "
            "so the download is pinned; or use all-MiniLM-L6-v2, or AEHUB_EMBEDDER=hash."
        )
    if "/" not in repository:
        repository = f"sentence-transformers/{repository}"
    return {"repository": repository, "revision": revision, "files": {}}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(source: Dict[str, Any], filename: str) -> str:
    """One file of the model at its commit, checked against its SHA-256 when known."""
    from huggingface_hub import hf_hub_download

    repository, revision = source["repository"], source["revision"]
    path = hf_hub_download(repository, filename, revision=revision)
    expected = source["files"].get(filename)
    if expected and path not in _verified:
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"Embedding model {repository}@{revision}: {filename} has SHA-256 {actual}, "
                f"expected {expected}. The file was not used."
            )
        _verified.add(path)
    return path


class SentenceTransformerEmbedder:
    """
    Local transformer embedder on ONNX Runtime. The model is downloaded once
    from the Hugging Face hub (its ONNX export and tokenizer) and loaded
    lazily, on first use.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.name = f"st:{model_name}"
        self._model: Optional[Any] = None
        self._lock = Lock()
        self.last_used = time.monotonic()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._open()

        return self._model

    def _open(self) -> Any:
        import onnxruntime
        from tokenizers import Tokenizer

        source = model_source(self.model_name)
        try:
            model_path = _download(source, ONNX_FILE)
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - said in words: a model without an ONNX export, or no network
            raise RuntimeError(
                f"Embedding model {source['repository']}@{source['revision']}: {ONNX_FILE} not available ({exc}). "
                "Choose a model that publishes an ONNX export, or AEHUB_EMBEDDER=hash."
            ) from exc

        tokenizer = Tokenizer.from_file(_download(source, TOKENIZER_FILE))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.no_padding()

        options = onnxruntime.SessionOptions()
        # One sentence at a time on a desktop: a thread or two is plenty.
        options.intra_op_num_threads = 2
        session = onnxruntime.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])
        return tokenizer, session, {item.name for item in session.get_inputs()}

    def embed(self, text: str) -> List[float]:
        import numpy

        tokenizer, session, inputs = self._load()
        self.last_used = time.monotonic()
        encoding = tokenizer.encode(text)
        feed: Dict[str, Any] = {
            "input_ids": numpy.array([encoding.ids], dtype=numpy.int64),
            "attention_mask": numpy.array([encoding.attention_mask], dtype=numpy.int64),
            "token_type_ids": numpy.array([encoding.type_ids], dtype=numpy.int64),
        }
        hidden = session.run(None, {name: value for name, value in feed.items() if name in inputs})[0]

        # Mean of the token vectors (padding excluded), then unit length.
        mask = feed["attention_mask"][..., None].astype(hidden.dtype)
        pooled = (hidden * mask).sum(axis=1) / numpy.clip(mask.sum(axis=1), 1e-9, None)
        vector = pooled[0] / max(float(numpy.linalg.norm(pooled[0])), 1e-12)
        values = [float(component) for component in vector]

        if len(values) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Embedding model {self.model_name} returned {len(values)} "
                f"dimensions; the memory store expects {EMBEDDING_DIMENSION}."
            )

        return values

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def release(self) -> None:
        """Let the model go; the next embedding loads it again."""
        with self._lock:
            self._model = None


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


def release_idle_embedder(now: Optional[float] = None) -> bool:
    """
    Let the embedding model go after AEHUB_VOICE_IDLE_MINUTES without use
    (O1: one setting for every local model). True when it was released.
    """
    from app.voice.engines import idle_seconds_limit

    limit = idle_seconds_limit()
    now = time.monotonic() if now is None else now

    with _embedder_lock:
        embedder = _embedder

    if limit <= 0 or not isinstance(embedder, SentenceTransformerEmbedder) or not embedder.loaded:
        return False
    if now - embedder.last_used < limit:
        return False

    embedder.release()
    gc.collect()
    return True


def loaded_embedder(now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The embedding model in memory, and how long it has been unused; None when none is."""
    with _embedder_lock:
        embedder = _embedder
    if not isinstance(embedder, SentenceTransformerEmbedder) or not embedder.loaded:
        return None
    now = time.monotonic() if now is None else now
    return {"kind": "embedder", "config": [embedder.model_name], "idle_seconds": round(now - embedder.last_used, 1)}


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
    "PINNED_MODELS",
    "get_embedder",
    "loaded_embedder",
    "model_source",
    "release_idle_embedder",
    "tokenize",
]
