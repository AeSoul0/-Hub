"""
@file backend/main.py
@description FastAPI application composition root for ÆHub.

The entrypoint is intentionally limited to application bootstrap concerns:
configuration, lifecycle initialization, global middleware, and router
registration. Feature-specific transport handlers live under app.api, while
the Agent Engine remains independent from this module.

Security invariants:
- Protected HTTP API routes require a valid persistent session.
- WebSocket authentication is enforced by the realtime transport module.
- Client-supplied session identifiers are never trusted as identity authorities.
- Workspace identity is derived from the authenticated server-side session.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents import orchestrator
from app.api import (
    academic,
    auth,
    media,
    realtime,
    voice,
)
from app.core import database
from app.core.telemetry import (
    setup_telemetry,
    shutdown_telemetry,
)
from app.skills.registry import skill_registry
from app.workers.scheduler import proactive_scheduler
from app.workflows.autonomous import register_workflows


# ==============================================================================
# APPLICATION CONFIGURATION
# ==============================================================================


load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from app.core.config import settings


AEHUB_SECRET_KEY = settings.AEHUB_SECRET_KEY

if (
    not AEHUB_SECRET_KEY
    or AEHUB_SECRET_KEY == "default-unsafe-key"
):
    print(
        "[CRITICAL] AEHUB_SECRET_KEY is not configured securely. "
        "Application startup aborted."
    )

    sys.exit(1)


# ==============================================================================
# DATABASE AND RUNTIME STARTUP
# ==============================================================================


def startup_db():
    """
    Initialize shared persistence, telemetry instrumentation, workflows, and
    the proactive scheduler.

    This function remains in the composition root for compatibility with the
    current test suite. Database-layer consolidation will move the remaining
    compatibility initialization out of this entrypoint in a later phase.
    """
    from sqlalchemy import text

    from app.core.db import engine
    from app.core.telemetry import instrument_sqlalchemy
    from app.domain.models import Base

    instrument_sqlalchemy(
        engine
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE EXTENSION IF NOT EXISTS vector"
            )
        )

    Base.metadata.create_all(
        bind=engine
    )

    database.init_db()
    register_workflows()
    proactive_scheduler.start()

    print(
        "[OK] Centralized PostgreSQL database schema initialized."
    )


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    Start and stop application-wide resources for the FastAPI process.
    """
    del app

    startup_db()

    # Skill modules import heavy dependencies (vision, browser), so discovery
    # runs off the event loop. Without it the agent has no tools to call.
    if not skill_registry.get_registered_skill_names():
        await asyncio.to_thread(
            skill_registry.load_from_package
        )

    try:
        yield

    finally:
        proactive_scheduler.stop()
        shutdown_telemetry()


app = FastAPI(
    title="AeSouls Hub API Server",
    lifespan=lifespan,
)

setup_telemetry(
    app
)


# ==============================================================================
# GLOBAL HTTP AUTHENTICATION
# ==============================================================================


@app.middleware("http")
async def verify_api_key(
    request: Request,
    call_next,
):
    """
    Validate the persistent authenticated session for protected API traffic.

    The session is resolved server-side. No arbitrary client identifier is
    accepted as an authentication authority.
    """
    if request.method == "OPTIONS":
        return await call_next(
            request
        )

    protected_api_path = (
        request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/auth/")
    )

    if protected_api_path:
        from app.core.cache import CacheService
        from app.core.db import SessionLocal
        from app.core.security import IdentityService

        auth_header = request.headers.get(
            "Authorization"
        )

        cookie_token = request.cookies.get(
            "aehub_session_token"
        )

        session_token = cookie_token

        if (
            auth_header
            and auth_header.startswith("Bearer ")
        ):
            session_token = auth_header.split(
                " ",
                1,
            )[1]

        with SessionLocal() as db:
            session = (
                IdentityService.validate_session(
                    db,
                    session_token,
                )
                if session_token
                else None
            )

            if not session:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": (
                            "Unauthorized access. "
                            "Invalid or missing session."
                        )
                    },
                )

            path = request.url.path

            limit = 60
            window = 60
            limit_key = "api"

            if (
                path.startswith(
                    "/api/orchestrator/listen"
                )
                or "upload" in path
            ):
                limit = 10
                window = 60
                limit_key = "upload"

            elif path.startswith(
                "/api/orchestrator/ask"
            ):
                limit = 20
                window = 60
                limit_key = "llm"

            is_allowed = (
                await CacheService.check_rate_limit(
                    identifier=(
                        f"{limit_key}:{session.user_id}"
                    ),
                    limit=limit,
                    window_seconds=window,
                )
            )

            if not is_allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "Too Many Requests. "
                            "Rate limit exceeded."
                        )
                    },
                )

    return await call_next(
        request
    )


# ==============================================================================
# GLOBAL SECURITY MIDDLEWARE
# ==============================================================================


from app.core.security_middleware import AdvancedSecurityMiddleware


app.add_middleware(
    AdvancedSecurityMiddleware
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv(
            "FRONTEND_URL",
            "http://localhost:3000",
        )
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    """
    Add browser-facing response security headers.
    """
    response = await call_next(
        request
    )

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Strict-Transport-Security"
    ] = (
        "max-age=31536000; includeSubDomains"
    )

    return response


# ==============================================================================
# HEALTH CHECK
# ==============================================================================


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Return the application health status used by container probes.
    """
    return {
        "status": "ok",
    }


# ==============================================================================
# FEATURE ROUTER REGISTRATION
# ==============================================================================


app.include_router(
    auth.router
)

app.include_router(
    media.router
)

app.include_router(
    academic.router
)

app.include_router(
    voice.router
)

app.include_router(
    orchestrator.router
)

app.include_router(
    realtime.router
)


# ==============================================================================
# LOCAL DEVELOPMENT ENTRYPOINT
# ==============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3002,
        reload=True,
    )