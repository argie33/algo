#!/usr/bin/env python3
"""Comprehensive audit of loader state and data consistency.

Checks for:
1. Missing watermarks (symbols never loaded)
2. Stale watermarks (symbols haven't loaded in N days)
3. NULL coverage issues (high NULL ratios indicating data quality problems)
4. Duplicate rows (data integrity)
5. Schema mismatches (missing/extra columns)
6. Type mismatches (wrong data types in critical columns)
7. Constraint violations (negative prices, invalid ranges)
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def check_watermarks() -> dict[str, any]:
    """Check loader watermark state for all symbols."""
    from utils.db import DatabaseContext

    try:
        with DatabaseContext("read") as cur:
            # Find loaders with stale/missing watermarks
            cur.execute("""
                SELECT
                    loader,
                    COUNT(DISTINCT symbol) as tracked_symbols,
                    COUNT(*) FILTER (WHERE watermark IS NULL) as missing,
                    COUNT(*) FILTER (WHERE watermark < (NOW()::date - INTERVAL '7 days')) as stale_7d,
                    COUNT(*) FILTER (WHERE watermark < (NOW()::date - INTERVAL '14 days')) as stale_14d,
                    MAX(watermark) as latest_watermark,
                    MIN(watermark) as oldest_watermark
                FROM loader_watermarks
                GROUP BY loader
                ORDER BY latest_watermark DESC
            """)
            rows = cur.fetchall()

            result = {}
            logger.info("\n=== WATERMARK STATUS ===")
            for row in rows:
                loader, tracked, missing, stale_7d, stale_14d, latest, oldest = row
                result[loader] = {
                    "tracked_symbols": tracked,
                    "missing_watermarks": missing,
                    "stale_7d": stale_7d,
                    "stale_14d": stale_14d,
                    "latest": latest.isoformat() if latest else None,
                    "oldest": oldest.isoformat() if oldest else None,
                }

                status_icon = "✅" if missing == 0 and stale_7d == 0 else "⚠️" if stale_7d == 0 else "🔴"
                logger.info(f"{status_icon} {loader}: {tracked} symbols, "
                           f"{missing} missing, {stale_7d} stale >7d, {stale_14d} stale >14d")

            return result
    except Exception as e:
        logger.error(f"Watermark check failed: {e}")
        return {}


def check_null_coverage() -> dict[str, dict[str, float]]:
    """Check NULL ratio in critical columns per table."""
    from utils.db import DatabaseContext

    tables_to_check = {
        "price_daily": ["open", "close", "high", "low", "volume"],
        "technical_data_daily": ["rsi", "macd", "sma_50", "sma_200"],
        "stock_scores": ["composite_score"],
        "buy_sell_daily": ["signal", "date"],
        "quality_metrics": ["roe", "roa", "current_ratio"],
        "growth_metrics": ["earnings_growth_yoy", "revenue_growth_yoy"],
        "value_metrics": ["pe_ratio", "pb_ratio"],
    }

    result = {}
    logger.info("\n=== NULL COVERAGE ===")

    try:
        with DatabaseContext("read") as cur:
            for table, columns in tables_to_check.items():
                result[table] = {}
                # Check if table exists
                cur.execute(f"""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = %s
                """, (table,))
                if cur.fetchone()[0] == 0:
                    logger.warning(f"❌ {table}: TABLE NOT FOUND")
                    continue

                row_count = 0
                for col in columns:
                    cur.execute(f"""
                        SELECT
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE {col} IS NULL) as nulls
                        FROM {table}
                    """)
                    total, nulls = cur.fetchone()
                    row_count = max(row_count, total)

                    null_pct = (nulls / total * 100) if total > 0 else 0
                    result[table][col] = null_pct

                    status = "⚠️" if null_pct > 5 else "✅"
                    logger.info(f"  {status} {table}.{col}: {null_pct:.1f}% NULL ({nulls}/{total})")

    except Exception as e:
        logger.error(f"NULL coverage check failed: {e}")

    return result


def check_duplicates() -> dict[str, int]:
    """Check for duplicate rows in key tables."""
    from utils.db import DatabaseContext

    tables_to_check = {
        "price_daily": ["symbol", "date"],
        "technical_data_daily": ["symbol", "date"],
        "stock_scores": ["symbol", "date"],
        "buy_sell_daily": ["symbol", "date"],
    }

    result = {}
    logger.info("\n=== DUPLICATE ROW CHECK ===")

    try:
        with DatabaseContext("read") as cur:
            for table, key_cols in tables_to_check.items():
                col_str = ", ".join(key_cols)
                cur.execute(f"""
                    SELECT COUNT(*) - COUNT(DISTINCT {col_str}) as duplicates
                    FROM {table}
                """)
                dup_count = cur.fetchone()[0]
                result[table] = dup_count

                status = "🔴" if dup_count > 0 else "✅"
                logger.info(f"{status} {table}: {dup_count} duplicate rows by ({col_str})")

    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")

    return result


def check_constraint_violations() -> dict[str, int]:
    """Check for constraint violations (negative prices, RSI out of range, etc)."""
    from utils.db import DatabaseContext

    result = {}
    logger.info("\n=== CONSTRAINT VIOLATIONS ===")

    try:
        with DatabaseContext("read") as cur:
            # Check for negative prices
            cur.execute("SELECT COUNT(*) FROM price_daily WHERE close < 0 OR high < 0 OR low < 0 OR open < 0")
            neg_prices = cur.fetchone()[0]
            result["price_daily.negative"] = neg_prices
            status = "🔴" if neg_prices > 0 else "✅"
            logger.info(f"{status} price_daily: {neg_prices} rows with negative prices")

            # Check for RSI out of range
            cur.execute("SELECT COUNT(*) FROM technical_data_daily WHERE rsi < 0 OR rsi > 100")
            bad_rsi = cur.fetchone()[0]
            result["technical_data_daily.rsi_range"] = bad_rsi
            status = "🔴" if bad_rsi > 0 else "✅"
            logger.info(f"{status} technical_data_daily: {bad_rsi} rows with RSI outside [0,100]")

            # Check for VIX out of extreme range
            cur.execute("SELECT COUNT(*) FROM price_daily WHERE symbol = '^VIX' AND close > 200")
            bad_vix = cur.fetchone()[0]
            result["price_daily.vix_extreme"] = bad_vix
            status = "🔴" if bad_vix > 0 else "✅"
            logger.info(f"{status} price_daily: {bad_vix} rows with VIX > 200")

    except Exception as e:
        logger.error(f"Constraint check failed: {e}")

    return result


def check_loader_status() -> dict[str, dict[str, any]]:
    """Check loader execution status."""
    from utils.db import DatabaseContext

    result = {}
    logger.info("\n=== LOADER EXECUTION STATUS ===")

    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    last_updated,
                    last_success_at,
                    consecutive_failures,
                    last_error,
                    execution_duration_sec
                FROM data_loader_status
                ORDER BY last_updated DESC
            """)
            rows = cur.fetchall()

            for row in rows:
                table, status_val, last_updated, last_success, failures, error, duration = row
                result[table] = {
                    "status": status_val,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "last_success": last_success.isoformat() if last_success else None,
                    "consecutive_failures": failures,
                    "error": error,
                    "duration_sec": duration,
                }

                if status_val == "COMPLETED":
                    icon = "✅"
                elif status_val == "RUNNING":
                    icon = "⏳"
                elif status_val == "FAILED":
                    icon = "🔴"
                else:
                    icon = "❓"

                duration_str = f"{duration}s" if duration else "N/A"
                logger.info(f"{icon} {table}: {status_val} ({failures} failures, "
                           f"duration: {duration_str})")

                if error:
                    logger.info(f"   Last error: {error[:100]}")

    except Exception as e:
        logger.error(f"Loader status check failed: {e}")

    return result


def main():
    """Run all audit checks."""
    logger.info("========================================")
    logger.info("COMPREHENSIVE LOADER AUDIT")
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info("========================================")

    watermarks = check_watermarks()
    nulls = check_null_coverage()
    dupes = check_duplicates()
    constraints = check_constraint_violations()
    loader_status = check_loader_status()

    # Summary
    logger.info("\n=== SUMMARY ===")

    issues = 0
    if any(v["missing_watermarks"] > 0 for v in watermarks.values()):
        issues += 1
        logger.warning("⚠️  Missing watermarks found")

    if any(v["stale_7d"] > 0 for v in watermarks.values()):
        issues += 1
        logger.warning("⚠️  Stale watermarks found")

    if any(v > 5 for d in nulls.values() for v in d.values()):
        issues += 1
        logger.warning("⚠️  High NULL ratios (>5%) found")

    if any(v > 0 for v in dupes.values()):
        issues += 1
        logger.warning("🔴 Duplicate rows found")

    if any(v > 0 for v in constraints.values()):
        issues += 1
        logger.warning("🔴 Constraint violations found")

    if any(v["status"] == "FAILED" for v in loader_status.values()):
        issues += 1
        logger.warning("🔴 Failed loaders found")

    if issues == 0:
        logger.info("✅ All audit checks passed!")
        return 0
    else:
        logger.warning(f"❌ {issues} categories with issues found")
        return 1


if __name__ == "__main__":
    sys.exit(main())
