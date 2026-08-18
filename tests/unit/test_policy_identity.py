"""
@file tests/unit/test_policy_identity.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import pytest
from app.core.security import Principal, IdentityService
from fastapi import HTTPException

def test_principal_instantiation():
    """M2: Verify Principal schema and role enforcement."""
    user = Principal(id="usr-123", roles=["user", "researcher"], workspace_id="ws-99")
    assert "user" in user.roles
    assert user.workspace_id == "ws-99"

def test_identity_service_rbac_allow():
    """M2: Verify IdentityService allows access for correct roles."""
    user = Principal(id="usr-1", roles=["admin"], workspace_id="ws-1")
    # Should not raise exception
    IdentityService.verify_access(user, required_role="admin")

def test_identity_service_rbac_deny():
    """M2: Verify IdentityService denies access for insufficient roles."""
    user = Principal(id="usr-2", roles=["viewer"], workspace_id="ws-1")
    with pytest.raises(HTTPException) as exc:
        IdentityService.verify_access(user, required_role="admin")
    assert exc.value.status_code == 403

def test_workspace_isolation():
    """M2: Verify cross-workspace access is mathematically denied."""
    user = Principal(id="usr-3", roles=["admin"], workspace_id="ws-A")
    with pytest.raises(HTTPException) as exc:
        IdentityService.enforce_workspace(user, target_workspace="ws-B")
    assert exc.value.status_code == 403
