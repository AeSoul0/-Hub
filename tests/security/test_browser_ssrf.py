"""
@file tests/security/test_browser_ssrf.py
@description The browser skill checks every request of the page against SSRF, not only the first URL.

Two local servers stand in for the internet: 127.0.0.1 plays a public site
(the test marks it safe) and 127.0.0.2 an address on the user's network. The
public page redirects and links to the private one; the private server must
never be reached.
"""

import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.ssrf_protector import SSRFProtector
from app.skills import browser_skill


class _Recorder(BaseHTTPRequestHandler):
    hits: list = []
    private_port = 0

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def do_GET(self) -> None:
        type(self).hits.append(self.path)
        if self.path == "/hop":
            self.send_response(302)
            self.send_header("Location", "/go")
            self.end_headers()
            return
        if self.path == "/go":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.2:{type(self).private_port}/secret")
            self.end_headers()
            return
        body = (
            "<html><body><p>public page</p>"
            f'<img src="http://127.0.0.2:{type(self).private_port}/pixel">'
            f"<script>fetch('http://127.0.0.2:{type(self).private_port}/fetch')</script>"
            "</body></html>"
            if self.path == "/page"
            else "<html><body>private secret</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)


def _serve(host: str, handler: type) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def sites(monkeypatch):
    public_handler = type("Public", (_Recorder,), {"hits": []})
    private_handler = type("Private", (_Recorder,), {"hits": []})
    private = _serve("127.0.0.2", private_handler)
    public_handler.private_port = private.server_address[1]
    public = _serve("127.0.0.1", public_handler)
    # Only 127.0.0.1 counts as public for this test.
    monkeypatch.setattr(SSRFProtector, "is_safe_ip", staticmethod(lambda ip: ip == "127.0.0.1"))
    yield f"http://127.0.0.1:{public.server_address[1]}", public_handler, private_handler
    public.shutdown()
    private.shutdown()


def test_private_addresses_are_refused_and_local_schemes_allowed(monkeypatch):
    monkeypatch.setattr(SSRFProtector, "is_safe_ip", staticmethod(lambda ip: ip == "127.0.0.1"))

    assert asyncio.run(browser_skill.is_allowed_request("http://127.0.0.1:8000/")) is True
    assert asyncio.run(browser_skill.is_allowed_request("http://127.0.0.2:8000/")) is False
    assert asyncio.run(browser_skill.is_allowed_request("file:///etc/passwd")) is False
    assert asyncio.run(browser_skill.is_allowed_request("data:text/plain,hi")) is True


def test_route_handler_refuses_a_private_request_or_redirect(monkeypatch):
    monkeypatch.setattr(SSRFProtector, "is_safe_ip", staticmethod(lambda ip: ip == "127.0.0.1"))
    calls = []

    class Response:
        def __init__(self, status, location=None):
            self.status = status
            self.headers = {"location": location} if location else {}

    # What each address answers: a status, and where it redirects.
    site = {
        "http://127.0.0.1/a": Response(200),
        "http://127.0.0.1/c": Response(302, "/d"),
        "http://127.0.0.1/d": Response(200),
        "http://127.0.0.1/e": Response(302, "/c"),
        "http://127.0.0.1/g": Response(302, "http://127.0.0.2/f"),
        "http://127.0.0.1/loop": Response(302, "/loop"),
    }

    class Route:
        def __init__(self, url):
            self.request = type("Request", (), {"url": url})()

        async def continue_(self):
            calls.append(("continue", self.request.url))

        async def fetch(self, url, max_redirects):
            assert max_redirects == 0
            calls.append(("fetch", url))
            return site[url]

        async def fulfill(self, response):
            calls.append(("fulfill", self.request.url))

        async def abort(self, reason):
            calls.append(("abort", self.request.url))

    def run(url):
        calls.clear()
        asyncio.run(browser_skill.guard_request(Route(url)))
        return list(calls)

    assert run("http://127.0.0.1/a") == [("fetch", "http://127.0.0.1/a"), ("fulfill", "http://127.0.0.1/a")]
    assert run("http://127.0.0.2/b") == [("abort", "http://127.0.0.2/b")]
    # Two public hops are followed and checked, then the final page is handed over.
    assert run("http://127.0.0.1/e") == [
        ("fetch", "http://127.0.0.1/e"),
        ("fetch", "http://127.0.0.1/c"),
        ("fetch", "http://127.0.0.1/d"),
        ("fulfill", "http://127.0.0.1/e"),
    ]
    # A hop to a private address is refused before it is fetched.
    assert run("http://127.0.0.1/g") == [("fetch", "http://127.0.0.1/g"), ("abort", "http://127.0.0.1/g")]
    assert run("http://127.0.0.1/loop")[-1] == ("abort", "http://127.0.0.1/loop")
    assert run("data:text/plain,hi") == [("continue", "data:text/plain,hi")]


def _chromium_or_skip():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch(headless=True).close()
    except Exception as exc:  # noqa: BLE001 - any launch failure means no browser here
        # The CI browser step installs Chromium and must run this test.
        if os.getenv("AEHUB_BROWSER_SMOKE") == "1":
            raise
        pytest.skip(f"Chromium is not available: {exc}")


def test_a_public_page_cannot_reach_a_private_address(sites):
    _chromium_or_skip()
    base, public, private = sites

    text = asyncio.run(browser_skill.browse_and_extract(f"{base}/page"))
    assert "public page" in text

    redirected = asyncio.run(browser_skill.browse_and_extract(f"{base}/go"))
    assert "private secret" not in redirected

    # A public redirect is allowed; the hop after it is checked again.
    chained = asyncio.run(browser_skill.browse_and_extract(f"{base}/hop"))
    assert "private secret" not in chained

    assert {"/page", "/go", "/hop"} <= set(public.hits)
    assert private.hits == []


def test_an_image_built_without_the_browser_offers_no_browser_tool(monkeypatch):
    """N8 (ADR-039): Chromium is in the Docker image only with AEHUB_BROWSER=1."""
    skill = browser_skill.BrowserSkill()
    monkeypatch.setenv("AEHUB_IN_CONTAINER", "1")
    monkeypatch.setenv("AEHUB_BROWSER", "0")
    assert skill.tools == [] and skill.get_tool_metadata() == {}
    monkeypatch.setenv("AEHUB_BROWSER", "1")
    assert list(skill.get_tool_metadata()) == ["browse_and_extract"]
    # Outside a container (desktop, codespace) the browser is the one installed there.
    monkeypatch.delenv("AEHUB_IN_CONTAINER")
    monkeypatch.setenv("AEHUB_BROWSER", "0")
    assert skill.tools == [browser_skill.browse_and_extract]
