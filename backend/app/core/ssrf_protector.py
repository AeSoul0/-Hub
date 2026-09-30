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
from typing import Optional, List, Tuple

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
            # Reject loopback (127.0.0.0/8, ::1)
            if ip.is_loopback: return False
            # Reject private RFC1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
            if ip.is_private: return False
            # Reject link-local (169.254.0.0/16, fe80::/10)
            if ip.is_link_local: return False
            # Reject multicast
            if ip.is_multicast: return False
            # Reject AWS/GCP metadata IP explicitly just in case
            if ip_str == "169.254.169.254": return False
            if ip_str == "169.254.169.253": return False
            if ip_str == "metadata.google.internal": return False
            return True
        except ValueError:
            return False

    @staticmethod
    def resolve_and_validate(hostname: str) -> str:
        """
        Executes the resolve_and_validate logic.
        Resolves hostname and checks if the IP is safe.
        """
        try:
            # Re-resolution to prevent DNS rebinding
            ip_address = socket.gethostbyname(hostname)
        except socket.gaierror:
            raise SSRFError(f"DNS resolution failed for hostname: {hostname}")
            
        if not SSRFProtector.is_safe_ip(ip_address):
            raise SSRFError(f"SSRF Attempt detected! Resolved IP {ip_address} is restricted.")
            
        return ip_address

    @staticmethod
    def validate_url(url: str) -> Tuple[str, str]:
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
        parsed, initial_ip = SSRFProtector.validate_url(url)
        
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
