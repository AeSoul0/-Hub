"""
@file tests/database/test_migrations.py
@description D1 exit tests (ADR-031): Alembic is the only source of the schema.

- From scratch, the revisions build exactly the SQLAlchemy models: an
  autogenerate comparison finds nothing to add or remove.
- A database built by the old `create_all` startup, from this release or an
  older one that lacks a table, is recognised, marked at the baseline and
  brought to head without losing a row.
- No startup path uses `create_all` any more (the offline evals excepted).

The PostgreSQL tests make a throwaway database next to
AEHUB_TEST_POSTGRES_URL. They skip when no server answers, except in CI,
where a skip would hide a broken migration.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.core.migrations import alembic_config, current_revision, head_revision, include_object, upgrade_database
from app.domain.models import Base

BACKEND = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture
def empty_database():
    url = make_url(os.getenv("AEHUB_TEST_POSTGRES_URL", ""))

    if not url.drivername.startswith("postgresql"):
        pytest.skip("AEHUB_TEST_POSTGRES_URL is not a PostgreSQL URL.")

    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2})
    name = f"aehub_migrations_{uuid.uuid4().hex[:10]}"

    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        admin.dispose()

        # In CI the database is there and a missing one is an error, except
        # in the Windows job, whose runner has no PostgreSQL with pgvector
        # (backend-windows: AEHUB_TEST_NO_POSTGRES=1; the Linux job runs these).
        if os.getenv("CI") and os.getenv("AEHUB_TEST_NO_POSTGRES") != "1":
            raise
        pytest.skip(f"PostgreSQL is not reachable: {exc.orig}")

    engine = create_engine(url.set(database=name))

    yield engine

    engine.dispose()

    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _differences(engine) -> list:
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={"compare_type": True, "compare_server_default": True, "include_object": include_object},
        )
        return compare_metadata(context, Base.metadata)


def _old_startup(engine) -> None:
    """What `main.startup_db` did before D1."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


# ==============================================================================
# FROM SCRATCH
# ==============================================================================


def test_the_revisions_build_exactly_the_models(empty_database):
    assert upgrade_database(empty_database) == head_revision()

    assert _differences(empty_database) == []

    names = set(inspect(empty_database).get_table_names())
    assert set(Base.metadata.tables) <= names
    assert "alembic_version" in names

    with empty_database.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() == 1
        # The GIN index autogenerate cannot see.
        assert conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_memory_chunks_fts'")).scalar() == 1


def test_a_second_start_changes_nothing(empty_database):
    first = upgrade_database(empty_database)
    tables = set(inspect(empty_database).get_table_names())

    assert upgrade_database(empty_database) == first
    assert set(inspect(empty_database).get_table_names()) == tables


# ==============================================================================
# FROM A create_all DATABASE
# ==============================================================================


def test_a_create_all_database_is_marked_and_keeps_its_rows(empty_database):
    _old_startup(empty_database)
    # A database from an older release: it lacks a table added later (F5).
    with empty_database.begin() as conn:
        conn.execute(text("DROP TABLE imported_skills"))
        conn.execute(
            text("INSERT INTO app_settings (key, value, updated_at) VALUES ('AEHUB_MONTHLY_BUDGET', '42', now())")
        )
        conn.execute(
            text(
                "INSERT INTO memory_chunks (id, workspace_id, principal_id, kind, content, content_hash, trusted) "
                "VALUES ('m1', 'ws', 'user', 'fact', 'The cat is called Miso.', 'h1', true)"
            )
        )
        assert current_revision(conn) is None

    assert upgrade_database(empty_database) == head_revision()

    with empty_database.connect() as conn:
        assert current_revision(conn) == head_revision()
        assert conn.execute(text("SELECT value FROM app_settings WHERE key = 'AEHUB_MONTHLY_BUDGET'")).scalar() == "42"
        assert conn.execute(text("SELECT content FROM memory_chunks WHERE id = 'm1'")).scalar() == "The cat is called Miso."
        # The lexical index still finds it.
        found = conn.execute(
            text("SELECT id FROM memory_chunks WHERE to_tsvector('simple'::regconfig, content) @@ plainto_tsquery('simple', 'Miso')")
        ).scalar()
        assert found == "m1"

    assert "imported_skills" in inspect(empty_database).get_table_names()
    assert _differences(empty_database) == []


# ==============================================================================
# NO create_all AT STARTUP, ONE LINE OF REVISIONS
# ==============================================================================


def test_the_revisions_form_one_line():
    scripts = ScriptDirectory.from_config(alembic_config())

    assert len(scripts.get_heads()) == 1, "two heads: merge them with `alembic merge heads`"
    assert scripts.get_base() == "0001"


def test_only_the_offline_evals_use_create_all():
    allowed = {BACKEND / "app" / "evaluation" / "engine.py"}
    found = set()

    for path in [*(BACKEND / "app").rglob("*.py"), *BACKEND.glob("*.py")]:
        if re.search(r"\bcreate_all\(", path.read_text(encoding="utf-8")):
            found.add(path)

    assert found <= allowed, f"create_all outside the evals: {sorted(map(str, found - allowed))}"
