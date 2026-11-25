"""
@file backend/app/core/config.py
@description The few values the API needs before it can start: the login
secret and the database and Redis URLs, read from the environment or
`backend/.env`. Everything that can change while ÆHub runs lives in
`app/core/runtime_config.py` instead.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Startup values; the SISTEMA page shows the URLs read only, never the secret.
    """
    # The login secret; provider keys come from the keyring or the environment.
    AEHUB_SECRET_KEY: str

    # Connections
    POSTGRES_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
