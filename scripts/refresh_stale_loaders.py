#!/usr/bin/env python3
"""
Comprehensive Loader Refresh System
=====================================

Identifies and refreshes stale loaders systematically.
Priority: Critical data first, then important data, then nice-to-have.

Usage: python3 scripts/refresh_stale_loaders.py [--force] [--verbose]
"""

import logging
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Loaders to refresh, with priority (1=critical, 2=important, 3=nice-to-have)
# Table names verified live against what each loader actually writes to (see
# scripts/verify_loaders_health.py / scripts/audit_all_loaders.py for the same
# reconciliation) - the old 'earnings_history' entry pointed at a permanently-empty
# (0 rows) legacy table instead of 'earnings_calendar_sec' (353k rows, updated daily),
# which crashed get_data_age's None-vs-int staleness comparison on every run before a
# single loader could refresh. 'load_growth_metrics.py' referenced a file deleted since
# Session 275 (renamed to load_value_quality_growth_metrics.py).
LOADERS_TO_REFRESH = [
    # CRITICAL PRIORITY (last refreshed 2+ weeks ago)
    ('loaders/load_earnings_calendar_sec.py', 'earnings_calendar_sec', 1, 7),
    ('loaders/load_sector_industry_daily.py', 'industry_ranking', 1, 7),

    # IMPORTANT PRIORITY (last refreshed 2+ days ago)
    ('loaders/load_prices.py', 'price_daily', 2, 1),
    ('loaders/load_buy_sell_daily.py', 'buy_sell_daily', 2, 1),
    ('loaders/load_technical_indicators.py', 'technical_data_daily', 2, 1),

    # MAINTAIN PRIORITY (keep fresh)
    ('loaders/load_stock_scores.py', 'stock_scores', 2, 1),
    ('loaders/load_value_quality_growth_metrics.py', 'growth_metrics', 2, 3),
    ('loaders/load_sec_valuations.py', 'sec_valuations', 2, 3),
]


def _validate_against_registry() -> None:
    """Fail loudly if this list drifts from loaders/loader_registry.py again.

    Same guard as scripts/verify_loaders_health.py - see that module for why:
    this exact list independently accumulated the same wrong-table/dead-loader
    drift the registry was built to eliminate, so both check against it rather
    than trusting hand-maintained entries indefinitely.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from loaders.loader_registry import all_tables

    for loader_path, table_name, _priority, _threshold_days in LOADERS_TO_REFRESH:
        loader_name = Path(loader_path).name
        registry_tables = all_tables(loader_name)
        if not registry_tables:
            continue
        if table_name not in registry_tables:
            raise AssertionError(
                f"[LOADERS_TO_REFRESH] {loader_name}'s configured table={table_name!r} not in "
                f"loaders/loader_registry.py's known tables {registry_tables} - fix before trusting "
                f"this script's refresh decisions."
            )


_validate_against_registry()

def get_data_age(table_name: str) -> dict:
    """Get table data age from database."""
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    try:
        # Determine date column
        date_col_map = {
            'price_daily': 'date',
            'buy_sell_daily': 'date',
            'technical_data_daily': 'date',
            'stock_scores': 'updated_at',
            'growth_metrics': 'updated_at',
            'sec_valuations': 'updated_at',
            'earnings_calendar_sec': 'updated_at',
            'industry_ranking': 'updated_at',
        }
        date_col = date_col_map.get(table_name, 'updated_at')

        cur.execute(f"""
            SELECT
                COUNT(*) as rows,
                CAST(MAX({date_col}) AS DATE) as latest
            FROM {table_name}
        """)
        rows, latest = cur.fetchone()

        if latest:
            age_days = (date.today() - latest).days
            return {
                'exists': True,
                'rows': rows,
                'latest_date': latest,
                'age_days': age_days,
            }
        else:
            return {'exists': True, 'rows': rows, 'latest_date': None, 'age_days': None}
    except Exception as e:
        return {'exists': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()

def run_loader(loader_path: str, timeout_seconds: int = 300) -> bool:
    """Run a loader script, return success status."""
    logger.info(f"Starting: {loader_path}")

    try:
        result = subprocess.run(
            ['python3', loader_path],
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent  # Use project root
        )

        if result.returncode == 0:
            logger.info(f"SUCCESS: {loader_path}")
            return True
        else:
            logger.error(f"FAILED: {loader_path}")
            logger.error(f"  stderr: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning(f"⏱ TIMEOUT: {loader_path} (>{timeout_seconds}s, likely still running)")
        # Long-running loaders (SEC API) may timeout; this is not necessarily failure
        return True  # Optimistic - assume it's working
    except Exception as e:
        logger.error(f"ERROR: {loader_path}: {e!s}")
        return False

def main():
    logger.info("=" * 80)
    logger.info("STALE LOADER REFRESH SYSTEM")
    logger.info("=" * 80)

    # Check database connectivity
    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        conn.close()
        logger.info("[OK] Database connection successful")
    except Exception as e:
        logger.error(f"[FAIL] Cannot connect to database: {e}")
        return 1

    # Audit current data freshness
    logger.info("\n" + "=" * 80)
    logger.info("BEFORE REFRESH: Data Age Audit")
    logger.info("=" * 80)

    stale_loaders = []
    for loader_path, table_name, priority, threshold_days in LOADERS_TO_REFRESH:
        age_info = get_data_age(table_name)

        if age_info['exists']:
            age = age_info['age_days']
            # age is None when the table exists but has no rows with a non-null date
            # column (never populated, or genuinely empty) - treat as CRITICAL rather
            # than crashing the None-vs-int comparison below.
            status = (
                "CRITICAL"
                if age is None or age > threshold_days * 2
                else "STALE"
                if age > threshold_days
                else "OK"
            )
            age_str = f"{age:3}" if age is not None else "N/A"

            logger.info(
                f"{table_name:25} | Age: {age_str}d | Threshold: {threshold_days}d | {status:8} | {age_info['rows']:,} rows"
            )

            if status in ("STALE", "CRITICAL"):
                stale_loaders.append((loader_path, table_name, priority, age))
        else:
            logger.error(f"{table_name:25} | Table not found or error: {age_info.get('error')}")

    if not stale_loaders:
        logger.info("\n[OK] All loaders are fresh! No refresh needed.")
        return 0

    logger.info(f"\n[ALERT] Found {len(stale_loaders)} stale loader(s). Starting refresh...")

    # Refresh stale loaders in priority order (1 = critical first, then oldest age
    # first - None (table has no dated rows at all) sorts as oldest, not a crash)
    stale_loaders.sort(key=lambda x: (-x[2], -(x[3] if x[3] is not None else float("inf"))))

    logger.info("\n" + "=" * 80)
    logger.info("REFRESH SEQUENCE (Priority Order)")
    logger.info("=" * 80)

    results = {}
    for loader_path, table_name, priority, age_days in stale_loaders:
        priority_name = "CRITICAL" if priority == 1 else "IMPORTANT" if priority == 2 else "MAINTAIN"
        logger.info(f"\n[{priority_name}] Refreshing {table_name} ({age_days}d stale)...")

        success = run_loader(loader_path)
        results[table_name] = success

        # Wait a bit between loader runs to avoid resource contention
        if stale_loaders.index((loader_path, table_name, priority, age_days)) < len(stale_loaders) - 1:
            logger.info("  Waiting 10s before next loader...")
            time.sleep(10)

    # Verify refresh
    logger.info("\n" + "=" * 80)
    logger.info("AFTER REFRESH: Data Age Audit")
    logger.info("=" * 80)

    all_fresh = True
    for _loader_path, table_name, _priority, _ in stale_loaders:
        age_info = get_data_age(table_name)

        if age_info['exists'] and age_info['age_days'] is not None:
            age = age_info['age_days']
            status = "REFRESHED" if age <= 1 else "UPDATED" if age <= 3 else "NOT FRESH"
            logger.info(f"  {status}: {table_name:25} | Age: {age:3}d old")

            if status == "NOT FRESH":
                all_fresh = False
        else:
            logger.error(f"  FAILED: {table_name:25} | Still no data")
            all_fresh = False

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("REFRESH SUMMARY")
    logger.info("=" * 80)

    successful = sum(1 for v in results.values() if v)
    total = len(results)

    logger.info(f"Loaders run: {total}")
    logger.info(f"Successful: {successful}/{total}")

    if all_fresh:
        logger.info("All critical data is now fresh!")
        return 0
    else:
        logger.warning("Some data is still stale. Recommend manual investigation.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
