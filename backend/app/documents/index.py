"""
@file backend/app/documents/index.py
@description Index and search the user's documents in the working folder (roadmap M13).

- Sources: text, Markdown and PDF files under the working folder (the first
  root of AEHUB_ALLOWED_DIRS, ./workspace by default). Hidden files and
  folders are skipped, and so is any symlink that leads outside the folder.
- Storage: chunks go to memory_chunks with kind "document", trusted=False and
  a dedicated principal, so they share the hybrid retrieval of the long-term
  memory but are never recalled automatically and never become preferences.
  A file is third-party content: whatever it says is data, not instructions.
- Incremental: document_files keeps size, mtime and SHA-256 of each file. A
  sync re-reads only changed files and drops the chunks of deleted ones.
- Citations: every chunk has a location, lines for text ("L12-30") and the
  page for PDF ("p3"). Answers cite it as [doc: path#location], and
  missing_citations() checks that a cited location exists in the index.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agent_engine.guardrails import allowed_directories
from app.core import db as core_db
from app.core.runtime_config import config_value
from app.domain.models.documents import DocumentFile
from app.domain.models.memory import MemoryChunk
from app.memory.embeddings import Embedder
from app.memory.store import CHUNK_MAX_CHARS, CHUNK_OVERLAP, MemoryStore, chunk_text, content_hash


logger = logging.getLogger(__name__)

DOCUMENT_KIND = "document"
# memory_chunks.principal_id of document chunks: documents belong to the
# working folder, not to one user, and stay out of every user's recall.
DOCUMENTS_PRINCIPAL = "_documents"
SOURCE_PREFIX = "document:"

SUPPORTED_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".pdf"})
SKIPPED_DIRS = frozenset({"node_modules", "__pycache__", "venv"})
MAX_FILES = 2000
MAX_CHUNKS_PER_FILE = 400
DEFAULT_MAX_FILE_MB = 5.0
SEARCH_LIMIT = 5

# Strict form of a citation, and a loose one that also catches malformed
# citations (a missing or invalid location) so they count as wrong.
_CITATION = re.compile(r"\[doc:\s*(?P<path>[^\]#\n]+?)\s*#\s*(?P<locator>L\d+-\d+|p\d+)\s*\]")
_ANY_CITATION = re.compile(r"\[doc:[^\]\n]*\]")

# One sync at a time per process: a search and a reindex from the API would
# otherwise insert the same chunks twice.
_SYNC_LOCK = threading.Lock()


def max_file_bytes() -> int:
    return _max_file_bytes()


def _max_file_bytes() -> int:
    try:
        megabytes = float(config_value("AEHUB_DOCUMENTS_MAX_FILE_MB", str(DEFAULT_MAX_FILE_MB)) or DEFAULT_MAX_FILE_MB)
    except ValueError:
        megabytes = DEFAULT_MAX_FILE_MB

    return int(max(megabytes, 0.0) * 1024 * 1024)


def documents_root() -> Path:
    """
    The working folder: the first root that file tools may touch.
    """
    return allowed_directories()[0]


# ==============================================================================
# PURE HELPERS
# ==============================================================================


def citation(path: str, locator: str) -> str:
    return f"[doc: {path}#{locator}]"


def _source(path: str, locator: str) -> str:
    return f"{SOURCE_PREFIX}{path}#{locator}"


def parse_source(source: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    (path, locator) of a document chunk source, (None, None) for anything else.
    """
    if not source or not source.startswith(SOURCE_PREFIX):
        return None, None

    path, separator, locator = source[len(SOURCE_PREFIX):].rpartition("#")

    if not separator:
        return None, None

    return path, locator


def chunk_lines(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> List[Tuple[int, int, str]]:
    """
    Split text into (first_line, last_line, chunk) of at most max_chars,
    cutting only between lines, with up to `overlap` characters of trailing
    lines repeated at the start of the next chunk. A single line longer than
    max_chars is split on its own, every piece keeping its line number.
    """
    chunks: List[Tuple[int, int, str]] = []
    current: List[Tuple[int, str]] = []
    size = 0

    def flush() -> None:
        lines = list(current)

        while lines and not lines[0][1].strip():
            lines.pop(0)

        while lines and not lines[-1][1].strip():
            lines.pop()

        if lines:
            chunks.append((lines[0][0], lines[-1][0], "\n".join(line for _, line in lines)))

    for number, line in enumerate(text.splitlines(), start=1):
        if len(line) > max_chars:
            flush()
            current, size = [], 0

            for piece in chunk_text(line, max_chars, overlap):
                chunks.append((number, number, piece))

            continue

        if current and size + len(line) + 1 > max_chars:
            flush()
            carried: List[Tuple[int, str]] = []
            carried_size = 0

            for item in reversed(current):
                if carried_size + len(item[1]) + 1 > overlap:
                    break

                carried.insert(0, item)
                carried_size += len(item[1]) + 1

            current, size = carried, carried_size

            if size + len(line) + 1 > max_chars:
                current, size = [], 0

        current.append((number, line))
        size += len(line) + 1

    flush()

    return chunks


def extract_chunks(path: str, data: bytes) -> List[Tuple[str, str]]:
    """
    (locator, text) chunks of one file: line ranges for text and Markdown,
    pages for PDF. NUL characters are dropped (PostgreSQL text rejects them).
    """
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))

        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("the PDF is password protected")

        pieces: List[Tuple[str, str]] = []

        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").replace("\x00", "")

            for chunk in chunk_text(text):
                pieces.append((f"p{number}", chunk))

        return pieces

    text = data.decode("utf-8-sig", errors="replace").replace("\x00", "")

    return [(f"L{first}-{last}", chunk) for first, last, chunk in chunk_lines(text)]


def find_citations(text: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """
    Every [doc: ...] tag of a text as (tag, path, locator); path and locator
    are None when the tag is malformed.
    """
    found: List[Tuple[str, Optional[str], Optional[str]]] = []

    for match in _ANY_CITATION.finditer(text or ""):
        strict = _CITATION.fullmatch(match.group(0))

        if strict is None:
            found.append((match.group(0), None, None))
        else:
            found.append((match.group(0), strict.group("path").strip(), strict.group("locator")))

    return found


def missing_citations(
    text: str,
    workspace_id: str,
    session_factory: Optional[Callable[[], Any]] = None,
) -> List[str]:
    """
    Citations of a text that point to no indexed location: malformed tags,
    unknown or deleted files, locations the file does not have.
    """
    cited = find_citations(text)

    if not cited:
        return []

    sources = {_source(path, locator) for _, path, locator in cited if path and locator}
    existing: set = set()

    if sources:
        with (session_factory or core_db.SessionLocal)() as db:
            existing = {
                row.source
                for row in db.query(MemoryChunk.source).filter(
                    MemoryChunk.workspace_id == workspace_id,
                    MemoryChunk.principal_id == DOCUMENTS_PRINCIPAL,
                    MemoryChunk.kind == DOCUMENT_KIND,
                    MemoryChunk.source.in_(sorted(sources)),
                )
            }

    return [
        tag
        for tag, path, locator in cited
        if not (path and locator and _source(path, locator) in existing)
    ]


# ==============================================================================
# INDEX
# ==============================================================================


@dataclass(frozen=True)
class DocumentHit:
    path: str
    locator: str
    content: str
    score: float = 0.0

    @property
    def citation(self) -> str:
        return citation(self.path, self.locator)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "locator": self.locator,
            "citation": self.citation,
            "content": self.content,
            "score": self.score,
        }


@dataclass
class SyncReport:
    """
    Outcome of one sync. `pending` counts changed files left for the next
    sync because the time budget ran out.
    """

    root: str = ""
    root_exists: bool = True
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    failed: List[Dict[str, str]] = field(default_factory=list)
    unchanged: int = 0
    pending: int = 0
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "root_exists": self.root_exists,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "failed": self.failed,
            "unchanged": self.unchanged,
            "pending": self.pending,
            "truncated": self.truncated,
        }


class DocumentIndex:
    """
    Document index of the working folder for one workspace.
    """

    def __init__(
        self,
        workspace_id: str,
        root: Optional[Path] = None,
        embedder: Optional[Embedder] = None,
        session_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required.")

        self.workspace_id = workspace_id
        self.root = Path(root) if root is not None else documents_root()
        self._session_factory = session_factory
        self._store = MemoryStore(
            workspace_id=workspace_id,
            principal_id=DOCUMENTS_PRINCIPAL,
            embedder=embedder,
            session_factory=session_factory,
        )

    def _session(self) -> Any:
        return (self._session_factory or core_db.SessionLocal)()

    # ------------------------------------------------------------------ sync

    def _walk(self, report: SyncReport) -> List[Tuple[str, Path]]:
        root = self.root.resolve()
        found: List[Tuple[str, Path]] = []

        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                name for name in dirnames if not name.startswith(".") and name not in SKIPPED_DIRS
            )

            for name in sorted(filenames):
                path = Path(directory) / name

                if name.startswith(".") or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue

                try:
                    resolved = path.resolve()
                except OSError:
                    continue

                # A symlink may point anywhere on the host.
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    continue

                if len(found) >= MAX_FILES:
                    report.truncated = True
                    return found

                found.append((path.relative_to(root).as_posix(), path))

        return found

    def _drop_chunks(self, db: Any, path: str) -> None:
        db.query(MemoryChunk).filter(
            MemoryChunk.workspace_id == self.workspace_id,
            MemoryChunk.principal_id == DOCUMENTS_PRINCIPAL,
            MemoryChunk.kind == DOCUMENT_KIND,
            MemoryChunk.source.startswith(f"{SOURCE_PREFIX}{path}#", autoescape=True),
        ).delete(synchronize_session=False)

    def _index_file(
        self,
        db: Any,
        path: str,
        file_path: Path,
        stat: os.stat_result,
        row: Optional[DocumentFile],
        report: SyncReport,
    ) -> None:
        pieces: List[Tuple[str, str]] = []
        error: Optional[str] = None
        digest = ""
        limit = _max_file_bytes()

        if stat.st_size > limit:
            error = f"larger than {limit // (1024 * 1024)} MB (AEHUB_DOCUMENTS_MAX_FILE_MB)"
        else:
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                logger.warning("Document %s not readable: %s", path, exc)
                return

            digest = hashlib.sha256(data).hexdigest()

            if row is not None and row.sha256 == digest:
                # Touched but not changed.
                row.mtime = stat.st_mtime
                report.unchanged += 1
                return

            try:
                pieces = extract_chunks(path, data)
            except Exception as exc:
                error = f"could not be read: {exc}"[:500]

            if len(pieces) > MAX_CHUNKS_PER_FILE:
                pieces = pieces[:MAX_CHUNKS_PER_FILE]
                error = f"only the first {MAX_CHUNKS_PER_FILE} parts are searchable"

        self._drop_chunks(db, path)
        now = datetime.utcnow()

        for locator, text in pieces:
            source = _source(path, locator)
            vector, embedder_name = self._store._embed(text)
            db.add(
                MemoryChunk(
                    workspace_id=self.workspace_id,
                    principal_id=DOCUMENTS_PRINCIPAL,
                    kind=DOCUMENT_KIND,
                    content=text,
                    content_hash=content_hash(DOCUMENT_KIND, f"{source}\n{text}"),
                    embedding=vector,
                    embedder=embedder_name,
                    trusted=False,
                    source=source,
                    created_at=now,
                )
            )

        if row is None:
            row = DocumentFile(workspace_id=self.workspace_id, path=path)
            db.add(row)
            report.added.append(path)
        else:
            report.updated.append(path)

        row.sha256 = digest
        row.size = stat.st_size
        row.mtime = stat.st_mtime
        row.chunks = len(pieces)
        row.error = error
        row.indexed_at = now

        if error:
            report.failed.append({"path": path, "error": error})

    def sync(self, budget_seconds: Optional[float] = None) -> SyncReport:
        """
        Bring the index in line with the folder. With a budget, changed files
        left over when it runs out are counted as pending; the next sync picks
        them up. Every file is committed on its own.
        """
        report = SyncReport(root=str(self.root))

        if not self.root.is_dir():
            report.root_exists = False
            return report

        deadline = time.monotonic() + budget_seconds if budget_seconds is not None else None

        with _SYNC_LOCK, self._session() as db:
            files = self._walk(report)
            known = {
                row.path: row
                for row in db.query(DocumentFile).filter(DocumentFile.workspace_id == self.workspace_id)
            }
            seen = set()

            for path, file_path in files:
                seen.add(path)

                try:
                    stat = file_path.stat()
                except OSError:
                    continue

                row = known.get(path)

                if row is not None and row.size == stat.st_size and row.mtime == stat.st_mtime:
                    report.unchanged += 1
                    continue

                if deadline is not None and time.monotonic() > deadline:
                    report.pending += 1
                    continue

                self._index_file(db, path, file_path, stat, row, report)
                db.commit()

            for path, row in known.items():
                if path not in seen:
                    self._drop_chunks(db, path)
                    db.delete(row)
                    report.removed.append(path)

            db.commit()

        return report

    # ------------------------------------------------------------------ read

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> List[DocumentHit]:
        hits: List[DocumentHit] = []

        for hit in self._store.search(query, limit=limit):
            path, locator = parse_source(hit.source)

            if path and locator:
                hits.append(DocumentHit(path=path, locator=locator, content=hit.content, score=hit.score))

        return hits

    def passage(self, path: str, locator: str) -> Optional[str]:
        """
        The indexed text a citation points to, None when there is none.
        """
        with self._session() as db:
            row = (
                db.query(MemoryChunk)
                .filter(
                    MemoryChunk.workspace_id == self.workspace_id,
                    MemoryChunk.principal_id == DOCUMENTS_PRINCIPAL,
                    MemoryChunk.source == _source(path, locator),
                )
                .first()
            )

            return row.content if row is not None else None

    def reembed(self) -> int:
        """
        Embed the document chunks again with the current embedder.
        """
        return self._store.reembed()

    def stale_vectors(self) -> int:
        return int(self._store.stats()["stale_vectors"])

    def upload_target(self, filename: str, size: int, replace: bool = False) -> Tuple[str, Path]:
        """
        Where an uploaded file would go: the top of the working folder (F6).
        Only a plain, visible file name with a supported extension, within
        the size limit; an existing file is replaced only when asked. Raises
        ValueError or FileExistsError.
        """
        name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()

        if (
            not name
            or name.startswith(".")
            or len(name) > 255
            or any(char in name for char in '<>:"|?*')
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError("Use a plain file name.")

        if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("Only .txt, .md, .markdown and .pdf files are indexed.")

        if size > _max_file_bytes():
            raise ValueError("The file is larger than the document size limit.")

        if not self.root.is_dir():
            raise ValueError("The working folder does not exist.")

        target = (self.root / name).resolve()

        if target.parent != self.root.resolve():
            raise ValueError("Use a plain file name.")

        if target.exists() and not replace:
            raise FileExistsError(name)

        return name, target

    def save_upload(self, filename: str, data: bytes, replace: bool = False) -> str:
        """
        Write an uploaded file (see upload_target) and return its index path.
        """
        name, target = self.upload_target(filename, len(data), replace)
        target.write_bytes(data)
        return name

    def files(self) -> List[Dict[str, Any]]:
        with self._session() as db:
            rows = (
                db.query(DocumentFile)
                .filter(DocumentFile.workspace_id == self.workspace_id)
                .order_by(DocumentFile.path)
                .all()
            )

            return [
                {
                    "path": row.path,
                    "size": row.size,
                    "chunks": row.chunks,
                    "error": row.error,
                    "indexed_at": row.indexed_at.isoformat() if row.indexed_at else None,
                }
                for row in rows
            ]


__all__ = [
    "DOCUMENT_KIND",
    "DOCUMENTS_PRINCIPAL",
    "DocumentHit",
    "DocumentIndex",
    "SyncReport",
    "chunk_lines",
    "citation",
    "documents_root",
    "extract_chunks",
    "find_citations",
    "max_file_bytes",
    "missing_citations",
    "parse_source",
]
