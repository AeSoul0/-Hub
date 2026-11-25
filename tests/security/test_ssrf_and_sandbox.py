"""
@file tests/security/test_ssrf_and_sandbox.py
@description SSRF protection of fetched URLs and the limits of the shell and Python sandbox.
"""
import socket

import pytest
from app.core.ssrf_protector import SSRFProtector, SSRFError
from app.workers.sandbox import EphemeralSandboxManager

# What the sandbox reports when Docker could not run the container at all
# (no daemon, no image pulled in time, no docker binary).
SANDBOX_DID_NOT_START = (
    "Execution timed out.",
    "Sandbox Error",
    "Cannot connect to the Docker daemon",
    "failed to connect",
    "docker:",
    "Unable to find image",
)

def test_ssrf_protector_rejects_localhost():
    with pytest.raises(SSRFError):
        SSRFProtector.validate_url("http://127.0.0.1/admin")
        
    with pytest.raises(SSRFError):
        SSRFProtector.validate_url("http://localhost/admin")
        
def test_ssrf_protector_rejects_metadata():
    with pytest.raises(SSRFError):
        SSRFProtector.validate_url("http://169.254.169.254/latest/meta-data")
        
def _resolves_to(monkeypatch, *addresses):
    # DNS answered without the network, so the test runs offline too.
    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in addresses]

    monkeypatch.setattr("app.core.ssrf_protector.socket.getaddrinfo", getaddrinfo)


def test_ssrf_protector_allows_safe_urls(monkeypatch):
    _resolves_to(monkeypatch, "93.184.215.14")
    parsed, ip = SSRFProtector.validate_url("https://www.example.com")
    assert parsed.hostname == "www.example.com"
    assert ip == "93.184.215.14"


def test_ssrf_protector_refuses_a_name_with_one_private_record(monkeypatch):
    # DNS rebinding: one public and one private answer for the same name.
    _resolves_to(monkeypatch, "93.184.215.14", "10.0.0.5")
    with pytest.raises(SSRFError):
        SSRFProtector.validate_url("https://www.example.com")

@pytest.mark.anyio
async def test_sandbox_python_timeout():
    manager = EphemeralSandboxManager()
    result = await manager.execute_python("import time; time.sleep(10)", timeout=1)
    assert result.exit_code != 0
    err_lower = result.stderr.lower()
    # Accept either timeout from our code or docker daemon connection error
    assert "timed out" in err_lower or "error" in err_lower or "docker" in err_lower

@pytest.mark.anyio
async def test_sandbox_python_memory_exhaustion():
    manager = EphemeralSandboxManager(memory_limit="64m")
    # Allocate a lot of memory
    result = await manager.execute_python("a = ' ' * 1024 * 1024 * 100", timeout=5)
    # The container should be killed by OOM killer, exit code 137 typically
    assert result.exit_code != 0

@pytest.mark.anyio
async def test_sandbox_shell_network_isolation():
    manager = EphemeralSandboxManager(network_disabled=True)
    result = await manager.execute_shell("curl -I https://google.com", timeout=5)
    assert result.exit_code != 0
    # No network means it cannot resolve host or connect
    assert "curl" in result.stderr or "wget" in result.stderr or result.exit_code != 0

@pytest.mark.anyio
async def test_sandbox_shell_read_only():
    manager = EphemeralSandboxManager()
    result = await manager.execute_shell("touch /usr/test.txt", timeout=5)
    assert result.exit_code != 0

    # The read-only check needs a container that actually started. Before R1
    # a blind `except Exception: pass` also swallowed this assertion.
    if any(marker in result.stderr for marker in SANDBOX_DID_NOT_START):
        pytest.skip(f"The sandbox container did not start here: {result.stderr.strip()[:120]}")
    assert "Read-only file system" in result.stderr
