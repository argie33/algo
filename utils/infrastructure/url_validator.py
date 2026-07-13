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
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check for private, loopback, reserved ranges
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast
    except ValueError:
        return False


def _check_url_format(url: str) -> tuple[bool, str | None]:
    if not url:
        return False, "URL is empty"
    if len(url) > 2048:
        return False, "URL is too long"
    if not url.startswith(("https://", "http://")):
        return False, "URL must use HTTP or HTTPS protocol"
    return True, None


def _extract_hostname(url: str) -> tuple[str | None, str | None]:
    """Extract hostname from URL. Returns (hostname, error_msg)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or parsed.netloc.split(":")[0]
        if not hostname:
            return None, "URL has no hostname"
        return hostname, None
    except Exception as e:
        return None, f"URL parsing failed: {e}"


def _check_hostname_safety(hostname: str) -> tuple[bool, str | None]:
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return False, "Localhost URLs not allowed"
    if is_private_ip(hostname):
        return False, f"Private/reserved IP address not allowed: {hostname}"
    return True, None


def _check_domain_whitelist(hostname: str, allowed_domains: list[str]) -> tuple[bool, str | None]:
    for allowed in allowed_domains:
        if hostname.endswith(allowed) or hostname == allowed:
            return True, None
    return False, f"Domain {hostname} not in whitelist: {allowed_domains}"


def _check_path_traversal(url: str) -> bool:
    return any(char in url for char in ["../", "..\\", "%2e%2e"])


def validate_url(url: str, allowed_domains: list[str] | None = None) -> tuple[bool, str | None]:
    """
    Validate URL for SSRF safety.

    Args:
        url: Full URL to validate
        allowed_domains: List of allowed domain patterns (e.g., ['aaii.com', 'sec.gov'])
                         If None, only checks for private IPs/localhost

    Returns:
        (is_valid: bool, error_msg: Optional[str])
    """
    is_valid, error = _check_url_format(url)
    if not is_valid:
        return is_valid, error

    hostname, error = _extract_hostname(url)
    if error or not hostname:
        return False, error or "URL has no hostname"

    is_valid, error = _check_hostname_safety(hostname)
    if not is_valid:
        return is_valid, error

    if allowed_domains:
        is_valid, error = _check_domain_whitelist(hostname, allowed_domains)
        if not is_valid:
            return is_valid, error

    if _check_path_traversal(url):
        return False, "Path traversal detected in URL"

    return True, None


def validate_redirect_url(
    original_url: str, redirect_url: str, allowed_domains: list[str] | None = None
) -> tuple[bool, str | None]:
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
    except (ValueError, Exception) as e:
        return False, f"URL parsing failed: {e}"

    # If redirected to a different domain, check it's still in allowlist
    if orig_host.lower() != redir_host.lower():
        logger.warning(f"Redirect detected: {orig_host} -> {redir_host}")
        return validate_url(redirect_url, allowed_domains)

    return True, None
