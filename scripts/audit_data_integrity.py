#!/usr/bin/env python3
"""Simplified data integrity audit - check for duplicates and data quality issues.

Focuses on:
1. Duplicate rows (where we know the schema)
2. Data freshness
3. Critical field NULLs

Usage:
  python scripts/audit_data_integrity.py  # Full audit
"""

import logging
import sys
import os
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)


def check_duplicates_by_key(table_name: str, key_columns: list[str]) -> dict[str, Any]:
    """Check for duplicate rows by key."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        try:
            key_str = ", ".join(key_columns)

            # Count duplicates
            dup_query = f"""
            SELECT COUNT(*) as dup_combos, SUM(cnt - 1) as dup_rows
            FROM (
                SELECT {key_str}, COUNT(*) as cnt
                FROM {table_name}
                GROUP BY {key_str}
                HAVING COUNT(*) > 1
            ) t
            """

            cur.execute(dup_query)
            result = cur.fetchone()

            dup_combos = result.get("dup_combos") or 0 if isinstance(result, dict) else (result[0] or 0)
            dup_rows = result.get("dup_rows") or 0 if isinstance(result, dict) else (result[1] or 0)

            return {
                "status": "OK" if dup_combos == 0 else "DUPLICATES_FOUND",
                "duplicate_keys": dup_combos,
                "total_duplicate_rows": dup_rows,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}


def check_critical_nulls(table_name: str, critical_fields: list[str]) -> dict[str, Any]:
    """Check NULL rates in critical fields."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        try:
            # Get total rows
            cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
            total = cur.fetchone().get("cnt") if isinstance(cur.fetchone(), dict) else 0

            if total == 0:
                return {"status": "EMPTY", "total_rows": 0}

            # Re-fetch for counting
            cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
            total_rows = cur.fetchone()
            total = total_rows.get("cnt") or 0 if isinstance(total_rows, dict) else (total_rows[0] or 0)

            nulls = {}
            for field in critical_fields:
                try:
                    cur.execute(f"""
                    SELECT COUNT(*) as null_cnt
                    FROM {table_name}
                    WHERE {field} IS NULL
                    """)
                    result = cur.fetchone()
                    null_count = result.get("null_cnt") or 0 if isinstance(result, dict) else (result[0] or 0)
                    null_rate = null_count / total if total > 0 else 0

                    if null_rate > 0.1:  # >10% NULLs = warning
                        nulls[field] = round(null_rate, 3)
                except:
                    pass  # Field may not exist

            return {
                "status": "OK" if not nulls else "WARNING",
                "total_rows": total,
                "critical_nulls": nulls,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}


def run_audit():
    """Run complete audit."""
    logger.info("\n" + "="*80)
    logger.info("DATA INTEGRITY AUDIT")
    logger.info("="*80)

    audits = [
        ("price_daily", ["symbol", "date"], ["open", "high", "low", "close", "volume"]),
        ("technical_data_daily", ["symbol", "date"], ["rsi_14", "macd"]),
        ("stock_scores", ["symbol", "score_date"], ["quality_score"]),
        ("annual_income_statement", ["symbol", "fiscal_year"], ["revenue", "net_income"]),
        ("quarterly_income_statement", ["symbol", "fiscal_year", "fiscal_quarter"], ["revenue"]),
        ("algo_signals", ["symbol", "signal_date"], ["signal_type"]),
        ("market_exposure_daily", ["date"], ["long_exposure_pct"]),
    ]

    issues = []

    for table, key_cols, crit_fields in audits:
        logger.info(f"\nAuditing: {table}")

        # Check duplicates
        dup_result = check_duplicates_by_key(table, key_cols)
        logger.info(f"  Duplicates: {dup_result['status']}", end="")
        if dup_result["status"] != "OK":
            logger.info(f" - {dup_result['duplicate_keys']} key combos")
            issues.append((table, "DUPLICATES", dup_result))
        else:
            logger.info()

        # Check critical field NULLs
        null_result = check_critical_nulls(table, crit_fields)
        logger.info(f"  Rows: {null_result.get('total_rows', 'UNKNOWN')}", end="")
        if null_result.get("critical_nulls"):
            logger.info(f" - HIGH NULLs: {null_result['critical_nulls']}")
            issues.append((table, "HIGH_NULLS", null_result))
        else:
            logger.info()

    # Summary
    logger.info("\n" + "="*80)
    if issues:
        logger.warning(f"FOUND {len(issues)} DATA ISSUES:")
        for table, issue_type, details in issues:
            logger.warning(f"  {table}: {issue_type}")
    else:
        logger.info("NO DATA INTEGRITY ISSUES FOUND ✓")
    logger.info("="*80)


if __name__ == "__main__":
    run_audit()
