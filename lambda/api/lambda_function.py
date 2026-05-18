"""Stock Analytics Platform - API Lambda Handler."""

import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway requests."""
    try:
        path = event.get("path", "/")
        method = event.get("httpMethod", "GET")
        logger.info(f"Request: {method} {path}")

        # Health check
        if path in ["/health", "/api/health"]:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"status": "healthy"})
            }

        # API info
        if path in ["/api", "/api/"]:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "name": "Stock Analytics API",
                    "version": "1.0.0",
                    "status": "operational"
                })
            }

        # CORS preflight
        if method == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization"
                }
            }

        # 404
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "not_found", "path": path})
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "internal_server_error"})
        }
