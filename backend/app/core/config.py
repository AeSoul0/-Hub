"""
@file backend/app/core/config.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "ÆHub Core OS"
    DEBUG_MODE: bool = False
    
    # Secrets
    AEHUB_SECRET_KEY: str
    GROQ_API_KEY: str
    OPENROUTER_API_KEY: str = ""
    
    # Connections
    POSTGRES_URL: str = "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # LLM Defaults
    DEFAULT_LLM_MODEL: str = "llama-3.2-90b-vision-preview"
    DEFAULT_TEMPERATURE: float = 0.75

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
