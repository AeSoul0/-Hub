"""
@file tests/unit/test_playwright_pin.py
@description The backend image installs the browser of its own `playwright` pin.

Since N8 (ADR-039) the image starts from Python slim and, with
AEHUB_BROWSER=1, runs `playwright install --only-shell chromium`: the
package installs the browser of its own release, so image and pin cannot
drift apart. What is left to keep together: the same exact pin for the
Docker backend and the desktop app, and no return to a Playwright base image
whose browsers would belong to another release.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def _pin(requirements: str) -> str:
    text = (BACKEND / requirements).read_text(encoding="utf-8")
    found = re.search(r"^playwright==([\d.]+)\s*$", text, re.MULTILINE)
    assert found, f"{requirements} has no exact playwright pin"
    return found.group(1)


def test_docker_and_the_desktop_app_pin_the_same_playwright():
    assert _pin("requirements.txt") == _pin("requirements-desktop.txt")


def test_the_image_installs_the_browser_of_its_pin_only_when_asked():
    dockerfile = (BACKEND / "dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, re.MULTILINE)
    assert "mcr.microsoft.com/playwright" not in dockerfile
    assert "ARG AEHUB_BROWSER=0" in dockerfile
    assert "playwright install --with-deps --only-shell chromium" in dockerfile
