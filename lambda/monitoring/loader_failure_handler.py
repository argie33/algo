#!/usr/bin/env python3

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Loaders that are CRITICAL - pipeline halts if they fail (FAIL-CLOSED)
# These loaders block all downstream operations and are essential for data completeness
CRITICAL_LOADERS = {
    "stock_prices_daily",  # Blocks: technicals, buy_sell, signals, scores
    "stock_symbols",  # Reference data; blocks price loading
    "technical_data_daily",  # Blocks: buy_sell_daily signal generation (Phase 5)
    # NOTE: swing_trader_scores is optional enrichment (legacy), not critical for core signals
}


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Log loader failure and decide whether to halt (fail-closed) or continue (fail-open).

    CRITICAL LOADERS (FAIL-CLOSED):
    - stock_prices_daily: All downstream loaders depend on prices
    - stock_symbols: Reference data required for price loading
    - technical_data_daily: Blocks buy_sell_daily signal generation (Phase 5)

    NON-CRITICAL LOADERS (FAIL-OPEN):
    - sector_ranking, algo_metrics_daily, etc.: Graceful degradation OK
    """
    try:
        loader_name = event.get("loader_name", "unknown")
        error_type = event.get("error", "unknown")
        error_message = event.get("error_message", "")
        is_critical = event.get("is_critical_loader", loader_name in CRITICAL_LOADERS)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Log the failure
        degradation_mode = "FAIL-CLOSED (halting pipeline)" if is_critical else "FAIL-OPEN (graceful degradation)"
        logger.warning(
            f"Loader failure [{degradation_mode}]: loader={loader_name} error={error_type} message={error_message}"
        )

        # Publish CloudWatch metric for visibility
        cloudwatch.put_metric_data(
            Namespace="Algo/DataLoading",
            MetricData=[
                {
                    "MetricName": "LoaderFailure",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": "LoaderName", "Value": loader_name},
                        {"Name": "ErrorType", "Value": error_type},
                        {
                            "Name": "Mode",
                            "Value": "FailClosed" if is_critical else "FailOpen",
                        },
                    ],
                }
            ],
        )

        # Alert on any loader failure
        alert_message = (
            f"LOADER FAILURE [{degradation_mode}]\n"
            f"Loader: {loader_name}\n"
            f"Error: {error_type}\n"
            f"Message: {error_message}\n"
            f"Time: {timestamp}\n"
        )

        if is_critical:
            alert_message += (
                f"\nPipeline is HALTING because {loader_name} is critical.\n"
                f"Reason: {loader_name} failure prevents reliable data loading.\n"
                "Action: Investigate and fix the underlying issue."
            )
        else:
            alert_message += (
                "\nPipeline is continuing with graceful degradation.\nSome data may be incomplete or stale."
            )

        sns_topic = os.getenv("SNS_ALERT_TOPIC_ARN")
        if sns_topic:
            try:
                sns.publish(
                    TopicArn=sns_topic,
                    Subject=f"[{'CRITICAL' if is_critical else 'WARNING'}] Loader Failure: {loader_name}",
                    Message=alert_message,
                )
            except Exception as e:
                logger.error(f"Failed to send SNS alert: {e}")

        # For critical loaders, FAIL the handler so Step Functions halts the pipeline
        # For non-critical loaders, SUCCEED so pipeline continues
        if is_critical:
            logger.error(f"CRITICAL LOADER {loader_name} FAILED - Halting pipeline")
            raise Exception(
                f"Critical loader {loader_name} failed. Pipeline halted to prevent trading on incomplete data."
            )

        # Non-critical loader: return success for graceful degradation
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Non-critical loader failure - pipeline continuing",
                    "loader_name": loader_name,
                    "timestamp": timestamp,
                    "critical": False,
                }
            ),
        }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error in loader_failure_handler: {e}", exc_info=True)
        # Re-raise to propagate the error to Step Functions (failing the pipeline for critical loaders)
        raise
