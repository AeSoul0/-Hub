"""
@file tests/security/test_api_surface.py
@description M10 exit test: the API exposes exactly the expected routes.

Every capability of the assistant runs as an agent tool through the Tool
Gateway (policy, approvals, provenance, audit). The only routes that start
work are the ones that hand a request to the agent engine; the rest manage
sessions, approvals, runs and memory. A new route that acts on its own (as
`/api/media/download` and `/api/academic/sync` did before M10) fails this test
until it is reviewed and added here on purpose.
"""

from __future__ import annotations

from starlette.routing import Mount, WebSocketRoute

import main


# Routes that hand the request to the agent engine (and so to the Gateway).
AGENT_ENTRYPOINTS = {
    ("POST", "/api/orchestrator/ask"),
    ("POST", "/api/orchestrator/listen"),
    ("WS", "/ws/orchestrator"),
}

# Session, control-plane and observability routes: they never run a tool.
MANAGEMENT = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/verify"),
    ("GET", "/api/approvals"),
    ("POST", "/api/approvals/{approval_id}"),
    ("GET", "/api/runs/live"),
    ("GET", "/api/runs/stats"),
    ("POST", "/api/runs/resume"),
    ("POST", "/api/runs/stop-all"),
    ("POST", "/api/runs/{run_id}/cancel"),
    ("GET", "/api/runs/{run_id}"),
    # F2: run history and timeline, read only.
    ("GET", "/api/runs"),
    ("GET", "/api/runs/{run_id}/events"),
    ("GET", "/api/audit"),
    # M12: settings change routing, prices and limits, never tools or secrets.
    ("GET", "/api/settings"),
    ("PUT", "/api/settings"),
    ("POST", "/api/settings/onboarding"),
    ("GET", "/api/memory"),
    ("POST", "/api/memory/preferences"),
    ("DELETE", "/api/memory/{memory_id}"),
    # M13: the document index of the working folder; search is a tool.
    ("GET", "/api/documents"),
    ("POST", "/api/documents/sync"),
    # M14: the desktop app's launch token and provider keys into the keyring.
    ("GET", "/desktop/launch/{token}"),
    ("GET", "/api/desktop"),
    ("PUT", "/api/desktop/secrets"),
    # F3: voice status, the ElevenLabs voice list and speaking a reply.
    ("GET", "/api/voice"),
    ("GET", "/api/voice/elevenlabs/voices"),
    ("POST", "/api/voice/speak"),
    ("GET", "/api/events"),
    ("GET", "/health"),
    ("MOUNT", "/metrics"),
}

# FastAPI's generated documentation.
DOCS = {
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
}


def _walk(routes, prefix: str = ""):
    for route in routes:
        # Newer FastAPI keeps each included router as one branch instead of
        # copying its routes into the app; descend into it.
        included = getattr(route, "original_router", None)

        if included is not None:
            context = getattr(route, "include_context", None)
            yield from _walk(included.routes, prefix + getattr(context, "prefix", ""))
        elif isinstance(route, Mount):
            yield ("MOUNT", prefix + route.path)
        elif isinstance(route, WebSocketRoute):
            yield ("WS", prefix + route.path)
        else:
            for method in route.methods - {"HEAD"}:
                yield (method, prefix + route.path)


def _surface():
    return set(_walk(main.app.routes))


def test_api_surface_is_exactly_the_reviewed_one():
    surface = _surface()

    assert surface - (AGENT_ENTRYPOINTS | MANAGEMENT | DOCS) == set(), (
        "Unreviewed route: does it reach a capability without the Tool Gateway?"
    )
    assert (AGENT_ENTRYPOINTS | MANAGEMENT | DOCS) - surface == set()


def test_removed_capabilities_stay_removed():
    paths = {path for _, path in _surface()}

    # ADR-019 removed the second audio input /api/voice/stream: speech still
    # comes in only through /api/orchestrator/listen and the WebSocket. The
    # F3 /api/voice routes take no audio and start no run (ADR-024).
    for prefix in ("/api/media", "/api/academic", "/api/voice/stream"):
        assert not any(path.startswith(prefix) for path in paths), prefix
