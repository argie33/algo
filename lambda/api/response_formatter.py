#!/usr/bin/env python3
"""Response Formatter - Unified API response formatting.

Consolidates 4 separate response builders into single source of truth:
- success_response() → single object
- error_response() → errors
- json_response() → wrapper for 200 or error codes
- list_response() → paginated lists

All use consistent format: {statusCode, data, statusMessage?, data_freshness?}
"""

from __future__ import annotations

from typing import Any


class ResponseFormatter:
    """Unified formatter for all API response types.

    Ensures consistent response shape across all endpoints:
    - Success (200): {statusCode: 200, data: {...}, data_freshness?: {...}, statusMessage?: "..."}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "...", _error: "..."}
    - List (200): {statusCode: 200, data: {items: [...], total: X, limit?: Y, offset?: Z}, data_freshness?: {...}}

    Replaces: success_response(), error_response(), json_response(), list_response()
    """

    # ──────────────────────────────────────────────────────────────────────────
    # SUCCESS RESPONSES
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def success(
        data: Any,
        status: int = 200,
        meta: dict[str, Any] | None = None,
        data_freshness: dict[str, Any] | None = None,
        status_message: str | None = None,
    ) -> dict[str, Any]:
        """Format successful response for single object.

        Args:
            data: Response data (will be sanitized to remove None values)
            status: HTTP status code (default 200)
            meta: Legacy metadata field (for backward compatibility)
            data_freshness: Data freshness/staleness metadata (age_days, is_stale, etc.)
            status_message: Optional status message (e.g., "Data loaded successfully")

        Returns:
            {statusCode: 200, data: {...}, data_freshness?: {...}, statusMessage?: "..."}
        """
        from utils.validation.api_response import APIResponseValidator

        response: dict[str, Any] = {
            "statusCode": status,
            "data": APIResponseValidator.sanitize_response(data),
        }
        if data_freshness:
            response["data_freshness"] = data_freshness
        if status_message:
            response["statusMessage"] = status_message
        if meta:
            response["meta"] = meta
        return response

    @staticmethod
    def json(
        code: int,
        data: dict[str, Any] | None = None,
        data_freshness: dict[str, Any] | None = None,
        status_message: str | None = None,
    ) -> dict[str, Any]:
        """Format JSON response (wrapper for success or error based on status code).

        For 200: delegates to success()
        For 4xx/5xx: delegates to error()

        Args:
            code: HTTP status code
            data: Response data (for success) or error fields (for error)
            data_freshness: Data freshness metadata (ignored for errors)
            status_message: Optional status message

        Returns:
            Standardized response dict
        """
        if code == 200:
            if data is None:
                return ResponseFormatter.error(
                    "data_unavailable", "Upstream loader returned None - data unavailable", status=503
                )
            return ResponseFormatter.success(
                data, status=code, data_freshness=data_freshness, status_message=status_message
            )
        else:
            error_type = str(data.get("errorType")) if data and data.get("errorType") else "unknown_error"
            error_msg = str(data.get("message")) if data and data.get("message") else "An error occurred"
            return ResponseFormatter.error(error_type, error_msg, status=code)

    # ──────────────────────────────────────────────────────────────────────────
    # LIST RESPONSES
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def paginated_list(
        items: list[Any],
        total: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        data_freshness: dict[str, Any] | None = None,
        status_message: str | None = None,
    ) -> dict[str, Any]:
        """Format paginated list response.

        Args:
            items: Array of items (will be sanitized)
            total: Total count (if None, uses len(items))
            limit: Limit parameter used in query (optional)
            offset: Offset parameter used in query (optional)
            data_freshness: Data freshness/staleness metadata
            status_message: Optional status message

        Returns:
            {statusCode: 200, data: {items: [...], total: X, limit?: Y, offset?: Z}, data_freshness?: {...}}
        """
        from utils.validation.api_response import APIResponseValidator

        sanitized_items = APIResponseValidator.sanitize_response(items if items is not None else [])
        total_count = total if total is not None else len(sanitized_items)

        data: dict[str, Any] = {
            "items": sanitized_items,
            "total": total_count,
        }
        if limit is not None:
            data["limit"] = limit
        if offset is not None:
            data["offset"] = offset

        response: dict[str, Any] = {"statusCode": 200, "data": data}
        if data_freshness:
            response["data_freshness"] = data_freshness
        if status_message:
            response["statusMessage"] = status_message
        return response

    # ──────────────────────────────────────────────────────────────────────────
    # ERROR RESPONSES
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def error(error_code: str, message: str, status: int = 400) -> dict[str, Any]:
        """Format error response.

        Args:
            error_code: Error type identifier (e.g., "bad_request", "not_found", "internal_error")
            message: Human-readable error message (will be sanitized)
            status: HTTP status code

        Returns:
            {statusCode: code, errorType: "...", message: "...", _error: "..."}
        """
        from utils.error_handlers import sanitize_error_message

        # Sanitize message to prevent credential/PII leakage
        sanitized_msg = sanitize_error_message(message or "")

        response: dict[str, Any] = {
            "statusCode": status,
            "errorType": error_code,
            "message": sanitized_msg,
            "_error": sanitized_msg,  # Redundant field for compatibility
        }

        # Mark 503/504 errors as transient so dashboard fetchers retry with backoff
        if status == 503:
            response["_is_transient_503"] = True
        elif status == 504:
            response["_is_transient_504"] = True

        return response

    # ──────────────────────────────────────────────────────────────────────────
    # PAGINATED (LEGACY)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
        """Format paginated response (legacy format).

        DEPRECATED: Use list() instead for standardized format.
        Kept for backward compatibility with existing code.
        """
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size,
            },
        }
