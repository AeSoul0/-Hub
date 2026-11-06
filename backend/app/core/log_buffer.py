"""
@file backend/app/core/log_buffer.py
@description The backend's recent warnings and errors, for the SISTEMA page
(F9, ADR-030).

A logging handler on the root logger keeps the last LOG_KEPT records at
WARNING or above in memory: nothing is written to disk, and a restart
empties it. Messages are cut to MESSAGE_CHARS.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

LOG_KEPT = 300
MESSAGE_CHARS = 2000


class RecentLogHandler(logging.Handler):
    def __init__(self, capacity: int = LOG_KEPT) -> None:
        super().__init__(level=logging.WARNING)
        self.records: Deque[Dict[str, Any]] = deque(maxlen=capacity)
        self._records_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                message = f"{message} ({type(record.exc_info[1]).__name__}: {record.exc_info[1]})"
        except Exception:
            message = str(record.msg)

        with self._records_lock:
            self.records.append(
                {
                    "at": datetime.utcfromtimestamp(record.created).isoformat(),
                    "level": record.levelname.lower(),
                    "logger": record.name,
                    "message": message[:MESSAGE_CHARS],
                }
            )

    def recent(self, limit: int, level: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._records_lock:
            items = list(self.records)

        if level:
            items = [item for item in items if item["level"] == level]

        return list(reversed(items))[:limit]


_handler: Optional[RecentLogHandler] = None
_install_lock = threading.Lock()


def install() -> RecentLogHandler:
    """
    Attach the handler to the root logger once; later calls return it.
    """
    global _handler

    with _install_lock:
        if _handler is None:
            _handler = RecentLogHandler()
            logging.getLogger().addHandler(_handler)

    return _handler


def recent_logs(limit: int = 200, level: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    The newest records first; empty until install() ran.
    """
    return _handler.recent(limit, level) if _handler is not None else []


__all__ = ["LOG_KEPT", "RecentLogHandler", "install", "recent_logs"]
