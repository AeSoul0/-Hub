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
    ("GET", "/api/memory"),
    ("POST", "/api/memory/preferences"),
    ("DELETE", "/api/memory/{memory_id}"),
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


def _surface():
    surface = set()

    for route in main.app.routes:
        if isinstance(route, Mount):
            surface.add(("MOUNT", route.path))
        elif isinstance(route, WebSocketRoute):
            surface.add(("WS", route.path))
        else:
            for method in route.methods - {"HEAD"}:
                surface.add((method, route.path))

    return surface


def test_api_surface_is_exactly_the_reviewed_one():
    surface = _surface()

    assert surface - (AGENT_ENTRYPOINTS | MANAGEMENT | DOCS) == set(), (
        "Unreviewed route: does it reach a capability without the Tool Gateway?"
    )
    assert (AGENT_ENTRYPOINTS | MANAGEMENT | DOCS) - surface == set()


def test_removed_capabilities_stay_removed():
    paths = {path for _, path in _surface()}

    for prefix in ("/api/media", "/api/academic", "/api/voice"):
        assert not any(path.startswith(prefix) for path in paths), prefix
