"""
@file backend/app/core/security_middleware.py
@description Implements security_middleware.py. Core components: AdvancedSecurityMiddleware.

This module manages the internal business logic for AdvancedSecurityMiddleware.
It provides specialized functionality to handle: dispatch.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.agent_engine.guardrails import contains_secret
import urllib.parse

class AdvancedSecurityMiddleware(BaseHTTPMiddleware):
    """
    Represents the AdvancedSecurityMiddleware entity and its core operations.
    """
    """
    M1 Security & M16 Gates.
    Enforces SSRF defense, Path Traversal defense, and injects strict Security Headers.
    """
    async def dispatch(self, request: Request, call_next):
        """
        Executes dispatch logic.
        """
        # Inspect raw URL paths to detect and block Path Traversal attempts
        # Inspect raw URL paths to detect and block Path Traversal attempts
        
        # 1. Path Traversal Defense
        raw_path = urllib.parse.unquote(request.url.path)
        if ".." in raw_path or "//" in raw_path:
            return JSONResponse(status_code=400, content={"detail": "Path Traversal detected and blocked."})

        # 2. SSRF is enforced where URLs are actually fetched: the ToolGateway
        # validates every network-tool URL with SSRFProtector (DNS-resolved,
        # all addresses checked). A substring match on the query string here
        # only produced false positives.

        # 3. Secrets must travel in headers, never in URLs (they end up in logs).
        query_str = urllib.parse.unquote(str(request.query_params))
        if contains_secret(query_str):
            return JSONResponse(status_code=400, content={"detail": "Secret Redaction: Tokens must be passed in Auth headers, not URLs."})

        # Execute Request
        response = await call_next(request)
        
        # 4. Strict Security Headers
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self)"

        return response
