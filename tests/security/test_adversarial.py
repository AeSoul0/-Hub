"""
@file tests/security/test_adversarial.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestSecurityMiddleware:
    """M16 Security Gate: Advanced Defenses."""
    
    def test_ssrf_defense(self):
        """M1: Test that SSRF attempts via URLs containing local IPs are blocked."""
        # Attempt to reach AWS metadata IP or localhost
        response = client.get("/api/v1/tools/execute?url=http://169.254.169.254/latest/meta-data")
        assert response.status_code == 403
        assert response.json().get("detail") == "SSRF attempt detected and blocked."
        
        response2 = client.get("/api/v1/tools/execute?url=http://localhost:8080/admin")
        assert response2.status_code == 403

    def test_path_traversal_defense(self):
        """M1: Test that directory traversal attempts are blocked."""
        response = client.get("/api/v1/workspace/files?path=../../../etc/passwd")
        assert response.status_code == 400
        assert "Path Traversal detected" in response.json().get("detail", "")
        
    def test_secret_redaction(self):
        """M16: Test that explicit tokens in URLs are blocked (Secret Redaction)."""
        response = client.get("/api/v1/workspace/files?token=sk-12345ABCD")
        assert response.status_code == 400
        assert "Secret Redaction" in response.json().get("detail", "")
        
    def test_security_headers_injected(self):
        """M1: Test that strict security headers are appended to responses."""
        response = client.get("/docs") # generic endpoint
        headers = response.headers
        assert "Content-Security-Policy" in headers
        assert "X-Frame-Options" in headers
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
