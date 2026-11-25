"""
@file backend/app/skills/skill_md.py
@description Reading and downloading SKILL.md files (F5, ADR-026).

SKILL.md is the open skill format of Claude Code, Codex and OpenClaw: a YAML
front matter with `name` and `description`, then Markdown instructions.
ÆHub imports only that text. Files a skill bundles (scripts/, references/,
assets/) are not imported and nothing in the text is run: the instructions
reach the model through the `use_skill` tool as untrusted content.

parse_skill_md() reads the front matter with a small parser (top-level
`key: value` lines, quoted values and `>`/`|` blocks), so no YAML library
is needed. It also returns warning codes for patterns the user should look
at before turning a skill on; they inform, they do not block.

fetch_skill_md() downloads a SKILL.md over https only, through the SSRF
checks of every hop, with a size cap. A GitHub page of the file or of the
skill folder is turned into its raw.githubusercontent.com address.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.ssrf_protector import SSRFError, SSRFProtector


MAX_SKILL_CHARS = 100_000
MAX_DESCRIPTION_CHARS = 1024
MAX_NAME_CHARS = 64
FETCH_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 4

_BLOCK_MARKERS = {">", ">-", ">+", "|", "|-", "|+"}

# Patterns worth a look before a skill is turned on (ClawHavoc-style skills
# hid downloaders and encoded payloads in their instructions).
WARNING_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (
        "download_and_run",
        re.compile(
            r"\b(curl|wget|iwr|invoke-webrequest)\b[^\n]*\|\s*(sudo\s+)?(\w*sh|iex|python\d?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded_payload",
        re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"),
    ),
    (
        "instruction_override",
        re.compile(
            r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+instructions"
            r"|disregard\s+(all\s+|the\s+)?(previous|prior|above)"
            r"|system\s+prompt",
            re.IGNORECASE,
        ),
    ),
    (
        "secrets",
        re.compile(
            r"\.env\b|id_rsa|\.ssh\b|private[\s_-]key|credential|password|api[\s_-]?key",
            re.IGNORECASE,
        ),
    ),
    (
        "bundled_files",
        re.compile(r"(?<![\w/.])(scripts|references|assets)/[\w.-]+"),
    ),
    (
        "external_links",
        re.compile(r"https?://", re.IGNORECASE),
    ),
)


class SkillFormatError(ValueError):
    """
    The text is not a SKILL.md ÆHub can import.
    """


class SkillFetchError(ValueError):
    """
    The link could not be downloaded as a SKILL.md.
    """


@dataclass(frozen=True)
class ParsedSkill:
    name: str
    description: str
    content: str
    sha256: str
    warnings: Tuple[str, ...]


# ==============================================================================
# PARSING
# ==============================================================================


def _unquote(value: str) -> str:
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]

    return value


def _front_matter(lines: List[str]) -> Dict[str, str]:
    """
    Top-level `key: value` pairs; nested keys are skipped.
    """
    fields: Dict[str, str] = {}
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1

        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue

        key, separator, value = line.partition(":")

        if not separator:
            continue

        key = key.strip().lower()
        value = value.strip()

        if value in _BLOCK_MARKERS:
            block: List[str] = []

            while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()):
                block.append(lines[index].strip())
                index += 1

            if value.startswith(">"):
                value = " ".join(part for part in block if part)
            else:
                value = "\n".join(block).strip()

        fields[key] = _unquote(value)

    return fields


def skill_slug(name: str) -> str:
    """
    The skill name as the format wants it: lowercase letters, digits and
    single hyphens, at most 64 characters.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:MAX_NAME_CHARS].rstrip("-")


def skill_warnings(text: str) -> Tuple[str, ...]:
    return tuple(code for code, pattern in WARNING_PATTERNS if pattern.search(text))


def parse_skill_md(text: str) -> ParsedSkill:
    """
    Check a SKILL.md and read its name and description.
    """
    text = text.lstrip("﻿").replace("\r\n", "\n")

    if "\x00" in text:
        raise SkillFormatError("The file is not text.")

    if len(text) > MAX_SKILL_CHARS:
        raise SkillFormatError(f"A SKILL.md can be at most {MAX_SKILL_CHARS} characters.")

    lines = text.split("\n")

    if not lines or lines[0].strip() != "---":
        raise SkillFormatError("A SKILL.md starts with a front matter block between --- lines.")

    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)

    if end is None:
        raise SkillFormatError("The front matter block is not closed by a --- line.")

    fields = _front_matter(lines[1:end])
    name = skill_slug(fields.get("name", ""))
    description = " ".join(fields.get("description", "").split())
    body = "\n".join(lines[end + 1:]).strip()

    if not name:
        raise SkillFormatError("The front matter has no name.")

    if not description:
        raise SkillFormatError("The front matter has no description.")

    if len(description) > MAX_DESCRIPTION_CHARS:
        raise SkillFormatError(f"The description can be at most {MAX_DESCRIPTION_CHARS} characters.")

    if not body:
        raise SkillFormatError("The skill has no instructions after the front matter.")

    content = text.strip() + "\n"

    return ParsedSkill(
        name=name,
        description=description,
        content=content,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        warnings=skill_warnings(text),
    )


# ==============================================================================
# DOWNLOAD
# ==============================================================================


def raw_skill_url(url: str) -> str:
    """
    The address to download: https only; a github.com page of a SKILL.md or
    of a skill folder becomes its raw.githubusercontent.com file.
    """
    url = url.strip()
    parts = urllib.parse.urlsplit(url)

    if parts.scheme != "https" or not parts.hostname:
        raise SkillFetchError("Use an https link.")

    if parts.username or parts.password:
        raise SkillFetchError("Links with credentials are not allowed.")

    if parts.hostname.lower() not in {"github.com", "www.github.com"}:
        return url

    segments = [urllib.parse.unquote(part) for part in parts.path.strip("/").split("/") if part]

    if len(segments) < 4 or segments[2] not in {"blob", "tree", "raw"}:
        raise SkillFetchError("Link a SKILL.md file or a skill folder of a GitHub repository.")

    owner, repository, kind, ref = segments[:4]
    path = "/".join(segments[4:])

    if kind == "tree" or not path.lower().endswith(".md"):
        path = f"{path}/SKILL.md" if path else "SKILL.md"

    quoted = "/".join(urllib.parse.quote(part) for part in [owner, repository, ref, *path.split("/")])
    return f"https://raw.githubusercontent.com/{quoted}"


async def fetch_skill_md(
    url: str,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Tuple[str, str]:
    """
    Download a SKILL.md; returns (text, the address it was read from).
    """
    current = raw_skill_url(url)

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=FETCH_TIMEOUT_SECONDS,
        transport=transport,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            if urllib.parse.urlsplit(current).scheme != "https":
                raise SkillFetchError("The link redirects to an address that is not https.")

            try:
                await asyncio.to_thread(SSRFProtector.validate_url, current)
            except SSRFError as exc:
                raise SkillFetchError("The link points to an address that is not public.") from exc

            async with client.stream("GET", current, headers={"Accept": "text/plain, text/markdown, */*"}) as response:
                if 300 <= response.status_code < 400 and response.headers.get("location"):
                    current = urllib.parse.urljoin(current, response.headers["location"])
                    continue

                if response.status_code != 200:
                    raise SkillFetchError(f"The link answered {response.status_code}.")

                body = bytearray()
                # A UTF-8 character is at most 4 bytes.
                limit = MAX_SKILL_CHARS * 4

                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise SkillFetchError("The file is too large for a SKILL.md.")

                try:
                    return bytes(body).decode("utf-8"), current
                except UnicodeDecodeError as exc:
                    raise SkillFetchError("The file is not UTF-8 text.") from exc

    raise SkillFetchError("Too many redirects.")


__all__ = [
    "MAX_DESCRIPTION_CHARS",
    "MAX_SKILL_CHARS",
    "ParsedSkill",
    "SkillFetchError",
    "SkillFormatError",
    "fetch_skill_md",
    "parse_skill_md",
    "raw_skill_url",
    "skill_slug",
    "skill_warnings",
]
