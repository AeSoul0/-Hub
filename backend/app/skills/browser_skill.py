"""
@file backend/app/skills/browser_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Callable, List, Optional, Dict
from bs4 import BeautifulSoup
from langchain_core.tools import tool
import asyncio

from app.skills.base import BaseSkill, SkillMetadata, ToolMetadata, RiskLevel

# We will use playwright in a managed way. To avoid hanging the event loop,
# we use the async API. Note that managing a long-lived browser instance 
# per session is complex, so we will use isolated contexts per tool call for simplicity,
# or require the user to chain actions.

@tool
async def browse_and_extract(url: str) -> str:
    """Navigates to a URL, waits for rendering, and extracts the text content. Use this to read web pages."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = await page.content()
            await browser.close()
            
            # Use BeautifulSoup to extract clean text
            soup = BeautifulSoup(html, "html.parser")
            for script in soup(["script", "style", "nav", "footer", "iframe"]):
                script.decompose()
            text = soup.get_text(separator="\n", strip=True)
            
            # Truncate to avoid blowing up the context window
            if len(text) > 15000:
                text = text[:15000] + "\n\n[Content Truncated]"
                
            return text
    except ImportError:
        return "Error: Playwright not installed."
    except Exception as e:
        return f"Browser Error: {str(e)}"

class BrowserSkill(BaseSkill):
    """
    M5 Sensory Expansion: Browser Automation.
    Enables autonomous web scraping and rendering analysis.
    """
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="browser_automation",
            description="Allows A.U.R.O.R.A. to actively navigate the web, render javascript pages, and extract data.",
            version="1.0.0"
        )
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "browse_and_extract": ToolMetadata(
                name="browse_and_extract",
                description="Navigates to a URL and extracts visible text.",
                risk_level=RiskLevel.MEDIUM,
                network_access=True
            )
        }

    @property
    def tools(self) -> List[Callable]:
        return [browse_and_extract]
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        return (
            "You have access to a fully headless browser. "
            "Use 'browse_and_extract' to read the contents of any URL provided or found via web search. "
            "This allows you to bypass simple scrapers and read modern JS-rendered websites."
        )

def get_skill() -> BaseSkill:
    return BrowserSkill()
