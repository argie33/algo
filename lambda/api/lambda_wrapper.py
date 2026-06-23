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
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)


class LambdaAPIClient:
    """Client for invoking algo-api-dev Lambda function directly."""

    def __init__(self) -> None:
        self.function_name = os.getenv("LAMBDA_API_FUNCTION", "algo-api-dev")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.client = None

    def _get_client(self) -> Any:
        """Get or create Lambda client."""
        if self.client is None:
            try:
                config = Config(
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"max_attempts": 0},
                )
                self.client = boto3.client("lambda", region_name=self.region, config=config)
            except Exception as e:
                raise RuntimeError(f"Operation failed: {e}") from e
        return self.client

    def invoke(self, path: str, method: str = "GET", query_params: dict | None = None) -> dict[str, Any]:
        """
        Invoke the Lambda function directly.

        Args:
            path: API path (e.g., "/api/algo/performance")
            method: HTTP method (GET, POST, etc.)
            query_params: Query string parameters

        Returns:
            Response dict with 'statusCode' and 'body' (JSON parsed)

        Raises:
            RuntimeError if Lambda client is unavailable
            json.JSONDecodeError if response payload is invalid
        """
        event = {
            "path": path,
            "requestContext": {
                "http": {
                    "method": method,
                }
            },
        }

        if query_params:
            event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query_params.items())

        logger.debug(f"[Lambda] Invoking {self.function_name} with path={path}")

        client = self._get_client()
        if not client:
            raise RuntimeError("Lambda client unavailable")

        response = client.invoke(
            FunctionName=self.function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(event),
        )

        response_payload = json.loads(response["Payload"].read())

        status_code = response_payload.get("statusCode", 500)
        body = response_payload.get("body", "{}")

        if isinstance(body, str):
            body = json.loads(body)

        logger.debug(f"[Lambda] Response: {status_code}")

        return {
            "statusCode": status_code,
            "body": body,
            "_source": "lambda_direct",
        }


# Singleton instance (thread-safe)
_client = None
_client_lock = threading.Lock()


def get_lambda_client() -> LambdaAPIClient:
    """Get the global Lambda API client (thread-safe)."""
    global _client
    with _client_lock:
        if _client is None:
            _client = LambdaAPIClient()
    return _client


def invoke_api(path: str, method: str = "GET", query_params: dict | None = None) -> dict[str, Any]:
    """Invoke the Lambda API directly (convenience function)."""
    return get_lambda_client().invoke(path, method, query_params)
