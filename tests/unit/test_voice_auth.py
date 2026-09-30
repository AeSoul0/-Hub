"""
@file tests/unit/test_voice_auth.py
@description Unit tests for voice-session identity binding.

These tests ensure that the voice layer preserves the authenticated role and
workspace and never manufactures a default tenant context.
"""

from types import SimpleNamespace

from app.api.voice import (
    _new_voice_session_id,
    _principal_from_session,
)
from app.core.security import RoleEnum


def test_voice_principal_preserves_session_identity() -> None:
    """
    The runtime Principal must exactly inherit identity boundaries from the
    authenticated persistence session.
    """
    session = SimpleNamespace(
        user_id="user-123",
        workspace_id="workspace-456",
        role=RoleEnum.ADMIN,
    )

    principal = _principal_from_session(session)

    assert principal is not None
    assert principal.id == "user-123"
    assert principal.workspace_id == "workspace-456"
    assert principal.role is RoleEnum.ADMIN


def test_voice_principal_accepts_string_role() -> None:
    """
    Persisted string roles must be converted to the canonical RoleEnum.
    """
    session = SimpleNamespace(
        user_id="user-1",
        workspace_id="workspace-1",
        role="user",
    )

    principal = _principal_from_session(session)

    assert principal is not None
    assert principal.role is RoleEnum.USER


def test_voice_principal_rejects_missing_workspace() -> None:
    """
    Missing tenant context must fail closed.
    """
    session = SimpleNamespace(
        user_id="user-1",
        workspace_id=None,
        role=RoleEnum.USER,
    )

    assert _principal_from_session(session) is None


def test_voice_principal_rejects_invalid_role() -> None:
    """
    Unknown persisted roles must never be converted into a default role.
    """
    session = SimpleNamespace(
        user_id="user-1",
        workspace_id="workspace-1",
        role="unknown-role",
    )

    assert _principal_from_session(session) is None


def test_voice_session_ids_are_unique() -> None:
    """
    Every voice connection must receive an isolated runtime session ID.
    """
    first = _new_voice_session_id()
    second = _new_voice_session_id()

    assert first.startswith("voice-")
    assert second.startswith("voice-")
    assert first != second