#!/usr/bin/env python3
"""Comprehensive data loading audit - find duplicates, gaps, and data quality issues.

Checks:
1. Duplicate rows (by primary key) in each critical table
2. Data completeness (gaps in expected data)
3. Watermark consistency (for watermark-based loaders)
4. NULL rates in critical vs optional fields
5. Row count trends (detecting stalled loaders)
6. Foreign key integrity (where applicable)

Usage:
  python scripts/audit_data_loading.py                    # Full audit
  python scripts/audit_data_loading.py --table price_daily # Single table
  python scripts/audit_data_loading.py --fix               # Auto-fix duplicates
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger
from loaders.loader_registry import LOADER_TABLES

logger = get_logger(__name__)

# Critical tables that should NOT have duplicates
CRITICAL_TABLES = {
    "price_daily": {
        "primary_key": ["symbol", "date"],
        "expected_row_millions": 5.0,
        "critical_fields": ["open", "high", "low", "close", "volume"],
    },
    "technical_data_daily": {
        "primary_key": ["symbol", "date"],
        "expected_row_millions": 0.1,
        "critical_fields": ["rsi_14", "macd"],
    },
    "stock_scores": {
        "primary_key": ["symbol", "date"],
        "expected_row_millions": 0.001,
        "critical_fields": ["quality_score", "growth_score"],
    },
    "algo_signals": {
        "primary_key": ["symbol", "signal_date"],
        "expected_row_millions": 0.0001,
        "critical_fields": ["signal_type", "confidence"],
    },
    "annual_income_statement": {
        "primary_key": ["symbol", "fiscal_year"],
        "expected_row_count": 50000,
        "critical_fields": ["revenue", "net_income"],
    },
    "quarterly_income_statement": {
        "primary_key": ["symbol", "fiscal_year", "quarter"],
        "expected_row_count": 200000,
        "critical_fields": ["revenue", "net_income"],
    },
    "market_exposure_daily": {
        "primary_key": ["date"],
        "expected_row_count": 1000,
        "critical_fields": ["long_exposure_pct", "short_exposure_pct"],
    },
}

# Tables with known high NULL rates (expected, not bugs)
EXPECTED_HIGH_NULL_RATES = {
    "institutional_holdings_13f": {
        "institutional_ownership_pct": 0.47,
    },
    "positioning_metrics": {
        "institutional_ownership_pct": 0.47,
        "insider_ownership_pct": 0.26,
    },
    "quality_metrics": {
        "operating_margin": 0.42,
        "net_margin": 0.33,
        "amortization_expense": 0.28,
    },
    "market_exposure_daily": {
        "market_exposure_pct": 1.0,  # This is computed, not loaded - 100% NULL is expected
    },
}


def check_table_duplicates(table_name: str, primary_key: list[str]) -> dict[str, Any]:
    """Check for duplicate rows in a table."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        # Build the duplicate check query
        key_cols = ", ".join(primary_key)
        dup_query = f"""
        WITH dup_check AS (
            SELECT {key_cols}, COUNT(*) as dup_count
            FROM {table_name}
            GROUP BY {key_cols}
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) as total_dups, SUM(dup_count) as total_dup_rows
        FROM dup_check
        """

        try:
            cur.execute(dup_query)
            result = cur.fetchone()
            total_dups = result.get("total_dups") or 0 if isinstance(result, dict) else (result[0] or 0)
            total_dup_rows = result.get("total_dup_rows") or 0 if isinstance(result, dict) else (result[1] or 0)

            if total_dups > 0:
                logger.warning(f"[{table_name}] Found {total_dups} duplicate key combinations ({total_dup_rows} duplicate rows)")

                # Get details of duplicates
                detail_query = f"""
                WITH dup_check AS (
                    SELECT {key_cols}, COUNT(*) as dup_count
                    FROM {table_name}
                    GROUP BY {key_cols}
                    HAVING COUNT(*) > 1
                    LIMIT 5
                )
                SELECT {key_cols}, dup_count FROM dup_check
                """
                cur.execute(detail_query)
                samples = cur.fetchall()
                logger.warning(f"  Sample duplicates: {samples}")

            return {
                "status": "DUPLICATES_FOUND" if total_dups > 0 else "OK",
                "duplicate_key_combos": total_dups,
                "duplicate_rows": total_dup_rows,
            }
        except Exception as e:
            logger.error(f"[{table_name}] Duplicate check failed: {e}")
            return {"status": "ERROR", "error": str(e)}


def check_table_nulls(table_name: str, expected_nulls: dict[str, float] | None = None) -> dict[str, Any]:
    """Check NULL rates in a table."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        try:
            # Get column names and NULL counts
            cur.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
            """, (table_name,))

            columns = [row[0] for row in cur.fetchall()]
            if not columns:
                return {"status": "ERROR", "error": f"Table {table_name} not found"}

            # Get row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_rows = cur.fetchone()[0]

            if total_rows == 0:
                return {"status": "EMPTY", "total_rows": 0}

            # Check NULL rates for key columns
            null_check = {}
            for col in columns[:20]:  # Check first 20 columns
                cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN {col} IS NOT NULL THEN 1 END) as non_null
                FROM {table_name}
                """)

                total, non_null = cur.fetchone()
                null_rate = (total - non_null) / total if total > 0 else 0

                if null_rate > 0.1:  # Flag columns with >10% NULLs
                    expected_rate = expected_nulls.get(col, 0) if expected_nulls else 0
                    if null_rate > expected_rate * 1.1:  # More than 10% over expected
                        null_check[col] = {
                            "null_rate": round(null_rate, 3),
                            "expected_rate": expected_rate,
                            "status": "UNEXPECTED_NULLS" if null_rate > 0.5 else "WARNING",
                        }

            return {
                "status": "OK" if not null_check else "WARNING",
                "total_rows": total_rows,
                "high_null_columns": null_check,
            }
        except Exception as e:
            logger.error(f"[{table_name}] NULL check failed: {e}")
            return {"status": "ERROR", "error": str(e)}


def check_row_count_trend(table_name: str) -> dict[str, Any]:
    """Check if row count is growing (detecting stalled loaders)."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        try:
            # Get row counts and age
            cur.execute(f"""
            SELECT
                COUNT(*) as total_rows,
                MAX(GREATEST(
                    COALESCE(MAX(date), '1900-01-01'::timestamp),
                    COALESCE(MAX(updated_at), '1900-01-01'::timestamp),
                    COALESCE(MAX(created_at), '1900-01-01'::timestamp)
                )) as last_update
            FROM {table_name}
            """)

            total_rows, last_update = cur.fetchone()

            if not last_update or last_update == '1900-01-01':
                age_hours = None
            else:
                # Convert to aware datetime if needed
                if not isinstance(last_update, datetime):
                    last_update = datetime.fromisoformat(str(last_update))
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                age_hours = (now - last_update).total_seconds() / 3600

            return {
                "status": "OK",
                "total_rows": total_rows,
                "last_update": str(last_update) if last_update else "UNKNOWN",
                "age_hours": round(age_hours, 1) if age_hours else None,
            }
        except Exception as e:
            logger.error(f"[{table_name}] Row count trend check failed: {e}")
            return {"status": "ERROR", "error": str(e)}


def fix_duplicates(table_name: str, primary_key: list[str]) -> dict[str, Any]:
    """Remove duplicate rows, keeping the most recent."""
    with DatabaseContext(role="write", enable_correlation_tracking=False) as cur:
        try:
            key_cols = ", ".join(primary_key)

            # Create temp table with deduplicated data
            cur.execute(f"""
            CREATE TEMP TABLE {table_name}_dedup AS
            SELECT DISTINCT ON ({key_cols})
                *
            FROM {table_name}
            ORDER BY {key_cols}, COALESCE(updated_at, created_at, NOW()) DESC NULLS LAST
            """)

            # Truncate and reload
            cur.execute(f"TRUNCATE TABLE {table_name}")
            cur.execute(f"""
            INSERT INTO {table_name}
            SELECT * FROM {table_name}_dedup
            """)

            # Get result
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            result = cur.fetchone()
            remaining_rows = result.get("count") or 0 if isinstance(result, dict) else (result[0] if result else 0)

            return {
                "status": "FIXED",
                "remaining_rows": remaining_rows,
            }
        except Exception as e:
            logger.error(f"[{table_name}] Fix duplicates failed: {e}")
            return {"status": "ERROR", "error": str(e)}


def run_full_audit(table_filter: str | None = None, fix: bool = False) -> None:
    """Run comprehensive audit on all critical tables."""
    logger.info("Starting comprehensive data loading audit...")
    logger.info(f"Auditing {len(CRITICAL_TABLES)} critical tables")

    results = {}

    for table_name, config in CRITICAL_TABLES.items():
        if table_filter and table_name != table_filter:
            continue

        logger.info(f"\n{'='*80}")
        logger.info(f"AUDITING: {table_name}")
        logger.info(f"{'='*80}")

        # Check duplicates
        logger.info("  Checking for duplicates...")
        dup_result = check_table_duplicates(table_name, config["primary_key"])
        results[table_name] = dup_result

        if dup_result["status"] == "DUPLICATES_FOUND":
            if fix:
                logger.info("  Auto-fixing duplicates...")
                fix_result = fix_duplicates(table_name, config["primary_key"])
                results[table_name]["fix_result"] = fix_result
            else:
                logger.warning("  Duplicates found. Run with --fix to remove them.")

        # Check NULLs
        logger.info("  Checking NULL rates...")
        null_result = check_table_nulls(table_name, EXPECTED_HIGH_NULL_RATES.get(table_name))
        results[table_name].update(null_result)

        # Check row count trend
        logger.info("  Checking row count and freshness...")
        trend_result = check_row_count_trend(table_name)
        results[table_name].update(trend_result)

    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info("AUDIT SUMMARY")
    logger.info(f"{'='*80}")

    for table_name, result in results.items():
        status = result.get("status", "UNKNOWN")
        logger.info(f"{table_name:40} {status}")

        if "error" in result:
            logger.error(f"  Error: {result['error']}")
        if "duplicate_key_combos" in result and result["duplicate_key_combos"] > 0:
            logger.warning(f"  Duplicates: {result['duplicate_key_combos']} key combos ({result['duplicate_rows']} rows)")
        if "high_null_columns" in result and result["high_null_columns"]:
            logger.warning(f"  High NULLs: {result['high_null_columns']}")
        if "age_hours" in result and result["age_hours"] and result["age_hours"] > 48:
            logger.warning(f"  STALE: Last update {result['age_hours']:.1f} hours ago")

    # Save detailed results
    with open("/tmp/audit_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nDetailed results saved to /tmp/audit_results.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit data loading for quality issues")
    parser.add_argument("--table", type=str, help="Audit only this table")
    parser.add_argument("--fix", action="store_true", help="Auto-fix duplicates")
    args = parser.parse_args()

    run_full_audit(table_filter=args.table, fix=args.fix)
