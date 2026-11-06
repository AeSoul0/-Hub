"""
@file backend/app/system/access_key.py
@description Rotation of the Control Plane access key (F9, ADR-030).

The key (AEHUB_SECRET_KEY) opens a session from a browser; the desktop app
signs in with its own one-time launch link and never needs it. A rotation:
1. writes a new random key to the OS keyring, so a restart keeps it;
2. makes login check the new key at once;
3. closes every other session, so whoever signed in with the old key is
   signed out; the caller's own session stays open.

Without the keyring (a server started from the environment) the key cannot
be saved here, and the rotation is refused rather than lost at the next
restart.
"""

from __future__ import annotations

import secrets
from typing import Optional, Tuple

from app.core.config import settings
from app.core.security import hash_session_token
from app.desktop.launch import desktop_mode, secret_store
from app.domain.models.identity import Session as SessionModel

KEY_NAME = "AEHUB_SECRET_KEY"


class KeyStoreUnavailable(RuntimeError):
    pass


def can_rotate() -> bool:
    return desktop_mode() and secret_store() is not None


def rotate(db, keep_session_token: Optional[str]) -> Tuple[str, int]:
    """
    The new key and how many sessions were closed.
    """
    store = secret_store()

    if not desktop_mode() or store is None:
        raise KeyStoreUnavailable(
            "The key is set in the environment: change AEHUB_SECRET_KEY where it is set and restart."
        )

    key = secrets.token_urlsafe(32)
    store.set(KEY_NAME, key)
    settings.AEHUB_SECRET_KEY = key

    sessions = db.query(SessionModel)

    if keep_session_token:
        sessions = sessions.filter(SessionModel.id != hash_session_token(keep_session_token))

    closed = sessions.delete(synchronize_session=False)
    db.commit()

    return key, int(closed)


__all__ = ["KEY_NAME", "KeyStoreUnavailable", "can_rotate", "rotate"]
