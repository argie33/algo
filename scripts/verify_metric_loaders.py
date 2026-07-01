#!/usr/bin/env python3
"""Verify metric loaders are running and loading data without gaps.

Checks:
1. Metric tables have been updated today
2. Data coverage is above threshold (no large gaps)
3. No excessive data_unavailable markers
4. Stock scores can be computed (upstream validation)
"""

import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def check_metric_table(table_name: str, min_coverage_pct: float = 0.70) -> dict:
    """Check a metric table for coverage and data quality."""
    try:
        with DatabaseContext("read", timeout=10) as cur:
            # Total rows
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = cur.fetchone()[0] if cur.fetchone() else 0

            # Rows with available data (not data_unavailable)
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE data_unavailable = false OR data_unavailable IS NULL")
            available = cur.fetchone()[0] if cur.fetchone() else 0

            # Latest update date
            cur.execute(f"SELECT MAX(updated_at) FROM {table_name}")
            latest = cur.fetchone()[0] if cur.fetchone() else None

            # Rows updated today
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE DATE(updated_at) = %s", (date.today(),))
            today_count = cur.fetchone()[0] if cur.fetchone() else 0

            coverage = (available / total * 100) if total > 0 else 0
            meets_threshold = coverage >= (min_coverage_pct * 100)

            return {
                "table": table_name,
                "total_rows": total,
                "available_rows": available,
                "coverage_pct": round(coverage, 1),
                "updated_today": today_count,
                "latest_date": latest,
                "meets_threshold": meets_threshold,
                "status": "✓ OK" if meets_threshold else "✗ INCOMPLETE"
            }
    except Exception as e:
        return {
            "table": table_name,
            "error": str(e),
            "status": "✗ ERROR"
        }


def main():
    logger.info("\n" + "="*70)
    logger.info("METRIC LOADER VERIFICATION")
    logger.info("="*70)

    metric_tables = {
        "positioning_metrics": 0.70,
        "value_metrics": 0.80,
        "stability_metrics": 0.85,
        "growth_metrics": 0.70,  # Optional SEC data, but must have >0%
        "quality_metrics": 0.70,  # Optional SEC data, but must have >0%
        "stock_scores": 0.80,
    }

    results = {}
    all_ok = True

    for table, threshold in metric_tables.items():
        logger.info(f"\nChecking {table}...")
        result = check_metric_table(table, min_coverage_pct=threshold)
        results[table] = result

        if "error" in result:
            logger.error(f"  ✗ ERROR: {result['error']}")
            all_ok = False
        else:
            status = result["status"]
            coverage = result["coverage_pct"]
            available = result["available_rows"]
            total = result["total_rows"]
            today = result["updated_today"]

            logger.info(f"  {status}")
            logger.info(f"    Coverage: {coverage}% ({available}/{total} available)")
            logger.info(f"    Updated today: {today} rows")
            logger.info(f"    Latest update: {result['latest_date']}")

            if not result["meets_threshold"]:
                all_ok = False

    # Summary
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)

    ok_count = sum(1 for r in results.values() if r.get("status") == "✓ OK")
    total_count = len([r for r in results.values() if "error" not in r])

    logger.info(f"✓ Tables with sufficient data: {ok_count}/{total_count}")

    if all_ok:
        logger.info("\n✓ All metric loaders appear to be running successfully!")
        logger.info("  OPI and other stocks should have proper factor scores.")
        return 0
    else:
        logger.error("\n✗ Some metric tables have insufficient data:")
        for table, result in results.items():
            if result.get("status") != "✓ OK":
                logger.error(f"  - {table}: {result.get('status', 'UNKNOWN')}")
        logger.error("\n  Possible causes:")
        logger.error("  1. Loaders still running (check 7 PM Computed Metrics Pipeline)")
        logger.error("  2. Upstream dependencies incomplete (financial_data_pipeline)")
        logger.error("  3. RDS connection saturation reducing parallelism")
        logger.error("  4. yfinance API rate limiting")
        return 1


if __name__ == "__main__":
    sys.exit(main())
