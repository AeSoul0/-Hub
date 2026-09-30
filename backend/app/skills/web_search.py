"""
@file backend/app/skills/web_search.py
@description Implements web_search.py. Core components: WebSearchSkill.

This module manages the internal business logic for WebSearchSkill.
It provides specialized functionality to handle: perform_web_search, metadata, tools, system_prompt_extension, get_skill.
"""
import json
from typing import Callable, List, Optional

from duckduckgo_search import DDGS
from langchain_core.tools import tool

from .base import BaseSkill, SkillMetadata


@tool
def perform_web_search(query: str) -> str:
    """
    Executes perform_web_search logic.
    """
    """Cerca informazioni su internet in tempo reale. Usa questo tool per rispondere a domande su notizie recenti, meteo, o informazioni non presenti nel tuo contesto."""
    try:
        # Fetch the top 3 web results matching the query
        results = DDGS().text(query, max_results=3)
        return json.dumps(results, ensure_ascii=False) if results else "No results found."
    except Exception as e:
        return f"Error during web search: {str(e)}"


class WebSearchSkill(BaseSkill):
    """
    Represents the WebSearchSkill entity and its core operations.
    """
    @property
    def metadata(self) -> SkillMetadata:
        """
        Executes metadata logic.
        """
        # Define the skill metadata
        return SkillMetadata(
            name="web_search",
            description="Provides capabilities to search the internet for real-time information using DuckDuckGo.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        """
        Executes tools logic.
        """
        # Expose the web search tool
        return [perform_web_search]
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Executes system_prompt_extension logic.
        """
        # Prompt context explaining when to rely on web search
        return (
            "You have access to a web search tool. "
            "Use it when you need to answer questions about current events, "
            "real-time data, or subjects you lack knowledge of."
        )

def get_skill() -> BaseSkill:
    """
    Executes get_skill logic.
    """
    # Factory function to instantiate the skill
    return WebSearchSkill()
