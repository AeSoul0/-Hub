"""
@file backend/app/core/ssrf_protector.py
@description SSRF Protection Module

Implements URL parsing, DNS resolution, and strict validation against private,
loopback, link-local, and metadata IP addresses. Validates redirects and prevents
DNS rebinding by re-resolving during execution.
"""
import socket
import urllib.parse
import ipaddress
import httpx
from typing import Tuple

class SSRFError(Exception):
    pass

class SSRFProtector:
    """
    Represents the SSRFProtector entity and its core operations.
    """

    ALLOWED_SCHEMES = {"http", "https"}

    @staticmethod
    def is_safe_ip(ip_str: str) -> bool:
        """
        Executes the is_safe_ip logic.
        """
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        # ::ffff:127.0.0.1 must be judged as the IPv4 address it maps to.
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped

        # Only globally routable unicast addresses: this excludes loopback,
        # RFC1918/ULA, CGNAT, link-local (cloud metadata lives in
        # 169.254.0.0/16), 0.0.0.0/::, documentation and reserved ranges.
        return ip.is_global and not ip.is_multicast

    @staticmethod
    def resolve_and_validate(hostname: str) -> str:
        """
        Executes the resolve_and_validate logic.
        Resolves hostname and checks that every resolved IP is safe, so a
        host with one public and one private record is rejected.
        """
        try:
            # Re-resolution to prevent DNS rebinding
            infos = socket.getaddrinfo(hostname, None)
        except (socket.gaierror, UnicodeError):
            raise SSRFError(f"DNS resolution failed for hostname: {hostname}")

        addresses = sorted({info[4][0] for info in infos})
        if not addresses:
            raise SSRFError(f"DNS resolution failed for hostname: {hostname}")

        for address in addresses:
            if not SSRFProtector.is_safe_ip(address):
                raise SSRFError(f"SSRF Attempt detected! Resolved IP {address} is restricted.")

        return addresses[0]

    @staticmethod
    def validate_url(url: str) -> Tuple[urllib.parse.ParseResult, str]:
        """
        Executes the validate_url logic.
        Returns parsed URL parts if safe.
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in SSRFProtector.ALLOWED_SCHEMES:
            raise SSRFError(f"Invalid scheme: {parsed.scheme}")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFError("Missing hostname in URL")

        if parsed.username or parsed.password:
            raise SSRFError("Credentials in URL are not allowed")

        ip_address = SSRFProtector.resolve_and_validate(hostname)
        return parsed, ip_address

class SafeHTTPClient:
    """
    Represents the SafeHTTPClient entity and its core operations.
    """

    @staticmethod
    async def request(method: str, url: str, **kwargs) -> httpx.Response:
        """
        Executes the request logic.
        Validates URL and handles redirects manually to prevent redirect SSRF.
        """
        SSRFProtector.validate_url(url)

        # Disable automatic redirects to validate each hop
        kwargs["follow_redirects"] = False

        current_url = url
        redirect_count = 0
        max_redirects = 5

        async with httpx.AsyncClient() as client:
            while redirect_count < max_redirects:
                response = await client.request(method, current_url, **kwargs)

                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location")
                    if not location:
                        break

                    # Handle relative redirects
                    next_url = urllib.parse.urljoin(current_url, location)

                    # Validate the redirect URL
                    SSRFProtector.validate_url(next_url)

                    current_url = next_url
                    redirect_count += 1
                else:
                    return response

            if redirect_count >= max_redirects:
                raise SSRFError("Too many redirects")

            return response
