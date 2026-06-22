#!/usr/bin/env python3
"""Loader Result Logger - Logs ECS task results to database.

FIXED Issue #7: Data Loaders Missing Error Reporting

Triggered by Step Functions after each ECS loader task completes.
Captures success/failure status and error details to data_loader_status table.
Uses LambdaHandler base class for standardized pattern.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from base_handler import LambdaHandler, LambdaResponse, create_lambda_handler


logger = logging.getLogger()


class LoaderResultLoggerHandler(LambdaHandler):
    """Logs loader execution results to DynamoDB."""

    def handle(self, event: dict[str, Any], context: Any) -> LambdaResponse:
        """Handle loader result logging."""
        loader_name = event.get("loader_name", "unknown")
        status = event.get("status", "UNKNOWN").upper()
        error_type = event.get("error")
        message = event.get("message", "")
        execution_date = event.get("execution_date", datetime.now(timezone.utc).date().isoformat())

        logger.info(f"[LOADER-RESULT] {loader_name}: {status} - {message}")

        table_name = f"{os.getenv('PROJECT_NAME', 'algo')}-loader-status-{os.getenv('ENVIRONMENT', 'dev')}"
        table = self.get_dynamodb_table(table_name, region=os.getenv("AWS_REGION", "us-east-1"))

        expires_at = int(datetime.now(timezone.utc).timestamp()) + 3600

        table.put_item(
            Item={
                "loader_name": loader_name,
                "execution_date": execution_date,
                "status": status,
                "error_type": error_type or "NONE",
                "message": message[:500],
                "task_arn": event.get("task_arn", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at,
            }
        )

        logger.info(f"[LOADER-RESULT] Logged {loader_name} result to DynamoDB")

        return LambdaResponse.success(
            {"loader": loader_name, "status": status, "logged": True}
        )


lambda_handler = create_lambda_handler(LoaderResultLoggerHandler)
