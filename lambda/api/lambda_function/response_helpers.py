"""Response-building helpers for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): content-type/security/cache headers and standardized error responses.
"""

from __future__ import annotations

import json
from typing import Any

from .cors_headers import get_cors_headers


def get_json_content_type() -> str:
    return "application/json; charset=utf-8"


def get_security_headers() -> dict[str, str]:
    from routes.utils import get_api_version_headers

    return {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'self'"
        ),
        **get_api_version_headers(),
    }


def make_error_response(code: int, error_type: str, message: str, event: dict[str, Any]) -> dict[str, Any]:
    """Build standardized error response with CORS and security headers.

    Eliminates repetitive error response building throughout lambda_handler.
    All 11 parameters (statusCode, errorType, message, _error, Content-Type, CORS, security headers)
    bundled into one call.

    Args:
        code: HTTP status code (400, 401, 500, etc.)
        error_type: Error classification for client (e.g., "invalid_json", "unauthorized")
        message: Human-readable error message (sanitized)
        event: Lambda event dict (used to extract CORS headers)

    Returns:
        Standardized Lambda response dict with statusCode, headers, body
    """
    cors_headers = get_cors_headers(event)
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": get_json_content_type(),
            **cors_headers,
            **get_security_headers(),
        },
        "body": json.dumps(
            {
                "statusCode": code,
                "errorType": error_type,
                "message": message,
                "_error": message,
            }
        ),
    }


def get_cache_headers(cache_type: str = "no-cache") -> dict[str, str]:
    """Return cache control headers based on content type.

    Args:
        cache_type: 'no-cache' (revalidate each time), 'public' (cacheable),
                    'private' (user-specific), or 'none' (never cache)
    """
    if cache_type == "no-cache":
        # Sensitive data - always revalidate with server
        return {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    elif cache_type == "public":
        # Public market data - cache for 5 minutes
        return {
            "Cache-Control": "public, max-age=300, s-maxage=300",
        }
    elif cache_type == "private":
        # User-specific data - cache only on client, not CDN
        return {
            "Cache-Control": "private, max-age=300",
        }
    elif cache_type == "none":
        # Never cache
        return {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
    else:
        return {"Cache-Control": "no-cache"}
