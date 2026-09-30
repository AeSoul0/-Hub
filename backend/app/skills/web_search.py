"""
@file backend/app/skills/web_search.py
@description Native web-search skill for A.U.R.O.R.A.

Provides controlled internet search through DuckDuckGo. Network capability
is explicitly declared in tool metadata so the central policy engine can
enforce it before execution.
"""

from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from duckduckgo_search import DDGS

from app.core.security import Permission
from app.skills.base import (
    BaseSkill,
    RiskLevel,
    SkillMetadata,
    ToolMetadata,
)


# ==============================================================================
# WEB SEARCH TOOL
# ==============================================================================


def perform_web_search(
    query: str,
) -> str:
    """
    Search the public web and return a compact JSON result set.
    """
    if not query.strip():
        raise ValueError(
            "Search query cannot be empty."
        )

    try:
        results = DDGS().text(
            query,
            max_results=3,
        )

        if not results:
            return "No web results found."

        return json.dumps(
            results,
            ensure_ascii=False,
        )

    except Exception as exc:
        return f"Web search error: {exc}"


# ==============================================================================
# WEB SEARCH SKILL
# ==============================================================================


class WebSearchSkill(BaseSkill):
    """
    Provides controlled access to public web search.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return web-search skill metadata.
        """
        return SkillMetadata(
            name="web_search",
            description=(
                "Searches public web content for current or externally "
                "verified information."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return the executable web-search tool.
        """
        return [
            perform_web_search,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return web-search security and execution metadata.
        """
        return {
            "perform_web_search": ToolMetadata(
                name="perform_web_search",
                description=(
                    "Search the public internet using DuckDuckGo."
                ),
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                permissions_required=[
                    Permission.NETWORK_ACCESS.value,
                ],
                network_access=True,
                filesystem_access=False,
                max_runtime=20,
                max_output=8000,
                max_cost=0.0,
                idempotent=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="network",
                audit_policy="standard",
            )
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return web-search system instructions.
        """
        return (
            "You have access to a controlled public web-search tool. "
            "Use it when information must be checked against current or "
            "external sources. Network access is enforced by the central "
            "policy layer."
        )


def get_skill() -> BaseSkill:
    """
    Create the web-search skill instance.
    """
    return WebSearchSkill()