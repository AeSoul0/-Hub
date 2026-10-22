"""
@file backend/app/agent_engine/guardrails.py
@description Input, output and tool guardrails for the native agent engine.

- InputGuardrail rejects obvious direct prompt-injection phrases in a task.
- OutputGuardrail redacts secrets (prefixed API keys, JWTs, private keys and
  the values of configured secret environment variables) instead of failing
  on loose substrings such as "sk-" inside "risk-based".
- ToolGuardrail blocks catastrophic arguments before execution, enforces SSRF
  and directory-allowlist checks for network/filesystem tools, and sanitizes
  tool output before it reaches the model or the audit log.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Tuple


class GuardrailException(Exception):
    """
    Raised when a guardrail rejects an input, an output or a tool call.
    """


# ==============================================================================
# SECRET REDACTION
# ==============================================================================


SECRET_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
            r"[\s\S]*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|\Z)"
        ),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
        ),
    ),
    (
        "anthropic_api_key",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}"),
    ),
    (
        "stripe_key",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    ),
    (
        "groq_api_key",
        re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    ),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    ),
    (
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    ),
    (
        "slack_token",
        re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ),
]

# Environment variables whose values are secrets by name.
_SECRET_ENV_NAME = re.compile(
    r"(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)",
    re.IGNORECASE,
)

# Shorter values are too likely to collide with ordinary text.
_MIN_ENV_SECRET_LENGTH = 12


def _configured_secret_values() -> List[Tuple[str, str]]:
    """
    Return (env name, value) for every configured secret environment value.
    """
    values = []

    for name, value in os.environ.items():
        if (
            value
            and len(value) >= _MIN_ENV_SECRET_LENGTH
            and _SECRET_ENV_NAME.search(name)
        ):
            values.append((name, value))

    # Longest first, so a secret containing another one is redacted whole.
    return sorted(values, key=lambda item: len(item[1]), reverse=True)


def redact_secrets(text: str) -> Tuple[str, List[str]]:
    """
    Redact known secret formats and configured secret values from text.

    Returns the redacted text and the kinds of secret that were found.
    """
    findings: List[str] = []

    for name, value in _configured_secret_values():
        if value in text:
            text = text.replace(value, f"[REDACTED:{name}]")
            findings.append(name)

    for kind, pattern in SECRET_PATTERNS:
        text, count = pattern.subn(f"[REDACTED:{kind}]", text)
        if count:
            findings.append(kind)

    return text, findings


def contains_secret(text: str) -> bool:
    """
    Return True when text holds a known secret format or configured secret.
    """
    return bool(redact_secrets(text)[1])


# ==============================================================================
# INPUT / OUTPUT GUARDRAILS
# ==============================================================================


class InputGuardrail:
    """
    Rejects obvious direct prompt-injection phrases in a task description.

    This is a cheap first filter, not the security boundary: indirect
    injection is contained by provenance tracking and the ToolGateway.
    """

    DISALLOWED = [
        r"ignore (?:all )?(?:the )?previous instructions",
        r"disregard (?:all )?(?:the )?(?:previous|prior|above) instructions",
        r"system prompt",
    ]

    @classmethod
    def validate(cls, text: str) -> str:
        for pattern in cls.DISALLOWED:
            if re.search(pattern, text, re.IGNORECASE):
                raise GuardrailException(
                    f"Input rejected by guardrail: matched pattern {pattern}"
                )
        return text


class OutputGuardrail:
    """
    Redacts secrets from a final answer before it leaves the engine.
    """

    @classmethod
    def validate(cls, text: str) -> str:
        return redact_secrets(text)[0]


# ==============================================================================
# TOOL GUARDRAIL
# ==============================================================================


# Arguments that carry code or shell commands, whatever the tool.
_COMMAND_ARGUMENT_KEYS = {"cmd", "command", "code", "script"}

# Commands that would destroy the host or the sandbox image regardless of
# context. Ordinary deletes (rm -rf ./build) stay allowed.
_ROOTISH_TARGET = (
    r"(?:/|/\*|~/?|\$HOME/?|\*|\.{1,2}/?|"
    r"/(?:bin|boot|dev|etc|home|lib|lib64|opt|proc|root|sbin|srv|sys|usr|var)/?)"
)

CATASTROPHIC_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "recursive delete of a root-level path",
        re.compile(
            r"\brm\s+(?:-{1,2}[\w-]+\s+)*['\"]?"
            + _ROOTISH_TARGET
            + r"['\"]?(?=[\s;&|)'\"]|$)",
        ),
    ),
    (
        "--no-preserve-root",
        re.compile(r"--no-preserve-root", re.IGNORECASE),
    ),
    (
        "filesystem format",
        re.compile(r"\bmkfs(?:\.[a-z0-9]+)?\b|\bformat\s+[a-z]:", re.IGNORECASE),
    ),
    (
        "raw write to a block device",
        re.compile(
            r"\bdd\b[^\n]*\bof=/dev/(?:sd|hd|nvme|xvd|vd|disk|mmcblk)"
            r"|>\s*/dev/(?:sd|hd|nvme|xvd|vd|disk|mmcblk)",
            re.IGNORECASE,
        ),
    ),
    (
        "fork bomb",
        re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    ),
    (
        "host power control",
        # Only at the start of a command, so Python's executor.shutdown()
        # is not mistaken for a host shutdown.
        re.compile(
            r"(?:^|[;&|(\"'`]\s*|\bsudo\s+)(?:shutdown|reboot|halt|poweroff|init\s+0)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "recursive permission change of /",
        re.compile(r"\bch(?:mod|own)\s+(?:-[a-zA-Z]*R[a-zA-Z]*\s+)\S+\s+/(?:\s|$)"),
    ),
    (
        "remote script piped to a shell",
        re.compile(
            r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recursive delete of a drive root",
        re.compile(
            r"\b(?:rd|rmdir|del)\s+(?:/[sq]\s+)+[a-z]:\\?(?:\s|$)"
            r"|Remove-Item\b[^\n]*-Recurse[^\n]*\s[a-z]:\\?(?:\s|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "recursive delete of the filesystem root from code",
        re.compile(
            r"\bshutil\.rmtree\(\s*['\"](?:/|~|[a-z]:\\\\?)['\"]",
            re.IGNORECASE,
        ),
    ),
]

# Argument names that hold a URL for network tools.
_URL_ARGUMENT_KEYS = {"url", "uri", "href", "link", "endpoint", "target_url"}
_URL_LIKE = re.compile(r"^\s*[a-zA-Z][a-zA-Z0-9+.-]*://")

# Argument names that hold a path for filesystem tools.
_PATH_ARGUMENT_KEYS = {
    "path",
    "file",
    "filename",
    "file_path",
    "filepath",
    "folder",
    "folder_path",
    "dir",
    "directory",
    "source",
    "destination",
}


def _iter_strings(value: Any, key: Optional[str] = None) -> Iterable[Tuple[Optional[str], str]]:
    """
    Yield (argument key, string) for every string inside a JSON-like value.
    """
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for child_key, child in value.items():
            yield from _iter_strings(child, str(child_key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_strings(child, key)


def allowed_directories() -> List[Path]:
    """
    Directories that filesystem tools may touch.

    AEHUB_ALLOWED_DIRS holds os.pathsep-separated roots. The default is the
    ./workspace folder of the current working directory.
    """
    configured = os.getenv("AEHUB_ALLOWED_DIRS", "")
    roots = [entry for entry in configured.split(os.pathsep) if entry.strip()]

    if not roots:
        roots = [os.path.join(os.getcwd(), "workspace")]

    return [Path(os.path.realpath(os.path.expanduser(root))) for root in roots]


def validate_path(raw_path: str) -> Path:
    """
    Normalize a path and require it to stay inside an allowed directory.

    Symlinks and ".." segments are resolved before the containment check.
    """
    if "\x00" in raw_path:
        raise GuardrailException("Path rejected: contains a NUL byte.")

    if not raw_path.strip():
        raise GuardrailException("Path rejected: empty path.")

    # On POSIX "C:\\Windows\\..." would be a relative file name inside the
    # workspace; a Windows absolute path is never a workspace path there.
    if os.name != "nt" and PureWindowsPath(raw_path).drive:
        raise GuardrailException(
            f"Path rejected: '{raw_path}' is a Windows absolute path."
        )

    roots = allowed_directories()
    candidate = Path(raw_path)

    if not candidate.is_absolute():
        candidate = roots[0] / candidate

    resolved = Path(os.path.realpath(candidate))

    for root in roots:
        if resolved == root or root in resolved.parents:
            return resolved

    raise GuardrailException(
        f"Path rejected: '{raw_path}' is outside the allowed directories."
    )


class ToolGuardrail:
    """
    Argument and output checks applied by the ToolGateway.
    """

    @classmethod
    def validate_pre_execution(cls, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reject catastrophic commands in any code or command argument.
        """
        for key, value in _iter_strings(args):
            if key is not None and key.lower() not in _COMMAND_ARGUMENT_KEYS:
                continue

            for label, pattern in CATASTROPHIC_PATTERNS:
                if pattern.search(value):
                    raise GuardrailException(
                        f"ToolGuardrail rejected parameter for {tool_name}: {label}."
                    )

        return args

    @classmethod
    def validate_resource_access(cls, spec: Any, args: Dict[str, Any]) -> None:
        """
        Enforce SSRF protection for network tools and the directory allowlist
        for filesystem tools. Arguments are validated, never rewritten, so the
        approval hash of the original call stays stable.
        """
        from app.core.ssrf_protector import SSRFError, SSRFProtector

        if getattr(spec, "network_access", False):
            for key, value in _iter_strings(args):
                is_url_key = key is not None and key.lower() in _URL_ARGUMENT_KEYS

                if not is_url_key and not _URL_LIKE.match(value):
                    continue

                try:
                    SSRFProtector.validate_url(value.strip())
                except SSRFError as exc:
                    raise GuardrailException(f"SSRF protection rejected '{key}': {exc}") from exc

        if getattr(spec, "filesystem_access", False):
            for key, value in _iter_strings(args):
                if key is None:
                    continue

                normalized_key = key.lower()

                if normalized_key in _PATH_ARGUMENT_KEYS or normalized_key.endswith(("_path", "_dir", "_file")):
                    validate_path(value)

    @classmethod
    def validate_post_execution(cls, tool_name: str, output: Any) -> Any:
        """
        Redact secrets and cap the size of a tool output before it is handed
        to the model or written to the audit log.
        """
        output_str = str(output)
        redacted, findings = redact_secrets(output_str)

        if findings:
            output_str = redacted
            output = redacted

        if len(output_str) > 10000:
            return output_str[:10000] + "... [TRUNCATED BY GUARDRAIL]"

        return output
