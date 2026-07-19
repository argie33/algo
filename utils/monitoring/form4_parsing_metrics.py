#!/usr/bin/env python3
"""CloudWatch metrics for Form 4 parsing monitoring.

Tracks Form 4 parsing failures by error type (HTML stripping, name extraction,
ownership extraction, etc.) to enable proactive alerting on data quality issues.

LOCAL_MODE: Metrics disabled (prints to stderr instead).
AWS_MODE: Metrics sent to CloudWatch for production visibility.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Check if running in AWS/production mode
IS_LOCAL_MODE = os.getenv("LOCAL_MODE") == "1"


def put_form4_parsing_metric(
    symbol: str,
    reason: str,
    is_failure: bool = True,
    filing_type: str = "plaintext",
) -> None:
    """Emit a Form 4 parsing metric to CloudWatch.

    Tracks parsing failures by error type to enable alerting on data quality issues.

    Args:
        symbol: Stock ticker symbol
        reason: Error reason or parsing step that failed
        is_failure: True if parsing failed, False if successful
        filing_type: "plaintext" or "xbrl" to distinguish between formats
    """
    if IS_LOCAL_MODE:
        # LOCAL_MODE: Log to stderr for local debugging
        status = "FAILED" if is_failure else "OK"
        logger.debug(f"[METRIC] Form4Parsing({symbol}): {status} reason={reason} format={filing_type}")
        return

    try:
        import boto3

        cloudwatch = boto3.client("cloudwatch")

        cloudwatch.put_metric_data(
            Namespace="Algo/Form4Parsing",
            MetricData=[
                {
                    "MetricName": "ParsingFailure" if is_failure else "ParsingSuccess",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": "Symbol", "Value": symbol[:10]},  # Limit to 10 chars
                        {"Name": "FailureReason", "Value": reason[:60]},  # Limit to 60 chars
                        {"Name": "FilingFormat", "Value": filing_type},
                    ],
                }
            ],
        )
        logger.debug(f"[CLOUDWATCH] Form 4 parsing metric emitted: {symbol} {reason}")
    except Exception as e:
        # Fail gracefully - metrics are optional, don't block parsing
        logger.warning(f"Failed to emit Form 4 parsing metric: {e}")


def track_form4_parsing_error(
    symbol: str,
    error_type: str,
    error_message: str | None = None,
    filing_type: str = "plaintext",
) -> None:
    """Track a Form 4 parsing error with details for alerting.

    Common error types:
    - "html_stripping_failed": HTML preprocessing failed
    - "insider_name_extraction_failed": Could not extract insider name
    - "shares_owned_extraction_failed": Could not extract shares owned
    - "ownership_pct_extraction_failed": Could not extract ownership %
    - "transaction_extraction_failed": Could not extract transactions
    - "invalid_content": Content validation failed
    - "parsing_returned_none": Parser returned None for filing

    Args:
        symbol: Stock ticker symbol
        error_type: Classification of the error
        error_message: Optional detailed error message
        filing_type: "plaintext" or "xbrl"
    """
    reason = error_type
    if error_message:
        reason = f"{error_type}:{error_message[:30]}"

    put_form4_parsing_metric(symbol, reason, is_failure=True, filing_type=filing_type)


def track_form4_parsing_success(symbol: str, filing_type: str = "plaintext") -> None:
    """Track successful Form 4 parsing for data quality monitoring."""
    put_form4_parsing_metric(symbol, "parsing_succeeded", is_failure=False, filing_type=filing_type)
