#!/usr/bin/env python3
"""
URL Validation for SSRF Prevention

Validates URLs to prevent Server-Side Request Forgery attacks where attackers
could redirect requests to internal services (localhost, private IPs, etc.)
by compromising environment variables or poisoning DNS responses.

SECURITY: Always pin expected domains and protocols. Reject redirects to unexpected hosts.
"""

import ipaddress
import logging
from typing import List, Optional
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


def is_private_ip(ip_str: str) -> bool:
    """Check if IP address is private/reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check for private, loopback, reserved ranges
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
        )
    except ValueError:
        return False


def validate_url(url: str, allowed_domains: Optional[List[str]] = None) -> tuple:
    """
    Validate URL for SSRF safety.

    Args:
        url: Full URL to validate
        allowed_domains: List of allowed domain patterns (e.g., ['aaii.com', 'sec.gov'])
                         If None, only checks for private IPs/localhost

    Returns:
        (is_valid: bool, error_msg: Optional[str])
    """
    if not url:
        return False, "URL is empty"

    if len(url) > 2048:
        return False, "URL is too long"

    # Must be HTTPS in production (or HTTP for localhost only)
    if not (url.startswith("https://") or url.startswith("http://")):
        return False, "URL must use HTTP or HTTPS protocol"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL parsing failed: {e}"

    # Extract hostname
    hostname = parsed.hostname or parsed.netloc.split(":")[0]
    if not hostname:
        return False, "URL has no hostname"

    # SECURITY: Reject localhost and private IPs
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return False, "Localhost URLs not allowed"

    # Check if hostname is an IP address
    try:
        if is_private_ip(hostname):
            return False, f"Private/reserved IP address not allowed: {hostname}"
    except ValueError:
        pass  # Not an IP, continue to domain check

    # SECURITY: If allowed_domains specified, URL must match one
    if allowed_domains:
        domain_match = False
        for allowed in allowed_domains:
            if hostname.endswith(allowed) or hostname == allowed:
                domain_match = True
                break

        if not domain_match:
            return False, f"Domain {hostname} not in whitelist: {allowed_domains}"

    # Check for suspicious URL patterns (directory traversal, etc.)
    if any(char in url for char in ["../", "..\\", "%2e%2e"]):
        return False, "Path traversal detected in URL"

    return True, None


def validate_redirect_url(
    original_url: str, redirect_url: str, allowed_domains: Optional[List[str]] = None
) -> tuple:
    """
    Validate a redirect target to prevent SSRF via redirects.

    Use this after requests.get() with allow_redirects=True to validate the final URL.

    Args:
        original_url: The original URL that was requested
        redirect_url: The final URL after following redirects
        allowed_domains: List of allowed domains

    Returns:
        (is_valid: bool, error_msg: Optional[str])
    """
    # Extract hostnames
    try:
        orig_parsed = urlparse(original_url)
        redir_parsed = urlparse(redirect_url)
        orig_host = orig_parsed.hostname or orig_parsed.netloc.split(":")[0]
        redir_host = redir_parsed.hostname or redir_parsed.netloc.split(":")[0]
    except (requests.RequestException, requests.Timeout) as e:
        return False, f"URL parsing failed: {e}"

    # If redirected to a different domain, check it's still in allowlist
    if orig_host.lower() != redir_host.lower():
        logger.warning(f"Redirect detected: {orig_host} -> {redir_host}")
        return validate_url(redirect_url, allowed_domains)

    return True, None
