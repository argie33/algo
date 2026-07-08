"""Unified response builders for consistent API error handling.

Centralizes construction of standard error responses:
- data_unavailable markers
- Error responses with structured context
- Success responses with metadata

Replaces scattered json_response() + manual dict building with consistent builders.
"""

from __future__ import annotations

from typing import Any


def unavailable_response(reason: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a data_unavailable response with reason and optional context.

    Usage:
        return json_response(200, unavailable_response("insufficient_data", {"symbols": 5}))
    """
    response: dict[str, Any] = {
        "data_unavailable": True,
        "reason": reason,
    }
    if context:
        response["context"] = context
    return response


def error_response_structured(
    code: str, message: str, detail: str | None = None, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build structured error response.

    Usage:
        return json_response(500, error_response_structured(
            "computation_failed",
            "Correlation calculation failed",
            detail="Division by zero",
            context={"x_var": 0, "y_var": 2}
        ))
    """
    response: dict[str, Any] = {
        "_error": message,
        "_error_code": code,
    }
    if detail:
        response["_detail"] = detail
    if context:
        response["_context"] = context
    return response


def data_present_response(data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build successful response with data and optional metadata.

    Usage:
        return json_response(200, data_present_response(
            {"value": 0.85, "timestamp": "2026-07-05"},
            metadata={"source": "live", "freshness_hours": 0.5}
        ))
    """
    response: dict[str, Any] = {"data": data}
    if metadata:
        response["_metadata"] = metadata
    return response
