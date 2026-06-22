#!/usr/bin/env python3
"""Lambda base handler - Consolidates common patterns across Lambda functions.

Provides:
- Standardized response formatting (statusCode + body JSON)
- Consistent error handling with proper logging
- Environment validation helpers
- Database connection helpers
- Consistent exception handling hierarchy
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2

logger = logging.getLogger()


class LambdaResponse:
    """Standardized Lambda response format."""

    def __init__(self, status_code: int, body: dict[str, Any]):
        self.status_code = status_code
        self.body = body

    def to_dict(self) -> dict[str, Any]:
        """Convert to Lambda response dict."""
        return {
            "statusCode": self.status_code,
            "body": json.dumps(self.body),
        }

    @staticmethod
    def success(data: dict[str, Any] | None = None, message: str = "Success") -> "LambdaResponse":
        """Create a successful response."""
        return LambdaResponse(
            200,
            {"status": "success", "message": message, **(data or {})},
        )

    @staticmethod
    def error(error_msg: str, status_code: int = 500, error_type: str | None = None) -> "LambdaResponse":
        """Create an error response."""
        return LambdaResponse(
            status_code,
            {
                "status": "error",
                "message": error_msg,
                "error_type": error_type or "internal_error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def validation_error(field: str, reason: str) -> "LambdaResponse":
        """Create a validation error response."""
        return LambdaResponse(
            400,
            {
                "status": "error",
                "message": f"Validation error: {reason}",
                "error_type": "validation_error",
                "field": field,
            },
        )


class LambdaHandler(ABC):
    """Abstract base class for Lambda handlers.

    Provides standardized pattern for:
    - Request validation
    - Error handling
    - Logging
    - Response formatting
    """

    def __init__(self):
        """Initialize handler with logging."""
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Setup handler logging."""
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(log_level)

    @abstractmethod
    def handle(self, event: dict[str, Any], context: Any) -> LambdaResponse:
        """Handle the Lambda event. Must be implemented by subclass."""

    def invoke(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """Public entry point for Lambda. Wraps handle() with error handling."""
        try:
            response = self.handle(event, context)
            return response.to_dict()
        except Exception as e:
            logger.exception(f"Unhandled exception in Lambda handler: {e}")
            return LambdaResponse.error(
                str(e),
                status_code=500,
                error_type=type(e).__name__,
            ).to_dict()

    @staticmethod
    def require_env_var(name: str, description: str = "") -> str:
        """Require an environment variable or raise error."""
        value = os.environ.get(name)
        if not value:
            error_msg = f"Required environment variable {name} is not set"
            if description:
                error_msg += f" ({description})"
            raise ValueError(error_msg)
        return value

    @staticmethod
    def get_db_connection(
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        ssl_mode: str = "require",
        timeout: int = 10,
    ) -> psycopg2.extensions.connection:
        """Get a database connection with proper error handling."""
        try:
            db_host = host or os.environ.get("DB_HOST")
            db_port = port or int(os.environ.get("DB_PORT", "5432"))
            db_name = database or os.environ.get("DB_NAME")
            db_user = user or os.environ.get("DB_USER")
            db_password = password or os.environ.get("DB_PASSWORD")

            if not all([db_host, db_name, db_user]):
                raise ValueError("Missing required database configuration (host, name, user)")

            return psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                connect_timeout=timeout,
                sslmode=ssl_mode,
            )
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Database connection failed: {e}") from e

    @staticmethod
    def get_secret(secret_arn: str, region: str = "us-east-1") -> dict[str, Any]:
        """Fetch secret from AWS Secrets Manager."""
        try:
            client = boto3.client("secretsmanager", region_name=region)
            response = client.get_secret_value(SecretId=secret_arn)
            if "SecretString" in response:
                return dict(json.loads(response["SecretString"]))
            return dict(json.loads(response["SecretBinary"]))
        except Exception as e:
            raise RuntimeError(f"Failed to fetch secret {secret_arn}: {e}") from e

    @staticmethod
    def get_dynamodb_table(table_name: str, region: str = "us-east-1") -> Any:
        """Get a DynamoDB table resource."""
        dynamodb = boto3.resource("dynamodb", region_name=region)
        return dynamodb.Table(table_name)


def create_lambda_handler(handler_class: type[LambdaHandler]) -> Any:
    """Create a Lambda handler function from a handler class.

    Usage:
        class MyHandler(LambdaHandler):
            def handle(self, event, context):
                return LambdaResponse.success({"result": "..."})

        lambda_handler = create_lambda_handler(MyHandler)
    """
    handler_instance = handler_class()
    return handler_instance.invoke
