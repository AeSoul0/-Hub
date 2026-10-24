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
    approvals,
    audit,
    auth,
    desktop,
    documents,
    memory,
    realtime,
    runs,
    settings as settings_api,
)
from app.core.telemetry import (
    setup_telemetry,
    shutdown_telemetry,
)
from app.core.settings_service import load_settings, log_configuration_issues
from app.skills.registry import skill_registry


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
    Initialize shared persistence and telemetry instrumentation: pgvector
    and every SQLAlchemy table (the only persistence layer since M15).
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

    # Settings edited from the Control Plane win over the environment (M12).
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        load_settings(db)

    # One line per problem (Critic equal to a Worker, missing provider key,
    # missing prices, ...). The API still starts, so the Settings page can
    # fix what it can; the engine refuses runs while routing is invalid.
    log_configuration_issues()

    try:
        yield

    finally:
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

        # The HttpOnly session cookie is the only credential, as in
        # resolve_session: a Bearer header would pass here and then be
        # rejected by every route.
        session_token = request.cookies.get(
            "aehub_session_token"
        )

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


from app.core.security import allowed_origins
from app.core.security_middleware import AdvancedSecurityMiddleware


app.add_middleware(
    AdvancedSecurityMiddleware
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
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


@app.middleware("http")
async def check_host_and_origin(
    request: Request,
    call_next,
):
    """
    Loopback hardening (spec 5.3, ADR-020), outermost: answer only to our
    host names (DNS rebinding) and refuse state-changing requests from pages
    of other origins, which would carry the owner's cookie.
    """
    from app.core.security import is_cross_origin_write, is_host_allowed

    if not is_host_allowed(
        request.headers.get("host")
    ):
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Host not allowed. Add it to AEHUB_ALLOWED_HOSTS "
                    "to serve the API under that name."
                )
            },
        )

    if is_cross_origin_write(
        request.method,
        request.headers.get("origin"),
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Cross-origin request refused."
            },
        )

    return await call_next(
        request
    )


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
    orchestrator.router
)

app.include_router(
    realtime.router
)

app.include_router(
    approvals.router
)

app.include_router(
    runs.router
)

app.include_router(
    memory.router
)

app.include_router(
    documents.router
)

app.include_router(
    audit.router
)

app.include_router(
    settings_api.router
)

app.include_router(
    desktop.router
)


# ==============================================================================
# STATIC FRONTEND (desktop app, ADR-020)
# ==============================================================================


# The exported frontend, served from the API's own origin: no CORS, and the
# session cookie reaches every request. Mounted last, so API routes win.
_frontend_dir = os.getenv(
    "AEHUB_FRONTEND_DIR",
    "",
)

if _frontend_dir and os.path.isdir(_frontend_dir):
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/",
        StaticFiles(
            directory=_frontend_dir,
            html=True,
        ),
        name="frontend",
    )


# ==============================================================================
# LOCAL DEVELOPMENT ENTRYPOINT
# ==============================================================================


if __name__ == "__main__":
    import uvicorn

    # Loopback by default: exposing the API on the network is an explicit
    # choice (AEHUB_HOST=0.0.0.0), as in the container image.
    uvicorn.run(
        "main:app",
        host=os.getenv(
            "AEHUB_HOST",
            "127.0.0.1",
        ),
        port=3002,
        reload=True,
    )