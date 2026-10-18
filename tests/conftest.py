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
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
