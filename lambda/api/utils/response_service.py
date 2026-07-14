"""Centralized response formatting and error handling service.

This module consolidates response formatting, error categorization, and
error response building to eliminate duplication across api_router and lambda_function.
All responses follow a consistent format: {statusCode, data, errorType, message, _error}.
"""

from __future__ import annotations

import re
from typing import Any


def wrap_response(response: Any) -> dict[str, Any]:
    """Standardize response format for consistent client handling.

    All API responses follow a consistent format:
    - Success (200): {statusCode: 200, data: {...}, data_freshness?: {...}}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "...", _error: "..."}

    This function is a safety net for any legacy endpoints that don't use the
    response utility functions (success_response, list_response, json_response).
    Also cleans up responses that have extra fields added by intermediate processing
    and fixes double-nested data issues.

    IMPORTANT: ALL route handlers MUST return dicts (never strings or other types).
    """
    if not isinstance(response, dict):
        return response

    # Errors are returned as-is (already include errorType and _error)
    if response.get("errorType"):
        return response

    status_code = response.get("statusCode")
    if status_code is None:
        raise RuntimeError(
            "[API_RESPONSE] Handler returned response dict without statusCode. "
            "All API responses must include an explicit statusCode field. "
            f"Response: {response}"
        )

    try:
        if int(status_code) >= 400:
            return response
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"[API_RESPONSE] Invalid statusCode value '{status_code}' (must be integer). Response: {response}"
        ) from e

    # Fix double-nested data issue: if data contains only a 'data' field (or data + extra fields), unwrap it
    if response.get("statusCode") == 200 and "data" in response:
        data_field = response["data"]
        # Check if data field is a dict with only 'data' and optional metadata keys
        if isinstance(data_field, dict) and "data" in data_field:
            # Check if 'data' is the only meaningful field (allow for pagination, total, etc.)
            meaningful_keys = [k for k in data_field.keys() if k not in ("data", "pagination", "total")]
            if len(meaningful_keys) == 0:
                # Double-nested: unwrap it
                response = dict(response)  # Make a copy
                response["data"] = data_field["data"]
                # Preserve pagination metadata if it exists
                if "pagination" in data_field:
                    response["data"]["pagination"] = data_field["pagination"]
                if "total" in data_field and "total" not in response["data"]:
                    response["data"]["total"] = data_field["total"]

    # Success responses should already have 'data' field from response utilities.
    # If they don't (legacy/direct returns), wrap them.
    if response.get("statusCode") == 200 and "data" not in response:
        # Extract core fields: items, total, etc. but exclude metadata/timestamps
        payload = {
            k: v
            for k, v in response.items()
            if k
            not in (
                "statusCode",
                "headers",
                "data_freshness",
                "success",
                "timestamp",
                "pagination",
            )
        }

        # If we have items but no data, wrap them properly
        if "items" in response and "items" not in payload:
            # Keep items and reconstruct pagination if needed
            payload["items"] = response.get("items")
            if "pagination" in response:
                payload["pagination"] = response["pagination"]
            pagination = response.get("pagination")
            total = pagination.get("total") if pagination and isinstance(pagination, dict) else None
            if total is None:
                items = response.get("items")
                if items is None:
                    total = 0
                elif isinstance(items, list):
                    total = len(items)
                else:
                    total = 0
            payload["total"] = total

        wrapped = {"statusCode": 200, "data": payload}
        # Preserve data_freshness if it exists
        if "data_freshness" in response:
            wrapped["data_freshness"] = response["data_freshness"]
        # Preserve headers if they exist
        if "headers" in response:
            wrapped["headers"] = response["headers"]
        return wrapped

    return response


def format_json_value(obj: Any) -> str | float:
    """JSON serialization helper for non-standard types (dates, decimals, etc)."""
    import datetime
    from decimal import Decimal

    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "__float__"):
        return float(obj)
    return str(obj)


def build_error_response(status_code: int, error_type: str, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "errorType": error_type,
        "message": message,
        "_error": message,
    }


def categorize_error(e: Exception) -> str:
    """Categorize exception to return specific error_type for better debugging.

    Returns error_type string: 'database_error', 'auth_error', 'validation_error',
    'import_error', or 'unknown_error'
    """
    error_class_name = type(e).__name__
    error_module = type(e).__module__ if hasattr(type(e), "__module__") else ""

    # Database errors
    if "psycopg2" in error_module or error_class_name in (
        "OperationalError",
        "DatabaseError",
    ):
        return "database_error"

    # Auth/JWT errors
    if "jwt" in error_module or error_class_name in (
        "ExpiredSignatureError",
        "InvalidTokenError",
    ):
        return "auth_error"

    # Validation errors
    if error_class_name == "ValueError":
        return "validation_error"

    # Import/initialization errors
    if error_class_name in ("ImportError", "ModuleNotFoundError", "AttributeError"):
        return "import_error"

    return "unknown_error"


def format_handler_error(e: Exception) -> dict[str, Any]:
    """Format exception as error response with diagnostic error types.

    Maps exception types to documented diagnostic error codes.
    Returns specific error type to client for debugging without exposing sensitive details.
    Logs full stack trace server-side for investigation.
    """
    # APIException subclasses (NotFound, BadRequest, ServiceUnavailable, ...) declare
    # their own status_code/error_type — honor them instead of falling through the
    # string heuristics below (which previously turned every 404 into a 500).
    from exceptions import APIException

    if isinstance(e, APIException):
        return build_error_response(e.status_code, e.error_type, e.message)

    error_type = type(e).__name__
    error_msg = str(e)

    # Schema errors: missing tables, columns, or migration issues
    if "UndefinedTable" in error_type or "UndefinedColumn" in error_type:
        return build_error_response(503, "schema_error", "Database schema mismatch or migration issue")

    # Connection errors: RDS/proxy unavailable or network issues
    if "OperationalError" in error_type or "Connection" in error_type or "failed to connect" in error_msg.lower():
        return build_error_response(503, "connection_error", "RDS/database connection failed")

    # Query execution errors: SQL syntax or constraint violations
    if "ProgrammingError" in error_type or "IntegrityError" in error_type or "statement error" in error_msg.lower():
        return build_error_response(503, "query_error", "Database query execution failed")

    # Auth errors: JWT validation, token expiry, Cognito failures
    if "Unauthorized" in error_type or "Forbidden" in error_type or "JWT" in error_type or "token" in error_msg.lower():
        return build_error_response(403, "auth_error", "JWT validation or Cognito authorization failed")

    # Cognito config errors: missing or invalid Cognito environment variables
    if (
        "COGNITO_USER_POOL_ID" in error_msg
        or "COGNITO_CLIENT_ID" in error_msg
        or "cognito.*config" in error_msg.lower()
    ):
        return build_error_response(500, "cognito_config_error", "Cognito environment variables not configured")

    # Data access errors: code bugs (AttributeError, KeyError, etc.) accessing response fields
    if "AttributeError" in error_type or "KeyError" in error_type or "IndexError" in error_type:
        return build_error_response(500, "data_access_error", "Code bug accessing data fields")

    # No data errors: required data table is empty or missing
    if "no.*data" in error_msg.lower() or "empty" in error_msg.lower() or "not.*found" in error_msg.lower():
        return build_error_response(500, "no_data_error", "Required data table is empty or missing")

    # Data processing errors: generic data transformation/processing failures
    if (
        "process" in error_msg.lower()
        or "data" in error_msg.lower()
        or "ValueError" in error_type
        or "TypeError" in error_type
    ):
        return build_error_response(500, "data_processing_error", "Generic data processing failure")

    # Invalid input: malformed request parameters or body
    if "invalid" in error_msg.lower() or "Bad Request" in error_msg:
        return build_error_response(400, "invalid_input", "Client sent invalid query parameters or request body")

    # Request timeouts
    if "Timeout" in error_type or "timeout" in error_msg.lower():
        return {
            "statusCode": 504,
            "errorType": "timeout",
            "message": "Request exceeded statement_timeout - query is too slow, needs optimization",
            "_error": "Request timeout",
            "_is_transient_504": True,  # Mark as transient for dashboard retry logic
        }

    # Generic internal error for unknown exceptions
    return build_error_response(500, "data_processing_error", "Service error")


def sanitize_error_message(msg: str) -> str:
    """Remove credentials/sensitive info from error messages."""
    return re.sub(r"password=\S+|api.?key=\S+", "***", msg)
