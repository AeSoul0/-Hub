"""
@file backend/alembic/env.py
@description Alembic environment of ÆHub (D1, ADR-031): the schema is the
SQLAlchemy models' metadata, the database is POSTGRES_URL.

Two ways in:
- the API at startup (`app.core.migrations.upgrade_database`) passes its own
  open connection in `config.attributes["connection"]`;
- the command line from `backend/` (`alembic upgrade head`,
  `alembic revision --autogenerate -m "..."`) connects to POSTGRES_URL.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config

# The API configures its own logging; only the command line uses the ini's.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

from app.core.migrations import include_object  # noqa: E402  (after logging, as Alembic does)
from app.domain.models import Base  # noqa: E402

target_metadata = Base.metadata


def _url() -> str:
    from app.core.db import POSTGRES_URL

    return POSTGRES_URL


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )


def run_migrations_offline() -> None:
    """SQL to stdout (`alembic upgrade head --sql`), without a database."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")

    if connection is not None:
        _configure(connection)

        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_url(), poolclass=pool.NullPool)

    with engine.connect() as connection:
        _configure(connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
