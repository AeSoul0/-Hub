"""
@file backend/app/skills/browser_skill.py
@description Native browser automation skill for A.U.R.O.R.A.

Provides SSRF-protected browser navigation and text extraction through a
framework-agnostic asynchronous Python callable. Every request the page makes
(redirects, images, scripts, fetch, WebSocket) passes the same SSRF check as
the first URL, so a public page cannot point the browser at this computer or
its network.

The Docker image has Chromium only when built with AEHUB_BROWSER=1 (N8,
ADR-039); without it the skill offers no tool, so the model never proposes
a browser that is not there.
"""

from __future__ import annotations
import asyncio
import logging
import os
from urllib.parse import urljoin

from typing import Callable, Dict, List

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


logger = logging.getLogger(__name__)

# Schemes that never reach the network.
LOCAL_SCHEMES = ("data:", "blob:", "about:")
MAX_REDIRECTS = 5


async def is_allowed_request(url: str) -> bool:
    """Whether the browser may load this URL: local schemes, or a public address."""
    from app.core.ssrf_protector import SSRFError, SSRFProtector

    if url.startswith(LOCAL_SCHEMES):
        return True
    try:
        # validate_url resolves DNS, which blocks: keep it off the event loop.
        await asyncio.to_thread(SSRFProtector.validate_url, url)
    except SSRFError as exc:
        logger.warning("Browser request blocked: %s", exc)
        return False
    return True


async def guard_request(route) -> None:
    """
    Playwright route handler: abort any request to a non-public address.

    Playwright calls the handler only for the first request of a redirect
    chain, and the browser's request after a redirect does not come back
    here either. So the handler follows the chain itself, one hop at a time,
    checks every hop, and hands the browser only the final response.
    """
    url = route.request.url
    if not await is_allowed_request(url):
        await route.abort("blockedbyclient")
        return
    if url.startswith(LOCAL_SCHEMES):
        await route.continue_()
        return
    for _ in range(MAX_REDIRECTS + 1):
        response = await route.fetch(url=url, max_redirects=0)
        location = response.headers.get("location")
        if not (300 <= response.status < 400 and location):
            await route.fulfill(response=response)
            return
        url = urljoin(url, location)
        if not await is_allowed_request(url):
            await route.abort("blockedbyclient")
            return
    logger.warning("Browser request blocked: more than %d redirects", MAX_REDIRECTS)
    await route.abort("blockedbyclient")


async def guard_web_socket(ws) -> None:
    """Playwright WebSocket handler: connect only to public addresses."""
    if await is_allowed_request(ws.url.replace("ws", "http", 1)):
        ws.connect_to_server()
    else:
        await ws.close(code=1008, reason="Blocked by ÆHub")


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
                # Service workers could fetch outside the route below.
                context = await browser.new_context(service_workers="block")
                await context.route("**/*", guard_request)
                await context.route_web_socket("**/*", guard_web_socket)

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

    except Exception as exc:  # noqa: BLE001 - a page error becomes the tool's answer
        logger.warning("Browser tool failed: %s", exc)
        return f"Browser Error: {exc}"


# ==============================================================================
# BROWSER SKILL
# ==============================================================================


def browser_available() -> bool:
    """False in a Docker image built without the browser (AEHUB_BROWSER=0), or without Playwright."""
    import importlib.util

    if os.getenv("AEHUB_IN_CONTAINER") == "1" and (os.getenv("AEHUB_BROWSER") or "1").strip() != "1":
        return False
    return importlib.util.find_spec("playwright") is not None


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
        return [browse_and_extract] if browser_available() else []

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return the security and execution metadata for browser tools.
        """
        if not browser_available():
            return {}
        return {
            "browse_and_extract": ToolMetadata(
                name="browse_and_extract",
                examples=["apri il sito", "leggi la pagina web", "pagina", "sito", "link", "url", "open the website", "read the web page", "page", "site"],
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

def get_skill() -> BaseSkill:
    """
    Create the browser skill instance.
    """
    return BrowserSkill()