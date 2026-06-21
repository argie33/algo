#!/usr/bin/env python3
"""Loader Failure Handler - Alert on failed data loaders in Step Functions pipeline.

Invoked by Step Functions when a loader task fails. Publishes failure alert to SNS
and logs error details for debugging.

Handler: lambda_handler
Runtime: Python 3.12
"""

import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns_client = boto3.client("sns")


def lambda_handler(event, context):
    """Handle loader task failure in Step Functions pipeline.

    Event structure from Step Functions:
    {
        "loader_name": "stock_symbols",
        "error": "States.ALL",
        "error_message": "ECS task exited with code 1"
    }

    Publishes alert to SNS topic configured in environment.
    """
    try:
        loader_name = event.get("loader_name", "unknown")
        error = event.get("error", "Unknown")
        error_message = event.get("error_message", "No details")

        logger.info(
            f"Loader failure detected: {loader_name}",
            extra={
                "loader_name": loader_name,
                "error": error,
                "error_message": error_message,
            },
        )

        # Publish alert to SNS if configured
        sns_topic_arn = os.getenv("SNS_ALERT_TOPIC_ARN")
        if sns_topic_arn:
            message = f"""
LOADER FAILURE ALERT

Loader: {loader_name}
Error: {error}
Details: {error_message}

Check CloudWatch logs for /ecs/{loader_name}-loader for details.
"""
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[ALGO] Loader Failed: {loader_name}",
                Message=message,
            )
            logger.info(f"SNS alert published for {loader_name}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Logged failure for {loader_name}",
                    "loader_name": loader_name,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Failed to handle loader failure: {e}", exc_info=True)
        # Don't re-raise — Step Functions should continue even if alert fails
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Failed to alert on loader failure"}),
        }
