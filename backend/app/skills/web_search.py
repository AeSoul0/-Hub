"""
@file backend/app/skills/web_search.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import json
from typing import List, Callable, Optional
from duckduckgo_search import DDGS
from langchain_core.tools import tool

from .base import BaseSkill, SkillMetadata

@tool
def perform_web_search(query: str) -> str:
    """Cerca informazioni su internet in tempo reale. Usa questo tool per rispondere a domande su notizie recenti, meteo, o informazioni non presenti nel tuo contesto."""
    try:
        results = DDGS().text(query, max_results=3)
        return json.dumps(results, ensure_ascii=False) if results else "No results found."
    except Exception as e:
        return f"Error during web search: {str(e)}"


class WebSearchSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="web_search",
            description="Provides capabilities to search the internet for real-time information using DuckDuckGo.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        return [perform_web_search]
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        return (
            "You have access to a web search tool. "
            "Use it when you need to answer questions about current events, "
            "real-time data, or subjects you lack knowledge of."
        )

def get_skill() -> BaseSkill:
    return WebSearchSkill()
