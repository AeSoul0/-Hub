"""
@file backend/app/desktop/launch.py
@description Desktop mode state (ADR-020): the one-time launch token and the
OS keyring the Settings page writes provider keys to.

The sidecar (`backend/desktop.py`) enables desktop mode in the API process,
issues a token and hands it to the Tauri shell over its stdout pipe only.
The window opens /desktop/launch/<token>; the token is exchanged once for
the owner's session cookie and is then dead. Outside desktop mode nothing
here is active and /desktop/launch always refuses.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from typing import Optional, Protocol


LAUNCH_TOKEN_TTL_SECONDS = 120


class SecretStore(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str) -> None: ...


class _DesktopState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.enabled = False
        self.store: Optional[SecretStore] = None
        self.token_hash: Optional[str] = None
        self.token_expires_at = 0.0


_state = _DesktopState()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def enable(store: Optional[SecretStore] = None) -> None:
    with _state.lock:
        _state.enabled = True
        _state.store = store


def disable() -> None:
    with _state.lock:
        _state.enabled = False
        _state.store = None
        _state.token_hash = None
        _state.token_expires_at = 0.0


def desktop_mode() -> bool:
    return _state.enabled


def secret_store() -> Optional[SecretStore]:
    return _state.store


def issue_launch_token(ttl_seconds: int = LAUNCH_TOKEN_TTL_SECONDS) -> str:
    """
    A new token; the previous one, used or not, stops working.
    """
    if not _state.enabled:
        raise RuntimeError("Launch tokens exist only in desktop mode.")

    token = secrets.token_urlsafe(32)

    with _state.lock:
        _state.token_hash = _hash(token)
        _state.token_expires_at = time.monotonic() + ttl_seconds

    return token


def consume_launch_token(token: str) -> bool:
    """
    True once for the current token, inside its lifetime.
    """
    with _state.lock:
        expected = _state.token_hash
        valid = (
            _state.enabled
            and expected is not None
            and time.monotonic() < _state.token_expires_at
            and hmac.compare_digest(_hash(token), expected)
        )

        if valid:
            _state.token_hash = None

        return valid


__all__ = [
    "LAUNCH_TOKEN_TTL_SECONDS",
    "SecretStore",
    "consume_launch_token",
    "desktop_mode",
    "disable",
    "enable",
    "issue_launch_token",
    "secret_store",
]
