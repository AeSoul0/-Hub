"""
@file backend/app/files/trash.py
@description ÆHub's trash (N5): what delete_path removes can be restored.

delete_path no longer deletes: it moves the file or folder into a hidden
".aehub-trash" folder at the top of the allowed folder it was in (the same
disk, so a move is a rename). Hidden folders are out of reach of every file
tool (validate_path), so an agent can neither read nor empty the trash.

Each item is a folder "<when>-<id>" holding the item and item.json (where it
was, when it was deleted). Items older than AEHUB_TRASH_DAYS (30 by
default) are removed for good at the next delete or listing. From the
STRUMENTI page the owner restores an item to where it was (never over
something that is there now) or removes it for good.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from app.agent_engine.guardrails import allowed_directories
from app.core.runtime_config import config_value

TRASH_NAME = ".aehub-trash"
META = "item.json"
DEFAULT_DAYS = 30


@dataclass(frozen=True)
class TrashItem:
    id: str
    original: str
    deleted_at: str
    kind: str  # "file" or "folder"
    size: int
    folder: Path

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original": self.original,
            "deleted_at": self.deleted_at,
            "kind": self.kind,
            "size": self.size,
        }


class TrashError(RuntimeError):
    """An item that cannot be restored or does not exist."""


def keep_days() -> int:
    try:
        return max(1, int(config_value("AEHUB_TRASH_DAYS") or DEFAULT_DAYS))
    except ValueError:
        return DEFAULT_DAYS


def _root_of(path: Path) -> Path:
    """The allowed folder that holds the path (the deepest one)."""
    roots = sorted(allowed_directories(), key=lambda root: len(root.parts), reverse=True)
    for root in roots:
        if path == root or root in path.parents:
            return root
    raise TrashError(f"{path} is not in an allowed folder.")


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for directory, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(directory) / name).stat().st_size
            except OSError:
                continue
    return total


def move_to_trash(path: Path) -> TrashItem:
    """Move a file or folder (already checked by validate_path) into its folder's trash."""
    root = _root_of(path)
    if path == root:
        raise TrashError(f"{path} is one of the allowed folders: it cannot be deleted.")
    now = datetime.now(timezone.utc)
    ident = f"{now:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
    folder = root / TRASH_NAME / ident
    folder.mkdir(parents=True)
    kind = "folder" if path.is_dir() else "file"
    size = _size(path)
    shutil.move(str(path), str(folder / path.name))
    item = TrashItem(ident, str(path), now.isoformat(timespec="seconds"), kind, size, folder)
    (folder / META).write_text(json.dumps(item.to_dict()), encoding="utf-8")
    purge()
    return item


def _items() -> List[TrashItem]:
    found: List[TrashItem] = []
    for root in allowed_directories():
        trash = root / TRASH_NAME
        if not trash.is_dir():
            continue
        for folder in sorted(trash.iterdir()):
            try:
                meta = json.loads((folder / META).read_text(encoding="utf-8"))
                found.append(TrashItem(meta["id"], meta["original"], meta["deleted_at"], meta["kind"], int(meta["size"]), folder))
            except (OSError, ValueError, KeyError):
                continue
    return sorted(found, key=lambda item: item.deleted_at, reverse=True)


def purge(now: Optional[datetime] = None) -> int:
    """Remove for good the items older than keep_days(). Returns how many."""
    limit = (now or datetime.now(timezone.utc)) - timedelta(days=keep_days())
    removed = 0
    for item in _items():
        if datetime.fromisoformat(item.deleted_at) < limit:
            shutil.rmtree(item.folder, ignore_errors=True)
            removed += 1
    return removed


def list_items() -> List[TrashItem]:
    purge()
    return _items()


def _find(item_id: str) -> TrashItem:
    for item in _items():
        if item.id == item_id:
            return item
    raise TrashError("This item is no longer in the trash.")


def restore(item_id: str) -> str:
    """Put an item back where it was; never over something that is there now."""
    item = _find(item_id)
    original = Path(item.original)
    if original.exists():
        raise TrashError(f"{original} exists again: move or rename it, then restore.")
    if not original.parent.is_dir():
        raise TrashError(f"The folder {original.parent} no longer exists.")
    # Still a place the file tools may write: inside an allowed folder, not
    # ÆHub's own files, not hidden (item.json is not trusted blindly).
    from app.agent_engine.guardrails import GuardrailException, validate_path

    try:
        original = validate_path(str(original))
    except GuardrailException as exc:
        raise TrashError(f"{item.original} is not a place ÆHub may restore to: {exc}") from exc
    shutil.move(str(item.folder / Path(item.original).name), str(original))
    shutil.rmtree(item.folder, ignore_errors=True)
    return str(original)


def remove(item_id: str) -> None:
    """Remove one item for good."""
    shutil.rmtree(_find(item_id).folder, ignore_errors=True)


def empty() -> int:
    items = _items()
    for item in items:
        shutil.rmtree(item.folder, ignore_errors=True)
    return len(items)


__all__ = ["TRASH_NAME", "TrashError", "TrashItem", "empty", "keep_days", "list_items", "move_to_trash", "purge", "remove", "restore"]
