"""
@file tests/unit/test_playwright_pin.py
@description The backend image and the `playwright` package move together.

The image `mcr.microsoft.com/playwright/python:vX.Y.Z-noble` ships the
browsers of exactly one Playwright release; a different `playwright==` pin
would look for browsers that are not there and break the browser tool at
runtime. Dependabot updates the image and the pins in separate pull requests
(Docker and pip), so this test makes a lone half fail in CI.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def _image_version() -> str:
    dockerfile = (BACKEND / "dockerfile").read_text(encoding="utf-8")
    found = re.search(r"^FROM mcr\.microsoft\.com/playwright/python:v([\d.]+)-", dockerfile, re.MULTILINE)
    assert found, "the backend image is no longer the Playwright one: update this test"
    return found.group(1)


def _pin(requirements: str) -> str:
    text = (BACKEND / requirements).read_text(encoding="utf-8")
    found = re.search(r"^playwright==([\d.]+)\s*$", text, re.MULTILINE)
    assert found, f"{requirements} has no exact playwright pin"
    return found.group(1)


def test_the_playwright_pins_match_the_image():
    image = _image_version()

    for requirements in ("requirements.txt", "requirements-desktop.txt"):
        assert _pin(requirements) == image, (
            f"backend/{requirements} pins playwright {_pin(requirements)} but the image is {image}: "
            "update both together"
        )
