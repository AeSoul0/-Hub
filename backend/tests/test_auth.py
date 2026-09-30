"""
@file backend/tests/test_auth.py
@description Core module for A.U.R.O.R.A. System

Implements core logic and architectural definitions.
"""

import os
os.environ["GROQ_API_KEY"] = "mock_key"
os.environ["POSTGRES_URL"] = "sqlite:///./aehub.db"
from unittest.mock import patch

patch('main.startup_db').start()
patch('app.core.cache.CacheService.check_rate_limit', return_value=True).start()

from fastapi.testclient import TestClient
from main import app, AEHUB_SECRET_KEY
from app.core.db import get_db
from unittest.mock import MagicMock

def mock_get_db():
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "admin"
    mock_workspace = MagicMock()
    mock_workspace.id = "default"
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_workspace]
    yield mock_db

app.dependency_overrides[get_db] = mock_get_db

client = TestClient(app)

def test_auth_login_success():
    response = client.post("/api/auth/login", json={"key": AEHUB_SECRET_KEY})
    assert response.status_code == 200
    assert "aehub_session_token" in response.cookies

def test_auth_login_failure():
    response = client.post("/api/auth/login", json={"key": "wrong-key"})
    assert response.status_code == 401
    
def test_protected_route_without_auth():
    # Attempting to access an endpoint protected by middleware without a cookie or header
    client.cookies.clear()
    response = client.get("/api/academic/status")
    assert response.status_code == 401
