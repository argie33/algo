"""Minimal Python Lambda API handler - temporary stub."""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway Lambda proxy events."""
    try:
        path = event.get("path", "/")
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        logger.info(f"Request: {method} {path}")

        # Health check
        if path in ["/health", "/api/health"]:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "ok"}),
            }

        # Info endpoint
        if path in ["/api", "/api/"]:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"service": "Stock Analytics API", "version": "1.0.0"}),
            }

        # Default 404
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"Not found: {path}"}),
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"}),
        }
