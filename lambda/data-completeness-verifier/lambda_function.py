#!/usr/bin/env python3
"""
Lambda Function: Verify production data loading completeness.

Triggered by: Manual invocation or EventBridge schedule
Purpose: Verify price data meets Phase 1 thresholds from inside VPC
Returns: CloudWatch metrics and detailed status

Invoke with: aws lambda invoke --function-name algo-data-completeness-verifier output.json
"""

import json
import logging
import os
from datetime import date, timedelta


logger = logging.getLogger()
logger.setLevel(logging.INFO)




def lambda_handler(event, context):
    """Main Lambda handler for data completeness verification."""
    try:
        import psycopg2

        from algo.infrastructure import MarketCalendar

        # Connect to RDS (Lambda runs in VPC with RDS access)
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME"),
            connect_timeout=10
        )

        cursor = conn.cursor()

        # Verify Phase 1 thresholds
        cursor.execute("SELECT MAX(date) FROM price_daily")
        max_date = cursor.fetchone()[0]

        if not max_date:
            return {
                "statusCode": 200,
                "result": "FAILED",
                "reason": "price_daily table is empty",
                "phase1_halted": True
            }

        # Get expected trading day
        today = date.today()
        last_trading_day = today - timedelta(days=1)
        while last_trading_day > today - timedelta(days=10):
            if MarketCalendar.is_trading_day(last_trading_day):
                break
            last_trading_day -= timedelta(days=1)

        # Check staleness
        if max_date < last_trading_day:
            return {
                "statusCode": 200,
                "result": "FAILED",
                "reason": f"Price data stale: {max_date} vs {last_trading_day}",
                "phase1_halted": True
            }

        # Check coverage
        cursor.execute(
            "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
            (max_date,)
        )
        symbols_today = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
            "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
            (max_date,)
        )
        symbols_prior = cursor.fetchone()[0] or symbols_today

        coverage_pct = (symbols_today / max(symbols_prior, 1)) * 100

        # Phase 1 thresholds
        min_symbols = 5000
        min_coverage = 75.0

        passes = symbols_today >= min_symbols and coverage_pct >= min_coverage

        # Publish CloudWatch metric
        import boto3
        cloudwatch = boto3.client("cloudwatch")

        cloudwatch.put_metric_data(
            Namespace="AlgoTrading",
            MetricData=[
                {
                    "MetricName": "PriceCoverage_Symbols",
                    "Value": symbols_today,
                    "Unit": "Count"
                },
                {
                    "MetricName": "PriceCoverage_Percent",
                    "Value": coverage_pct,
                    "Unit": "Percent"
                },
                {
                    "MetricName": "Phase1_Pass",
                    "Value": 1.0 if passes else 0.0,
                    "Unit": "Count"
                }
            ]
        )

        cursor.close()
        conn.close()

        if passes:
            logger.info(f"Phase 1 PASSED: {symbols_today} symbols, {coverage_pct:.1f}% coverage")
            return {
                "statusCode": 200,
                "result": "SUCCESS",
                "phase1_passes": True,
                "symbols": symbols_today,
                "coverage_percent": round(coverage_pct, 1),
                "max_date": str(max_date)
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
                "max_date": str(max_date)
            }

    except Exception as e:
        logger.error(f"Verification error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "result": "ERROR",
            "error": str(e)
        }


if __name__ == "__main__":
    # Local testing
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))
