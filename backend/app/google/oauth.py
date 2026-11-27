"""
@file backend/app/google/oauth.py
@description The owner's Google account (N4, ADR-046): OAuth with PKCE, and its tokens.

The owner creates an OAuth client in Google Cloud (type "Web application")
and registers the redirect address the STRUMENTI page shows; its id and
secret are keys like the others: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET,
from the keyring (launcher, desktop app) or the environment (a codespace
secret). "Connect" on STRUMENTI opens Google's consent page; Google sends
the browser back to /api/google/callback with a one-time code, exchanged
here for a refresh token.

The refresh token is a key too, never written to the database or a file:
- in the desktop app it goes to the OS keyring;
- elsewhere it stays in this process, and the page shows it once so the
  owner can save it as GOOGLE_REFRESH_TOKEN (codespace secret, or
  `python scripts/aehub.py setup`); after a restart it is read from there.

The access token lives in memory and is renewed before it expires. The
scopes are the least the tools need: the events of the calendars, reading
mail and sending mail.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105 - an endpoint, not a password
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)
CLIENT_ID = "GOOGLE_CLIENT_ID"
CLIENT_SECRET = "GOOGLE_CLIENT_SECRET"  # nosec B105 - the name of the variable
REFRESH_TOKEN = "GOOGLE_REFRESH_TOKEN"  # nosec B105 - the name of the variable
CALLBACK_PATH = "/api/google/callback"
FLOW_SECONDS = 600
TIMEOUT = 20.0
# An access token is renewed this long before Google says it expires.
RENEW_MARGIN = 120


class GoogleNotConnected(RuntimeError):
    """No client, no account, or Google refused the token: connect again from STRUMENTI."""


class GoogleError(RuntimeError):
    """Google answered with an error."""


@dataclass
class _Flow:
    verifier: str
    redirect_uri: str
    return_to: str
    created: float
    # Who started it, for the audit entry of the connection.
    owner_id: str = ""
    workspace_id: str = ""


@dataclass
class _State:
    lock: threading.Lock = field(default_factory=threading.Lock)
    flows: Dict[str, _Flow] = field(default_factory=dict)
    # The refresh token obtained in this process, when no keyring keeps it.
    refresh: Optional[str] = None
    # Shown once on STRUMENTI, so the owner can keep it as a secret.
    to_show: Optional[str] = None
    access: Optional[str] = None
    access_until: float = 0.0
    account: Optional[str] = None


_state = _State()
# Tests replace it with an httpx.MockTransport.
transport: Optional[httpx.AsyncBaseTransport] = None


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, transport=transport)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def client_configured() -> bool:
    return bool(_env(CLIENT_ID) and _env(CLIENT_SECRET))


def _store():
    from app.desktop.launch import secret_store

    return secret_store()


def refresh_token() -> Optional[str]:
    return _state.refresh or _env(REFRESH_TOKEN) or None


def token_source() -> Optional[str]:
    """Where the refresh token comes from: keyring, environment, memory, or None."""
    if _state.refresh:
        return "keyring" if _store() is not None else "memory"
    if _env(REFRESH_TOKEN):
        return "environment"
    return None


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def start(redirect_uri: str, return_to: str, owner_id: str = "", workspace_id: str = "") -> str:
    """The URL of Google's consent page for a new connection."""
    if not client_configured():
        raise GoogleNotConnected(f"Add {CLIENT_ID} and {CLIENT_SECRET} first.")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    now = time.monotonic()
    with _state.lock:
        _state.flows = {key: flow for key, flow in _state.flows.items() if now - flow.created < FLOW_SECONDS}
        _state.flows[state] = _Flow(verifier, redirect_uri, return_to, now, owner_id, workspace_id)
    query = {
        "client_id": _env(CLIENT_ID),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        # A refresh token, asked for again at every connection.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def flow_of(state: str) -> Optional[_Flow]:
    """The connection a state belongs to, without using it (where to send the browser back)."""
    with _state.lock:
        return _state.flows.get(state)


def _take_flow(state: str) -> _Flow:
    with _state.lock:
        flow = _state.flows.pop(state, None)
    if flow is None or time.monotonic() - flow.created >= FLOW_SECONDS:
        raise GoogleNotConnected("This connection link has expired or was already used: start again.")
    return flow


async def _token_request(data: Dict[str, str]) -> Dict[str, Any]:
    async with http_client() as client:
        response = await client.post(TOKEN_URL, data=data)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        error = str(body.get("error") or f"HTTP {response.status_code}")
        if error in ("invalid_grant", "unauthorized_client", "invalid_client"):
            raise GoogleNotConnected(f"Google refused the account ({error}): connect again from STRUMENTI.")
        raise GoogleError(f"Google token request failed: {error}.")
    return body


def _keep(refresh: str) -> None:
    """Keep a new refresh token: keyring when there is one, else this process (shown once)."""
    store = _store()
    with _state.lock:
        _state.refresh = refresh
        _state.to_show = None if store is not None else refresh
    os.environ[REFRESH_TOKEN] = refresh
    if store is not None:
        store.set(REFRESH_TOKEN, refresh)


async def finish(state: str, code: str) -> tuple[str, _Flow]:
    """Exchange Google's code for the tokens; returns where to send the browser, and the flow."""
    flow = _take_flow(state)
    body = await _token_request(
        {
            "code": code,
            "client_id": _env(CLIENT_ID),
            "client_secret": _env(CLIENT_SECRET),
            "redirect_uri": flow.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": flow.verifier,
        }
    )
    refresh = body.get("refresh_token")
    if not refresh:
        raise GoogleError("Google sent no refresh token: remove ÆHub from your Google account's apps and connect again.")
    granted = set(str(body.get("scope") or "").split())
    missing = [scope.rsplit("/", 1)[-1] for scope in SCOPES if granted and scope not in granted]
    _keep(str(refresh))
    with _state.lock:
        _state.access = body.get("access_token")
        _state.access_until = time.monotonic() + float(body.get("expires_in") or 0) - RENEW_MARGIN
        _state.account = None
    separator = "&" if "?" in flow.return_to else "?"
    outcome = "missing-" + "-".join(missing) if missing else "connected"
    return f"{flow.return_to}{separator}google={outcome}", flow


async def access_token() -> str:
    """A valid access token, renewed with the refresh token when needed."""
    with _state.lock:
        if _state.access and time.monotonic() < _state.access_until:
            return _state.access
    refresh = refresh_token()
    if not client_configured() or not refresh:
        raise GoogleNotConnected("Google is not connected: STRUMENTI → Google → Connect.")
    body = await _token_request(
        {
            "client_id": _env(CLIENT_ID),
            "client_secret": _env(CLIENT_SECRET),
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    )
    with _state.lock:
        _state.access = str(body["access_token"])
        _state.access_until = time.monotonic() + float(body.get("expires_in") or 0) - RENEW_MARGIN
        return _state.access


def take_token_to_show() -> Optional[str]:
    """The refresh token to show once (no keyring here), then never again."""
    with _state.lock:
        token, _state.to_show = _state.to_show, None
    return token


def remember_account(email: str) -> None:
    with _state.lock:
        _state.account = email


def account() -> Optional[str]:
    return _state.account


async def disconnect() -> None:
    """Revoke the token at Google and forget it here (and in the keyring)."""
    refresh = refresh_token()
    if refresh:
        try:
            async with http_client() as client:
                await client.post(REVOKE_URL, data={"token": refresh})
        except httpx.HTTPError:
            pass  # forgotten here all the same
    store = _store()
    if store is not None and hasattr(store, "delete"):
        try:
            store.delete(REFRESH_TOKEN)
        except Exception:  # noqa: BLE001 - nothing to delete is fine
            pass
    os.environ.pop(REFRESH_TOKEN, None)
    reset()


def reset_access() -> None:
    """Forget the access token: the next call renews it."""
    with _state.lock:
        _state.access = None
        _state.access_until = 0.0


def reset() -> None:
    """Forget everything in this process (disconnect, tests)."""
    with _state.lock:
        _state.flows.clear()
        _state.refresh = None
        _state.to_show = None
        _state.access = None
        _state.access_until = 0.0
        _state.account = None


__all__ = [
    "CALLBACK_PATH",
    "CLIENT_ID",
    "CLIENT_SECRET",
    "GoogleError",
    "GoogleNotConnected",
    "REFRESH_TOKEN",
    "SCOPES",
    "access_token",
    "account",
    "client_configured",
    "disconnect",
    "finish",
    "flow_of",
    "refresh_token",
    "remember_account",
    "reset",
    "reset_access",
    "start",
    "take_token_to_show",
    "token_source",
]
