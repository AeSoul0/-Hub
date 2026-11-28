"""
@file tests/unit/test_windows_backend.py
@description N9: what the backend tests on Windows (CI job backend-windows) found.

- with PostgreSQL down or still starting, a connection gives up after a few
  seconds instead of the operating system's TCP timeout (minutes on Windows);
- memory chunks keep the order they were written in although the clock of
  Python 3.12 on Windows moves in steps of about 15 ms.
"""

from datetime import datetime

from app.core import db
from app.domain.models import memory


def test_postgresql_connections_give_up_after_a_few_seconds():
    url = "postgresql://user:pw@localhost:5432/aehub_db"
    assert db.connect_args(url) == {"connect_timeout": db.CONNECT_TIMEOUT_SECONDS}
    assert 0 < db.CONNECT_TIMEOUT_SECONDS <= 10
    # A timeout written in the URL wins; SQLite (some legacy tests) takes no such option.
    assert db.connect_args(url + "?connect_timeout=1") == {}
    assert db.connect_args("sqlite:///./aehub.db") == {}


def test_chunks_written_in_the_same_clock_step_keep_their_order(monkeypatch):
    frozen = datetime(2026, 11, 28, 12, 0, 0)

    class StuckClock(datetime):
        @classmethod
        def utcnow(cls):
            return frozen

    monkeypatch.setattr(memory, "datetime", StuckClock)
    monkeypatch.setattr(memory, "_last_stamp", datetime.min)

    stamps = [memory.created_now() for _ in range(5)]
    assert stamps == sorted(stamps) and len(set(stamps)) == 5
    assert stamps[0] == frozen
    assert memory.MemoryChunk.__table__.c.created_at.default.arg.__name__ == "created_now"


def test_the_store_stamps_its_chunks_with_that_time():
    from pathlib import Path

    from app.memory import store

    source = Path(store.__file__).read_text(encoding="utf-8")
    assert "created_at=created_now()" in source and "created_at=datetime.utcnow()" not in source
