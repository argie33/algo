#!/usr/bin/env python3
"""
Lambda-based Alpaca SIP verification that runs inside VPC with direct DB access.

This Lambda can be invoked to verify Alpaca SIP data loaded successfully.
Usage from CLI:
    aws lambda invoke --function-name algo-db-migration-dev \
        --payload '{"action": "verify_alpaca_sip"}' output.json
"""

import json
import sys
import os
from typing import Any

# Add lambda path for imports
sys.path.insert(0, "/var/task")


def verify_alpaca_sip() -> dict[str, Any]:
    """Verify Alpaca SIP data in stock_prices_daily table."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cursor:
            # Query 1: Alpaca SIP symbol count and rows
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as alpaca_symbols,
                    COUNT(*) as alpaca_rows,
                    MAX(date) as latest_date,
                    MIN(date) as earliest_date
                FROM stock_prices_daily
                WHERE source = 'alpaca'
            """)

            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "status": "NO_DATA",
                    "message": "No Alpaca SIP data found in stock_prices_daily",
                    "symbols": 0,
                    "rows": 0,
                }

            alpaca_symbols, alpaca_rows, latest_date, earliest_date = row

            # Query 2: Sample of symbols
            cursor.execute("""
                SELECT DISTINCT symbol
                FROM stock_prices_daily
                WHERE source = 'alpaca'
                ORDER BY symbol
                LIMIT 5
            """)

            sample_symbols = [r[0] for r in cursor.fetchall()]

            # Query 3: OHLCV completeness
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN open IS NOT NULL THEN 1 END) as open_non_null,
                    COUNT(CASE WHEN high IS NOT NULL THEN 1 END) as high_non_null,
                    COUNT(CASE WHEN low IS NOT NULL THEN 1 END) as low_non_null,
                    COUNT(CASE WHEN close IS NOT NULL THEN 1 END) as close_non_null,
                    COUNT(CASE WHEN volume IS NOT NULL THEN 1 END) as volume_non_null
                FROM stock_prices_daily
                WHERE source = 'alpaca'
            """)

            ohlcv = cursor.fetchone()

            return {
                "status": "VERIFIED",
                "message": f"Alpaca SIP data verified: {alpaca_symbols} symbols, {alpaca_rows} rows",
                "symbols": alpaca_symbols,
                "rows": alpaca_rows,
                "date_range": {"earliest": str(earliest_date), "latest": str(latest_date)},
                "sample_symbols": sample_symbols,
                "ohlcv_completeness": {
                    "open": ohlcv[0],
                    "high": ohlcv[1],
                    "low": ohlcv[2],
                    "close": ohlcv[3],
                    "volume": ohlcv[4],
                },
            }

    except Exception as e:
        return {"status": "ERROR", "message": str(e), "error_type": type(e).__name__}


def verify_growth_score() -> dict[str, Any]:
    """Verify growth_score and rs_percentile data in stock_scores table."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cursor:
            # Query: Overall statistics
            cursor.execute("""
                SELECT
                    COUNT(*) as total_rows,
                    COUNT(growth_score) as growth_score_non_null,
                    COUNT(rs_percentile) as rs_percentile_non_null,
                    MIN(growth_score) as min_growth,
                    MAX(growth_score) as max_growth,
                    MIN(rs_percentile) as min_rs,
                    MAX(rs_percentile) as max_rs
                FROM stock_scores
            """)

            row = cursor.fetchone()
            total, growth_non_null, rs_non_null, min_g, max_g, min_rs, max_rs = row

            if total == 0:
                return {"status": "NO_DATA", "message": "stock_scores table is empty"}

            growth_pct = 100 * growth_non_null / max(1, total)
            rs_pct = 100 * rs_non_null / max(1, total)

            return {
                "status": "VERIFIED" if growth_pct > 90 and rs_pct > 90 else "PARTIAL",
                "message": f"growth_score: {growth_pct:.1f}%, rs_percentile: {rs_pct:.1f}%",
                "total_symbols": total,
                "growth_score": {"non_null_count": growth_non_null, "percentage": growth_pct, "range": [min_g, max_g]},
                "rs_percentile": {"non_null_count": rs_non_null, "percentage": rs_pct, "range": [min_rs, max_rs]},
            }

    except Exception as e:
        return {"status": "ERROR", "message": str(e), "error_type": type(e).__name__}


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda handler to verify Alpaca SIP and growth_score data."""
    action = event.get("action", "verify_both")

    results = {}

    if action in ["verify_alpaca_sip", "verify_both"]:
        results["alpaca_sip"] = verify_alpaca_sip()

    if action in ["verify_growth_score", "verify_both"]:
        results["growth_score"] = verify_growth_score()

    return {"statusCode": 200, "body": json.dumps(results, default=str, indent=2)}


if __name__ == "__main__":
    # For local testing
    result = lambda_handler({"action": "verify_both"}, None)
    print(json.dumps(result, indent=2, default=str))
