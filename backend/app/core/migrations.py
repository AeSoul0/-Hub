"""
@file backend/app/core/migrations.py
@description The database schema at startup (D1, ADR-031): `alembic upgrade
head` on the API's own engine, in place of `create_all`.

Three cases, one call:
- an empty database gets every revision, from the baseline on;
- a database built by `create_all` before D1 (tables, no `alembic_version`)
  is recognised and logged; the baseline creates only the tables it lacks
  and marks it, then the later revisions run. No row is touched;
- a database already on Alembic gets only the revisions it has not had.

Docker, `make demo` and the desktop sidecar all start through
`main.startup_db`, so they all pass here. The offline evals keep
`create_all` on their in-memory SQLite (`app/evaluation/engine.py`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
VERSION_TABLE = "alembic_version"

# Objects the models create with a DDL event instead of declaring them, so
# autogenerate would see them as removed: the revisions manage them by hand.
MANAGED_BY_HAND = {"ix_memory_chunks_fts"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Autogenerate filter: leave out the objects the revisions manage by hand."""
    return not (type_ == "index" and name in MANAGED_BY_HAND)


def alembic_config(connection: Connection | None = None) -> Config:
    """The project's Alembic configuration, wherever the process started."""
    config = Config(str(ALEMBIC_INI))
    # Absolute, so the desktop sidecar and the tests find the scripts from
    # any working directory.
    config.set_main_option("script_location", str(ALEMBIC_DIR))

    if connection is not None:
        config.attributes["connection"] = connection

    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None, "no Alembic revision in backend/alembic/versions"
    return head


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def upgrade_database(engine: Engine) -> str:
    """
    Bring the schema to the newest revision and return it.
    """
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())

        if tables and VERSION_TABLE not in tables:
            logger.warning(
                "Database built before migrations (%d tables, no %s): the "
                "baseline adds the missing tables and marks it; no row changes.",
                len(tables),
                VERSION_TABLE,
            )

        before = current_revision(connection)
        command.upgrade(alembic_config(connection), "head")
        after = current_revision(connection)

    if before != after:
        logger.info("Database schema: %s -> %s", before or "empty", after)

    return after or ""


__all__ = ["alembic_config", "current_revision", "head_revision", "include_object", "upgrade_database"]
