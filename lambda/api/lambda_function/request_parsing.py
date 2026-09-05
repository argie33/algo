"""Request-parsing and audit-logging helpers for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): header redaction, query-param parsing/validation, client IP extraction, and
structured audit-log emission.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger()


def redact_sensitive_headers(headers_dict: dict[str, str]) -> dict[str, str]:
    """Issue #42: Redact sensitive headers from logs to prevent credential leakage."""
    redacted = dict(headers_dict)
    sensitive_keys = ["authorization", "cookie", "x-api-key", "x-auth-token"]
    for key in sensitive_keys:
        if key.lower() in [k.lower() for k in redacted.keys()]:
            actual_key = next(k for k in redacted.keys() if k.lower() == key.lower())
            redacted[actual_key] = "***REDACTED***"
    return redacted


def validate_query_param_type(value: str, expected_type: str) -> tuple[bool, Any]:
    """Validate and convert query parameter to expected type.

    Args:
        value: The string value to validate
        expected_type: 'int', 'float', 'bool', 'string'

    Returns:
        (valid: bool, converted_value: Any)
    """
    if expected_type == "int":
        try:
            return True, int(value)
        except ValueError:
            return False, None
    elif expected_type == "float":
        try:
            return True, float(value)
        except ValueError:
            return False, None
    elif expected_type == "bool":
        if value.lower() in ("true", "1", "yes", "on"):
            return True, True
        elif value.lower() in ("false", "0", "no", "off"):
            return True, False
        else:
            return False, None
    else:  # string
        return True, value


def parse_query_params(event: dict[str, Any]) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    # Try v1 format first (REST API)
    if event.get("queryStringParameters"):
        for k, v in event["queryStringParameters"].items():
            params[k] = [v] if v else []
    # If no v1 params, try v2 format (HTTP API with rawQueryString)
    elif event.get("rawQueryString"):
        for param in event["rawQueryString"].split("&"):
            if "=" in param:
                k, v = param.split("=", 1)
                existing = params.get(k)
                params[k] = [*(existing if existing is not None else []), v]
            else:
                params[param] = [""]
    return params


def get_client_ip(event: dict[str, Any]) -> str:
    """Extract client IP for audit logging.

    Uses API Gateway's requestContext.identity.sourceIp as the authoritative source -
    this is filled by API Gateway itself and cannot be forged by a client.

    NOTE: When behind CloudFront, sourceIp is the CloudFront edge IP, not the user's IP.
    To log real user IPs, configure CloudFront to add a shared-secret custom header
    (e.g. x-origin-verify) and verify it here before trusting CF-Connecting-IP.
    """
    _req_ctx = event.get("requestContext")
    if _req_ctx:
        # API GW v1: requestContext.identity.sourceIp
        identity = _req_ctx.get("identity")
        if identity:
            source_ip = identity.get("sourceIp")
            if source_ip:
                return str(source_ip)
        # API GW v2: requestContext.http.sourceIp
        http_ctx = _req_ctx.get("http")
        if http_ctx:
            source_ip = http_ctx.get("sourceIp")
            if source_ip:
                return str(source_ip)

    # Fallback for local/test invocations without requestContext
    headers = event.get("headers")
    if headers:
        xff = headers.get("x-forwarded-for")
        if xff is None:
            xff = headers.get("X-Forwarded-For")
        if xff:
            return str(xff).split(",")[0].strip()

    logger.debug("Could not determine sourceIp from event (local/test invocation)")
    return "unknown"


def log_api_request(
    event: dict[str, Any],
    status_code: int,
    user_id: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Log API request for audit trail (security incident investigation).

    Format: JSON structured log with timestamp, request ID, IP, method, path, status, user
    """
    try:
        client_ip = get_client_ip(event)
        path = event.get("rawPath")
        if path is None:
            path = event.get("path", "/")
        _req_ctx = event.get("requestContext")
        _req_ctx = _req_ctx if _req_ctx is not None else {}
        http_ctx = _req_ctx.get("http")
        http_ctx = http_ctx if http_ctx is not None else {}
        method = http_ctx.get("method")
        if method is None:
            method = event.get("httpMethod")
        if method is None:
            method = f"UNKNOWN_METHOD (event has no httpMethod or http.method field; keys: {list(event.keys())})"
        request_id = _req_ctx.get("requestId", "unknown")

        audit_log = {
            "event": "API_REQUEST",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "client_ip": client_ip,
            "method": method,
            "path": path,
            "status_code": status_code,
            "user_id": user_id if user_id else "anonymous",
            # HIGH-006 FIX: Preserve None instead of replacing with empty string
            "error": error_msg,
        }

        logger.info(json.dumps(audit_log))
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to log API request: {e!s}")
