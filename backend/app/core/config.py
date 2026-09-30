"""
@file backend/app/core/config.py
@description Implements config.py. Core components: Settings.

This module manages the internal business logic for Settings.
It provides specialized functionality to handle: utility operations.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Represents the Settings entity and its core operations.
    """
    # App Config
    APP_NAME: str = "ÆHub Core OS"
    DEBUG_MODE: bool = False
    
    # Secrets
    AEHUB_SECRET_KEY: str
    GROQ_API_KEY: str
    OPENROUTER_API_KEY: str = ""
    
    # Connections
    POSTGRES_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # LLM Defaults
    DEFAULT_LLM_MODEL: str = "llama-3.2-90b-vision-preview"
    DEFAULT_TEMPERATURE: float = 0.75

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
