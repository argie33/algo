"""
Lambda Function Wrapper - Direct invocation for dashboard access.

Allows the dashboard to invoke the algo-api-dev Lambda function directly
without needing the API Gateway endpoint URL. This bypasses VPC isolation
and IAM permission issues that prevent discovering the API Gateway URL.

Usage:
    from lambda.api.lambda_wrapper import invoke_api
    result = invoke_api("/api/algo/performance")
"""

import json
import logging
import os
import threading
from typing import Dict, Any, Optional

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


class LambdaAPIClient:
    """Client for invoking algo-api-dev Lambda function directly."""

    def __init__(self):
        self.function_name = os.getenv("LAMBDA_API_FUNCTION", "algo-api-dev")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.client = None

    def _get_client(self):
        """Get or create Lambda client."""
        if self.client is None and boto3:
            try:
                self.client = boto3.client("lambda", region_name=self.region)
            except Exception as e:
                logger.warning(f"Could not create Lambda client: {e}")
                return None
        return self.client

    def invoke(
        self, path: str, method: str = "GET", query_params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Invoke the Lambda function directly.

        Args:
            path: API path (e.g., "/api/algo/performance")
            method: HTTP method (GET, POST, etc.)
            query_params: Query string parameters

        Returns:
            Response dict with 'statusCode' and 'body' (JSON parsed)
        """
        if not boto3:
            return {"statusCode": 500, "body": {"_error": "boto3 not available"}}

        try:
            # Build the Lambda event (API Gateway v2 format)
            event = {
                "path": path,
                "requestContext": {
                    "http": {
                        "method": method,
                    }
                },
            }

            if query_params:
                event["rawQueryString"] = "&".join(
                    f"{k}={v}" for k, v in query_params.items()
                )

            logger.debug(f"[Lambda] Invoking {self.function_name} with path={path}")

            client = self._get_client()
            if not client:
                return {
                    "statusCode": 500,
                    "body": {"_error": "Lambda client unavailable"},
                }

            response = client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(event),
            )

            # Parse response
            response_payload = json.loads(response["Payload"].read())

            status_code = response_payload.get("statusCode", 500)
            body = response_payload.get("body", "{}")

            # Parse JSON body if it's a string
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    body = {"_error": body}

            logger.debug(f"[Lambda] Response: {status_code}")

            return {
                "statusCode": status_code,
                "body": body,
                "_source": "lambda_direct",
            }

        except Exception as e:
            logger.error(f"[Lambda] Invocation failed: {e}")
            return {
                "statusCode": 500,
                "body": {"_error": f"Lambda invocation failed: {str(e)}"},
                "_source": "lambda_direct",
            }


# Singleton instance (thread-safe)
_client = None
_client_lock = threading.Lock()


def get_lambda_client() -> LambdaAPIClient:
    """Get the global Lambda API client (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _client
    if _client is None:
        with _client_lock:
            # Double-check pattern to avoid race conditions
            if _client is None:
                _client = LambdaAPIClient()
    return _client


def invoke_api(
    path: str, method: str = "GET", query_params: Optional[Dict] = None
) -> Dict[str, Any]:
    """Invoke the Lambda API directly (convenience function)."""
    return get_lambda_client().invoke(path, method, query_params)
