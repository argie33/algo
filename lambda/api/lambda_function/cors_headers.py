"""CORS helpers for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): allowed-origin allowlist construction and per-request CORS header building.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger()

_ALLOWED_ORIGINS_CACHE = None
_ALLOWED_ORIGINS_CACHE_TIME = None
_ALLOWED_ORIGINS_LOCK = threading.Lock()  # Protects allowed origins cache
_ALLOWED_ORIGINS_CACHE_TTL_SECONDS = 3600  # Refresh allowed origins hourly (handles env var changes)


def _build_allowed_origins() -> set[str]:
    """Build allowed origins from environment variables (cached at module load).

    SECURITY FIX: Explicitly configure all allowed origins; no wildcard matching.
    Dev mode origins (localhost) only allowed if ALLOW_LOCALHOST_CORS=true
    Thread-safe: Uses double-check locking pattern to prevent race conditions.
    """
    global _ALLOWED_ORIGINS_CACHE, _ALLOWED_ORIGINS_CACHE_TIME

    now = datetime.now(timezone.utc)
    cache_ttl = timedelta(seconds=_ALLOWED_ORIGINS_CACHE_TTL_SECONDS)

    # Check if cache is still valid (within TTL)
    if (
        _ALLOWED_ORIGINS_CACHE is not None
        and _ALLOWED_ORIGINS_CACHE_TIME is not None
        and (now - _ALLOWED_ORIGINS_CACHE_TIME) < cache_ttl
    ):
        return _ALLOWED_ORIGINS_CACHE

    with _ALLOWED_ORIGINS_LOCK:
        # Double-check pattern after acquiring lock
        if (
            _ALLOWED_ORIGINS_CACHE is not None
            and _ALLOWED_ORIGINS_CACHE_TIME is not None
            and (now - _ALLOWED_ORIGINS_CACHE_TIME) < cache_ttl
        ):
            return _ALLOWED_ORIGINS_CACHE

        origins = set()

        # FRONTEND_URL is required in production (must be set explicitly)
        frontend_url = os.getenv("FRONTEND_URL")
        if frontend_url:
            frontend_url = frontend_url.strip()
            if frontend_url:
                origins.add(frontend_url)

        # Additional origins from ALLOWED_ORIGINS env var (comma-separated)
        env_origins = os.getenv("ALLOWED_ORIGINS")
        if env_origins:
            env_origins = env_origins.strip()
            if env_origins:
                for o in env_origins.split(","):
                    o = o.strip()
                    if o:
                        origins.add(o)

        # In development ONLY, allow localhost origins (if explicitly enabled)
        # This is gated behind ALLOW_LOCALHOST_CORS=true to prevent accidental exposure
        if os.getenv("ALLOW_LOCALHOST_CORS") == "true":
            origins.add("http://localhost:5173")  # Vite default
            origins.add("http://localhost:3000")  # React dev default

        _ALLOWED_ORIGINS_CACHE = origins
        _ALLOWED_ORIGINS_CACHE_TIME = now
        return origins


def get_cors_headers(event: dict[str, Any]) -> dict[str, str]:
    """Get CORS headers based on request origin (strict whitelist only).

    SECURITY FIX: Explicitly whitelists origins from FRONTEND_URL and ALLOWED_ORIGINS.
    Dev mode: Allows localhost/127.0.0.1 if ALLOW_LOCALHOST_CORS=true.

    Issue #10 FIX: Improved diagnostics when CORS fails.
    """
    headers = event.get("headers")
    headers = headers if headers is not None else {}
    origin = headers.get("origin", "")
    if origin == "":
        origin = headers.get("Origin", "")
    if not origin:
        origin = ""

    allowed_origins = _build_allowed_origins()

    # Only allow origin if explicitly whitelisted
    if origin in allowed_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }

    # Enhanced diagnostics for CORS failures (helps debug Issue #10)
    frontend_url = os.getenv("FRONTEND_URL", "").strip()
    allow_localhost = os.getenv("ALLOW_LOCALHOST_CORS", "") == "true"

    # Log CORS rejection with context for debugging
    if origin:
        logger.warning(
            f"[CORS_REJECTED] origin={origin} frontend_url={frontend_url if frontend_url else 'NOT_SET'} "
            f"allow_localhost={allow_localhost} allowed_origins={allowed_origins}"
        )

    # Reject cross-origin requests from unknown sources
    # Return minimal headers so browser blocks the response as a security measure
    return {
        "Vary": "Origin",
    }
