"""
@file tests/conftest.py
@description Test-only environment defaults.

Settings() fails closed when secrets are missing, which is the correct
production behaviour. Unit tests must not need real credentials, so this
module provides placeholder values before any app module is imported.
Values already present in the environment (e.g. from CI) always win.
"""
import os

_TEST_ENV_DEFAULTS = {
    "AEHUB_SECRET_KEY": "test-only-secret-key",
    "GROQ_API_KEY": "test-only-groq-key",
    "POSTGRES_URL": "postgresql://aehub_user:password@localhost:5432/aehub_db",
    "REDIS_URL": "redis://localhost:6379/0",
    # Spec 4.1: the Critic must differ from the Implementer, or the engine
    # refuses to start.
    "AEHUB_CHECKER_MODEL": "test-only-critic-model",
    # Long-term memory needs the database; tests that exercise it enable it
    # explicitly against their own store. The hash embedder needs no model
    # download.
    "AEHUB_MEMORY_ENABLED": "0",
    "AEHUB_EMBEDDER": "hash",
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

# Some legacy test modules overwrite POSTGRES_URL at import time; tests that
# need the real database read this snapshot instead.
os.environ.setdefault("AEHUB_TEST_POSTGRES_URL", os.environ["POSTGRES_URL"])
