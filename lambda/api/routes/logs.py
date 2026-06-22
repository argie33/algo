"""Route: logs - Frontend error logging to CloudWatch

Receives error logs from frontend (React app) and sends them to CloudWatch Logs.

POST /api/logs
Body: {
  "logs": [
    {
      "timestamp": "2026-06-14T12:00:00Z",
      "level": "ERROR",
      "sessionId": "uuid",
      "userId": "user123",
      "component": "MarketsHealth",
      "operation": "fetchMarketData",
      "errorType": "TypeError",
      "errorMessage": "Cannot read property 'price' of undefined",
      "errorStack": "...",
      "url": "https://...",
      "context": {}
    }
  ],
  "sessionId": "uuid",
  "userId": "user123",
  "environment": "production"
}
"""

import json
import logging
from typing import Any

import boto3
from routes.utils import error_response, success_response

logger = logging.getLogger(__name__)

# CloudWatch Logs client (lazy init to avoid NoRegionError at import time)
_logs_client = None
LOG_GROUP = "/aws/frontend/algo-trading-dashboard"


def _get_logs_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs")
    return _logs_client


def ensure_log_stream(stream_name: str):
    """Ensure CloudWatch log stream exists."""
    try:
        client = _get_logs_client()
        client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
    except _get_logs_client().exceptions.ResourceAlreadyExistsException:
        pass  # Stream already exists
    except Exception as e:
        logger.warning(f"Could not create log stream {stream_name}: {e}")


def handle(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
) -> dict[str, Any]:
    """Handle frontend error logging.

    POST /api/logs - Receive and log frontend errors to CloudWatch
    Authentication: Optional (can be called from unauthenticated components)
    """

    if method != "POST":
        return error_response(405, "method_not_allowed", "Only POST is supported")

    if not body:
        return error_response(400, "missing_body", "Request body required")

    try:
        logs = body.get("logs")
        session_id = body.get("sessionId", "unknown")
        user_id = body.get("userId", "anonymous")
        environment = body.get("environment", "unknown")

        if not logs:
            return success_response({"logged": 0, "message": "No logs to process"})

        # Create log stream for this user/session
        stream_name = f"{environment}/{user_id}/{session_id[:8]}"
        ensure_log_stream(stream_name)

        # Batch logs by level for easier filtering
        log_events = []

        for log_entry in logs:
            # Format log message
            if log_entry.get("type") == "API_ERROR":
                message = (
                    f"API_ERROR: {log_entry.get('component')}/{log_entry.get('operation')} - "
                    f"{log_entry.get('method')} {log_entry.get('endpoint')} "
                    f"({log_entry.get('statusCode')}): {log_entry.get('errorMessage')}"
                )
            else:
                message = (
                    f"{log_entry.get('level', 'LOG')}: {log_entry.get('component', '?')}/"
                    f"{log_entry.get('operation', '?')} - "
                    f"{log_entry.get('errorMessage', log_entry.get('message', ''))}"
                )

            # Add full context as JSON
            context = {
                "timestamp": log_entry.get("timestamp"),
                "level": log_entry.get("level", "LOG"),
                "component": log_entry.get("component"),
                "operation": log_entry.get("operation"),
                "errorType": log_entry.get("errorType"),
                "url": log_entry.get("url"),
                "userAgent": log_entry.get("userAgent"),
                "context": log_entry.get("context"),
            }

            # CloudWatch expects unix timestamp in milliseconds
            from datetime import datetime

            timestamp_str = log_entry.get("timestamp", "")
            try:
                if timestamp_str:
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    timestamp_ms = int(dt.timestamp() * 1000)
                else:
                    from datetime import datetime, timezone

                    timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            except (ValueError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse log entry timestamp '{timestamp_str}': {e}, using current time")
                from datetime import datetime, timezone

                timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            log_events.append(
                {
                    "timestamp": timestamp_ms,
                    "message": f"{message}\nContext: {json.dumps(context)}",
                }
            )

        if log_events:
            try:
                # Put logs to CloudWatch (batch up to 1MB)
                _get_logs_client().put_log_events(
                    logGroupName=LOG_GROUP,
                    logStreamName=stream_name,
                    logEvents=log_events,
                )
                logger.info(f"Logged {len(log_events)} frontend events to {stream_name}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to put logs to CloudWatch: {e}")
                # Still return success to avoid breaking frontend
                return success_response(
                    {
                        "logged": len(log_events),
                        "message": "Logs received (CloudWatch delivery failed)",
                        "warning": "Local logging may be unavailable",
                    }
                )

        return success_response(
            {
                "logged": len(log_events),
                "sessionId": session_id,
                "message": f"Logged {len(log_events)} events to CloudWatch",
            }
        )

    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"Log handler error: {e}", exc_info=True)
        # Return success anyway - don't break frontend if logging fails
        return success_response(
            {
                "logged": 0,
                "message": "Log handler error (frontend not affected)",
                "error": str(e)[:100],
            }
        )
