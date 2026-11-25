"""
@file tests/security/test_frontend_api_routes.py
@description R1: every backend address the frontend calls is a real route.

The test reads the frontend sources and collects each `/api/...` address
written in them (string or template literal). An interpolated path segment,
such as `${encodeURIComponent(runId)}`, matches any route parameter; an
interpolation glued to the end, such as a query string, is dropped. The
address must match a route of the backend, and when the call is a direct
`getJson`, `postJson`, `postForm`, `putJson`, `deleteJson` or `fetchApi`
with the address written inline, the method must match too.

So a route renamed or removed on one side fails here, not in the browser.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from starlette.routing import Mount, WebSocketRoute

import main

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "frontend" / "src"

HELPER_METHODS = {
    "getJson": "GET",
    "postJson": "POST",
    "postForm": "POST",
    "putJson": "PUT",
    "deleteJson": "DELETE",
}

# An address starts with /api/, or with a constant of the file (`${path}/events`).
_START = r"(?:/api/|\$\{\w+\}/)"
_LITERAL = re.compile(r"""(["`])(""" + _START + r"""[^"`]*)\1""")
_CALL = re.compile(
    r"""\b(getJson|postJson|postForm|putJson|deleteJson|fetchApi)\s*(?:<[^()]*?>)?\(\s*(["`])("""
    + _START
    + r"""[^"`]*)\2"""
)
_METHOD_OPTION = re.compile(r"""method:\s*["']([A-Z]+)["']""")
_CONSTANT = re.compile(r"""\bconst\s+(\w+)\s*=\s*(["`])(/api/[^"`]*)\2""")
_INTERPOLATION = re.compile(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def _sources() -> Iterator[Tuple[Path, str]]:
    for path in sorted(SOURCES.rglob("*")):
        if path.suffix in (".ts", ".tsx"):
            text = path.read_text(encoding="utf-8")
            yield path, _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _routes() -> Dict[str, Set[str]]:
    """Route path -> methods, with included routers flattened."""
    routes: Dict[str, Set[str]] = {}

    def walk(items, prefix: str = "") -> None:
        for route in items:
            included = getattr(route, "original_router", None)

            if included is not None:
                context = getattr(route, "include_context", None)
                walk(included.routes, prefix + getattr(context, "prefix", ""))
            elif isinstance(route, Mount):
                continue
            elif isinstance(route, WebSocketRoute):
                routes.setdefault(prefix + route.path, set()).add("WS")
            else:
                routes.setdefault(prefix + route.path, set()).update(route.methods - {"HEAD"})

    walk(main.app.routes)
    return routes


def _normalize(address: str, constants: Dict[str, str]) -> str:
    """
    The address as a path pattern: `{}` for an interpolated segment, no
    query string, no interpolation glued to the end.
    """

    def substitute(match: re.Match) -> str:
        name = match.group(1).strip()
        return constants.get(name, "${" + name + "}")

    # A constant of the same file (`${path}/events`) is replaced by its value.
    address = _INTERPOLATION.sub(substitute, address)
    address = address.split("?", 1)[0]
    segments: List[str] = []

    for segment in address.split("/"):
        if _INTERPOLATION.fullmatch(segment):
            segments.append("{}")
        else:
            segments.append(_INTERPOLATION.sub("", segment))

    return "/".join(segments).rstrip("/") or "/"


def _pattern(route: str) -> re.Pattern:
    parts = [
        "[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in route.split("/")
    ]
    return re.compile("^" + "/".join(parts) + "$")


def _matching(address: str, routes: Dict[str, Set[str]]) -> Optional[Set[str]]:
    probe = address.replace("{}", "x")
    methods: Set[str] = set()
    found = False

    for route, route_methods in routes.items():
        if _pattern(route).match(probe):
            found = True
            methods |= route_methods

    return methods if found else None


def _addresses() -> List[Tuple[str, str, Optional[str]]]:
    """(file, normalized address, method or None) for each address written."""
    found: List[Tuple[str, str, Optional[str]]] = []

    for path, text in _sources():
        name = str(path.relative_to(REPO))
        constants = {match.group(1): match.group(3) for match in _CONSTANT.finditer(text)}
        inline: Set[int] = set()

        for match in _CALL.finditer(text):
            helper = match.group(1)
            method = HELPER_METHODS.get(helper)

            if helper == "fetchApi":
                window = text[match.end() : match.end() + 400]
                option = _METHOD_OPTION.search(window.split(");", 1)[0])
                method = option.group(1) if option else "GET"

            inline.add(match.start(3))
            found.append((name, _normalize(match.group(3), constants), method))

        for match in _LITERAL.finditer(text):
            if match.start(2) not in inline:
                found.append((name, _normalize(match.group(2), constants), None))

    # A template that starts with something other than a known constant.
    found = [entry for entry in found if entry[1].startswith("/api/")]

    return found


def test_the_frontend_calls_addresses():
    # Guards the parser: if it stops finding calls, the other tests pass empty.
    addresses = _addresses()
    assert len(addresses) > 50
    assert sum(1 for _, _, method in addresses if method) > 40


def test_every_address_the_frontend_calls_is_a_route():
    routes = _routes()
    missing = sorted(
        {f"{name}: {address}" for name, address, _ in _addresses() if _matching(address, routes) is None}
    )
    assert not missing, f"The frontend calls addresses the backend does not serve: {missing}"


def test_every_direct_call_uses_a_method_of_its_route():
    routes = _routes()
    wrong = []

    for name, address, method in _addresses():
        methods = _matching(address, routes)

        if method and methods is not None and method not in methods:
            wrong.append(f"{name}: {method} {address} (the route takes {sorted(methods)})")

    assert not wrong, f"The frontend calls routes with a method they do not take: {sorted(set(wrong))}"


def test_the_normalization():
    assert _normalize("/api/runs/${encodeURIComponent(runId)}/cancel", {}) == "/api/runs/{}/cancel"
    assert _normalize("/api/system/events${recorderQuery(filters)}", {}) == "/api/system/events"
    assert _normalize("/api/events?scope=workspace", {}) == "/api/events"
    assert _normalize("${path}/events", {"path": "/api/runs/${id}"}) == "/api/runs/{}/events"
