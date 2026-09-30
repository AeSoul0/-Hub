"""
@file backend/app/skills/browser_skill.py
@description Native browser automation skill for A.U.R.O.R.A.

Provides SSRF-protected browser navigation and text extraction through a
framework-agnostic asynchronous Python callable.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from bs4 import BeautifulSoup

from app.core.security import Permission
from app.skills.base import (
    BaseSkill,
    RiskLevel,
    SkillMetadata,
    ToolMetadata,
)


# ==============================================================================
# BROWSER TOOL
# ==============================================================================


async def browse_and_extract(url: str) -> str:
    """
    Navigate to a validated URL and return readable page text.

    SSRF validation is mandatory before the browser is allowed to access the
    requested URL. Browser resources are created per invocation and closed
    before the tool returns.
    """
    try:
        from app.core.ssrf_protector import SSRFProtector

        SSRFProtector.validate_url(url)

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
            )

            try:
                context = await browser.new_context()

                try:
                    page = await context.new_page()

                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )

                    html = await page.content()

                finally:
                    await context.close()

            finally:
                await browser.close()

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for element in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "iframe",
                "noscript",
            ]
        ):
            element.decompose()

        text = soup.get_text(
            separator="\n",
            strip=True,
        )

        if len(text) > 10_000:
            return (
                text[:10_000]
                + "\n\n[Content truncated by browser skill]"
            )

        return text

    except ImportError:
        return "Browser Error: Playwright is not installed."

    except Exception as exc:
        return f"Browser Error: {exc}"


# ==============================================================================
# BROWSER SKILL
# ==============================================================================


class BrowserSkill(BaseSkill):
    """
    Provides controlled browser navigation and rendered page extraction.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return the browser skill metadata.
        """
        return SkillMetadata(
            name="browser_automation",
            description=(
                "Provides controlled browser navigation and extraction "
                "of rendered web page content."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return the executable browser tools.
        """
        return [browse_and_extract]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return the security and execution metadata for browser tools.
        """
        return {
            "browse_and_extract": ToolMetadata(
                name="browse_and_extract",
                description=(
                    "Navigate to a validated URL and extract visible "
                    "text from the rendered page."
                ),
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                permissions_required=[
                    Permission.NETWORK_ACCESS.value,
                ],
                network_access=True,
                filesystem_access=False,
                max_runtime=30,
                max_output=10_000,
                max_cost=0.0,
                idempotent=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "format": "uri",
                        }
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="browser",
                audit_policy="standard",
            )
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return browser-specific system instructions.
        """
        return (
            "You have access to a controlled browser tool. "
            "Use 'browse_and_extract' only when current web content is "
            "required. URLs are validated against SSRF protections before "
            "network access is permitted."
        )


def get_skill() -> BaseSkill:
    """
    Create the browser skill instance.
    """
    return BrowserSkill()