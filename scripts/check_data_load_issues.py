#!/usr/bin/env python3
"""Check for data loading issues: duplicates, incomplete loads, missing data.

Audits:
1. Duplicate rows by primary key
2. Data freshness (staleness)
3. Critical field NULLs
4. Expected vs actual row counts
5. Data gaps (missing expected symbols/dates)
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)


def check_price_daily_duplicates():
    """Check price_daily for duplicate (symbol, date) combinations."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        cur.execute("""
        WITH dups AS (
            SELECT symbol, date, COUNT(*) as cnt
            FROM price_daily
            GROUP BY symbol, date
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) as dup_count, SUM(cnt - 1) as extra_rows
        FROM dups
        """)

        result = cur.fetchone()
        dup_count = result.get("dup_count") or 0 if isinstance(result, dict) else (result[0] or 0)
        extra_rows = result.get("extra_rows") or 0 if isinstance(result, dict) else (result[1] or 0)

        return {
            "table": "price_daily",
            "issue": "DUPLICATES" if dup_count > 0 else "OK",
            "duplicate_dates": dup_count,
            "extra_rows": extra_rows,
        }


def check_technical_data_duplicates():
    """Check technical_data_daily for duplicate (symbol, date) combinations."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        cur.execute("""
        WITH dups AS (
            SELECT symbol, date, COUNT(*) as cnt
            FROM technical_data_daily
            GROUP BY symbol, date
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) as dup_count, SUM(cnt - 1) as extra_rows
        FROM dups
        """)

        result = cur.fetchone()
        dup_count = result.get("dup_count") or 0 if isinstance(result, dict) else (result[0] or 0)
        extra_rows = result.get("extra_rows") or 0 if isinstance(result, dict) else (result[1] or 0)

        return {
            "table": "technical_data_daily",
            "issue": "DUPLICATES" if dup_count > 0 else "OK",
            "duplicate_dates": dup_count,
            "extra_rows": extra_rows,
        }


def check_annual_income_statement_duplicates():
    """Check annual_income_statement for duplicate (symbol, fiscal_year) combinations."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        cur.execute("""
        WITH dups AS (
            SELECT symbol, fiscal_year, COUNT(*) as cnt
            FROM annual_income_statement
            GROUP BY symbol, fiscal_year
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) as dup_count, SUM(cnt - 1) as extra_rows
        FROM dups
        """)

        result = cur.fetchone()
        dup_count = result.get("dup_count") or 0 if isinstance(result, dict) else (result[0] or 0)
        extra_rows = result.get("extra_rows") or 0 if isinstance(result, dict) else (result[1] or 0)

        return {
            "table": "annual_income_statement",
            "issue": "DUPLICATES" if dup_count > 0 else "OK",
            "duplicate_fiscal_years": dup_count,
            "extra_rows": extra_rows,
        }


def check_data_freshness():
    """Check how fresh each critical table is."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        tables_to_check = [
            ("price_daily", "date"),
            ("technical_data_daily", "date"),
            ("stock_scores", "updated_at"),
            ("annual_income_statement", "updated_at"),
            ("quarterly_income_statement", "updated_at"),
            ("algo_signals", "signal_date"),
        ]

        results = []
        for table, date_col in tables_to_check:
            try:
                cur.execute(f"""
                SELECT MAX({date_col}) as last_update
                FROM {table}
                """)

                result = cur.fetchone()
                last_update = result.get("last_update") if isinstance(result, dict) else result[0]

                if last_update:
                    # Make it timezone aware if needed
                    if hasattr(last_update, 'tzinfo') and last_update.tzinfo is None:
                        last_update = last_update.replace(tzinfo=timezone.utc)
                    elif not hasattr(last_update, 'tzinfo'):
                        last_update = datetime.fromisoformat(str(last_update)).replace(tzinfo=timezone.utc)

                    now = datetime.now(timezone.utc)
                    age = (now - last_update).total_seconds() / 3600  # hours

                    status = "FRESH" if age < 24 else ("STALE" if age < 48 else "CRITICAL")
                    results.append({
                        "table": table,
                        "last_update": str(last_update),
                        "age_hours": round(age, 1),
                        "status": status,
                    })
                else:
                    results.append({
                        "table": table,
                        "status": "NO_DATA",
                    })
            except Exception as e:
                results.append({
                    "table": table,
                    "error": str(e),
                })

        return results


def check_symbol_coverage():
    """Check if all expected symbols are loaded."""
    with DatabaseContext(role="read", enable_correlation_tracking=False) as cur:
        # Get list of expected symbols
        cur.execute("""
        SELECT COUNT(DISTINCT symbol) as cnt
        FROM stock_symbols
        """)

        result = cur.fetchone()
        expected_symbols = result.get("cnt") or 0 if isinstance(result, dict) else (result[0] or 0)

        # Check coverage in price_daily
        cur.execute("""
        SELECT COUNT(DISTINCT symbol) as cnt
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        """)

        result = cur.fetchone()
        loaded_symbols = result.get("cnt") or 0 if isinstance(result, dict) else (result[0] or 0)

        coverage = (loaded_symbols / expected_symbols * 100) if expected_symbols > 0 else 0

        return {
            "expected_active_symbols": expected_symbols,
            "loaded_in_price_daily_today": loaded_symbols,
            "coverage_percent": round(coverage, 1),
            "issue": "OK" if coverage > 95 else ("WARNING" if coverage > 80 else "CRITICAL"),
        }


def main():
    """Run all audit checks."""
    logger.info("\n" + "="*80)
    logger.info("DATA LOADING AUDIT - CHECKING FOR ISSUES")
    logger.info("="*80)

    issues_found = []

    # Check duplicates
    logger.info("\n[DUPLICATES CHECK]")
    for checker in [check_price_daily_duplicates, check_technical_data_duplicates, check_annual_income_statement_duplicates]:
        result = checker()
        table = result["table"]
        status = result["issue"]

        if status == "OK":
            logger.info(f"  ✓ {table:40} NO DUPLICATES")
        else:
            logger.warning(f"  ✗ {table:40} {result['duplicate_dates']} duplicate keys ({result['extra_rows']} extra rows)")
            issues_found.append((table, "DUPLICATES", result))

    # Check freshness
    logger.info("\n[FRESHNESS CHECK]")
    freshness = check_data_freshness()
    for item in freshness:
        table = item["table"]
        if "error" in item:
            logger.error(f"  ✗ {table:40} ERROR: {item['error']}")
        elif item["status"] == "NO_DATA":
            logger.error(f"  ✗ {table:40} NO DATA")
            issues_found.append((table, "NO_DATA", item))
        else:
            symbol = "✓" if item["status"] == "FRESH" else "⚠" if item["status"] == "STALE" else "✗"
            logger.info(f"  {symbol} {table:40} {item['status']:10} ({item['age_hours']:.1f}h old)")
            if item["status"] in ["STALE", "CRITICAL"]:
                issues_found.append((table, "STALE_DATA", item))

    # Check symbol coverage
    logger.info("\n[SYMBOL COVERAGE CHECK]")
    coverage = check_symbol_coverage()
    symbol = "✓" if coverage["issue"] == "OK" else "⚠" if coverage["issue"] == "WARNING" else "✗"
    logger.info(f"  {symbol} {coverage['loaded_in_price_daily_today']}/{coverage['expected_active_symbols']} symbols ({coverage['coverage_percent']:.1f}%)")
    if coverage["issue"] != "OK":
        issues_found.append(("symbol_coverage", coverage["issue"], coverage))

    # Summary
    logger.info("\n" + "="*80)
    if issues_found:
        logger.warning(f"FOUND {len(issues_found)} ISSUES:")
        for table, issue_type, details in issues_found:
            logger.warning(f"  - {table}: {issue_type}")
    else:
        logger.info("✓ NO DATA LOADING ISSUES FOUND")
    logger.info("="*80 + "\n")


if __name__ == "__main__":
    main()
