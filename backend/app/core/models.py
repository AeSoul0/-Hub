"""
@file backend/app/core/models.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel

class ModelProvider(str, Enum):
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

class ModelCapabilities(BaseModel):
    vision: bool = False
    function_calling: bool = False
    json_mode: bool = False

class ModelUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ModelRequest(BaseModel):
    messages: List[Dict[str, Any]]
    temperature: float = 0.7
    max_tokens: int = 1000

class ModelResponse(BaseModel):
    content: str
    usage: Optional[ModelUsage] = None

class ModelRouter:
    _cache_initialized = False

    @staticmethod
    def _init_cache():
        if not ModelRouter._cache_initialized:
            import os
            try:
                from langchain.globals import set_llm_cache
                from langchain_community.cache import RedisCache
                import redis
                
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                redis_client = redis.Redis.from_url(redis_url)
                set_llm_cache(RedisCache(redis_=redis_client))
                ModelRouter._cache_initialized = True
                print("[OK] Distributed Redis LLM Caching initialized.")
            except ImportError:
                print("[WARN] langchain_community not installed, skipping Redis LLM caching.")

    @staticmethod
    def get_model(provider: ModelProvider, model_name: str, temperature: float = 0.75) -> BaseChatModel:
        import os
        ModelRouter._init_cache()
        
        if provider == ModelProvider.GROQ:
            from langchain_groq import ChatGroq
            return ChatGroq(model=model_name, temperature=temperature, api_key=os.getenv("GROQ_API_KEY"))
        elif provider == ModelProvider.OPENAI:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, temperature=temperature, api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == ModelProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model_name=model_name, temperature=temperature, api_key=os.getenv("ANTHROPIC_API_KEY"))
        elif provider == ModelProvider.LOCAL:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, temperature=temperature, api_key="not-needed", base_url="http://localhost:11434/v1")
        else:
            raise ValueError(f"Unsupported provider: {provider}")
