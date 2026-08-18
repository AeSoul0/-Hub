"""
@file backend/tests/test_auth.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

def test_auth_login_success():
    os.environ["AEHUB_SECRET_KEY"] = "test-key"
    response = client.post("/api/auth/login", json={"key": "test-key"})
    assert response.status_code == 200
    assert "aehub_auth_token" in response.cookies

def test_auth_login_failure():
    os.environ["AEHUB_SECRET_KEY"] = "test-key"
    response = client.post("/api/auth/login", json={"key": "wrong-key"})
    assert response.status_code == 401
    
def test_protected_route_without_auth():
    # Attempting to access an endpoint protected by middleware without a cookie or header
    response = client.get("/api/academic/status")
    assert response.status_code == 401
