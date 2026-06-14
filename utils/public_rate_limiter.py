#!/usr/bin/env python3
"""
Public Endpoint Rate Limiting

Protects public API endpoints from abuse by rate limiting per-IP-address.
This prevents DoS attacks on endpoints that don't require authentication.

SECURITY: Public endpoints are accessible to anyone and thus need
per-IP rate limiting to prevent being hammered by bots or attackers.
"""

import hashlib
import logging
import os
from time import time
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# In-memory rate limit tracker: {endpoint_ip: [timestamp, ...]}
# Note: This is per-Lambda-instance. For distributed rate limiting, use DynamoDB.
_public_rate_limits: Dict[str, list] = {}


def _get_rate_limit_key(client_ip: str, endpoint: str) -> str:
    """Generate a unique key for rate limit tracking."""
    return f"{endpoint}:{client_ip}"


def check_public_rate_limit(
    client_ip: str,
    endpoint: str,
    max_requests: int = 100,
    window_seconds: int = 60,
) -> Tuple[bool, Optional[str]]:
    """
    Check if client IP has exceeded public endpoint rate limit.

    Args:
        client_ip: Client IP address from request context
        endpoint: API endpoint path (e.g., '/api/algo/markets')
        max_requests: Max requests allowed in time window
        window_seconds: Time window in seconds

    Returns:
        (is_allowed: bool, error_msg: Optional[str])
    """
    global _public_rate_limits

    now = time()
    window_start = now - window_seconds
    key = _get_rate_limit_key(client_ip, endpoint)

    # Initialize or get request times for this endpoint:IP
    if key not in _public_rate_limits:
        _public_rate_limits[key] = []

    # Remove old requests outside the window
    recent_requests = [t for t in _public_rate_limits[key] if t >= window_start]
    _public_rate_limits[key] = recent_requests

    # Check if limit exceeded
    if len(recent_requests) >= max_requests:
        logger.warning(
            f"Public endpoint rate limit exceeded for {client_ip} on {endpoint}: "
            f"{len(recent_requests)} requests in {window_seconds}s"
        )
        return False, f"Rate limit exceeded: max {max_requests} requests per minute"

    # Record this request
    _public_rate_limits[key].append(now)
    return True, None


# Rate limit profiles for different public endpoints
PUBLIC_RATE_LIMITS = {
    '/api/algo/markets': {'max_requests': 100, 'window': 60},           # Popular endpoint
    '/api/algo/market': {'max_requests': 100, 'window': 60},            # Popular endpoint
    '/api/algo/swing-scores': {'max_requests': 100, 'window': 60},      # Popular endpoint
    '/api/algo/market-factors': {'max_requests': 100, 'window': 60},    # Popular endpoint
}
