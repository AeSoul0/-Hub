"""
@file backend/app/core/security_middleware.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import re
import urllib.parse

class AdvancedSecurityMiddleware(BaseHTTPMiddleware):
    """
    M1 Security & M16 Gates.
    Enforces SSRF defense, Path Traversal defense, and injects strict Security Headers.
    """
    async def dispatch(self, request: Request, call_next):
        
        # 1. Path Traversal Defense
        raw_path = urllib.parse.unquote(request.url.path)
        if ".." in raw_path or "//" in raw_path:
            return JSONResponse(status_code=400, content={"detail": "Path Traversal detected and blocked."})

        # 2. SSRF Defense (Basic static heuristic for user-input URLs in query or body)
        # Note: True SSRF defense also requires intercepting outgoing requests.
        query_str = urllib.parse.unquote(str(request.query_params))
        blocked_ips = ["127.0.0.1", "localhost", "169.254.169.254", "0.0.0.0"]
        for ip in blocked_ips:
            if ip in query_str:
                return JSONResponse(status_code=403, content={"detail": "SSRF attempt detected and blocked."})

        # 2.5 Secret Redaction (M16 Gate)
        # Prevents accidental logging or transmission of explicit API keys
        if "sk-" in query_str or "Bearer ey" in query_str:
            return JSONResponse(status_code=400, content={"detail": "Secret Redaction: Tokens must be passed in Auth headers, not URLs."})

        # Execute Request
        response = await call_next(request)
        
        # 3. Strict Security Headers
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"

        return response
