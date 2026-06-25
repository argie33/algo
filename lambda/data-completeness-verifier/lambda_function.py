#!/usr/bin/env python3
"""Lambda Function: Verify production data loading completeness.

Triggered by: Manual invocation or EventBridge schedule
Purpose: Verify price data meets Phase 1 thresholds from inside VPC
Returns: CloudWatch metrics and detailed status
Uses LambdaHandler base class for standardized pattern.
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from base_handler import LambdaHandler, create_lambda_handler

logger = logging.getLogger()


class DataCompletenessHandler(LambdaHandler):
    """Verifies production data loading completeness."""

    def handle(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """Handle data completeness verification."""
        import boto3

        from algo.infrastructure import MarketCalendar

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT MAX(date) FROM price_daily")
            row = cursor.fetchone()
            max_date = row[0] if row and row[0] is not None else None

            if not max_date:
                return {
                    "statusCode": 200,
                    "result": "FAILED",
                    "reason": "price_daily table is empty",
                    "phase1_halted": True,
                }

            today = date.today()
            last_trading_day = today - timedelta(days=1)
            while last_trading_day > today - timedelta(days=10):
                if MarketCalendar.is_trading_day(last_trading_day):
                    break
                last_trading_day -= timedelta(days=1)

            if max_date < last_trading_day:
                return {
                    "statusCode": 200,
                    "result": "FAILED",
                    "reason": f"Price data stale: {max_date} vs {last_trading_day}",
                    "phase1_halted": True,
                }

            cursor.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (max_date,),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise ValueError(f"Today's symbol count returned NULL for {max_date} — cannot validate data completeness")
            symbols_today = int(row[0])

            cursor.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
                "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
                (max_date,),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise ValueError("Prior day symbol count returned NULL — cannot validate coverage comparison")
            symbols_prior = int(row[0])

            coverage_pct = (symbols_today / max(symbols_prior, 1)) * 100

            min_symbols = 5000
            min_coverage = 75.0
            passes = symbols_today >= min_symbols and coverage_pct >= min_coverage

            cloudwatch = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cloudwatch.put_metric_data(
                Namespace="AlgoTrading",
                MetricData=[
                    {
                        "MetricName": "PriceCoverage_Symbols",
                        "Value": symbols_today,
                        "Unit": "Count",
                    },
                    {
                        "MetricName": "PriceCoverage_Percent",
                        "Value": coverage_pct,
                        "Unit": "Percent",
                    },
                    {
                        "MetricName": "Phase1_Pass",
                        "Value": 1.0 if passes else 0.0,
                        "Unit": "Count",
                    },
                ],
            )

            if passes:
                logger.info(f"Phase 1 PASSED: {symbols_today} symbols, {coverage_pct:.1f}% coverage")
                return {
                    "statusCode": 200,
                    "result": "SUCCESS",
                    "phase1_passes": True,
                    "symbols": symbols_today,
                    "coverage_percent": round(coverage_pct, 1),
                    "max_date": str(max_date),
                }
            else:
                logger.error(f"Phase 1 FAILED: {symbols_today} symbols, {coverage_pct:.1f}% coverage")
                reason = []
                if symbols_today < min_symbols:
                    reason.append(f"symbols {symbols_today} < {min_symbols}")
                if coverage_pct < min_coverage:
                    reason.append(f"coverage {coverage_pct:.1f}% < {min_coverage}%")

                return {
                    "statusCode": 200,
                    "result": "FAILED",
                    "phase1_halted": True,
                    "reason": ", ".join(reason),
                    "symbols": symbols_today,
                    "coverage_percent": round(coverage_pct, 1),
                    "max_date": str(max_date),
                }

        finally:
            cursor.close()
            conn.close()

    def invoke(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """Override invoke to return raw dict (not standardized response format)."""
        try:
            return self.handle(event, context)
        except Exception as e:
            logger.exception(f"Unhandled exception: {e}")
            return {"statusCode": 500, "result": "ERROR", "error": str(e)}


lambda_handler = create_lambda_handler(DataCompletenessHandler)


if __name__ == "__main__":
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))
