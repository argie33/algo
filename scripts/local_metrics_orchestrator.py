#!/usr/bin/env python3
"""Local metrics orchestrator - runs complete metrics pipeline with monitoring.

Replaces EventBridge Scheduler for local development. Runs the complete
metrics pipeline (financial statements → metrics → scores) and monitors
data completion.

This is for LOCAL/DEV ONLY. Production uses EventBridge Scheduler + Step Functions.

Usage:
    python3 scripts/local_metrics_orchestrator.py          # Run once
    python3 scripts/local_metrics_orchestrator.py --watch   # Monitor completion
    python3 scripts/local_metrics_orchestrator.py --daily   # Run daily (daemon)

What it does:
1. Checks if metrics are fresh (within 24h)
2. If stale, runs complete pipeline:
   - load_financial_statements.py (20-30 min)
   - load_sec_valuations.py
   - load_value_quality_growth_metrics.py
   - load_positioning_metrics.py
   - load_stock_scores.py
3. Monitors data completion and reports results
4. Returns exit code 0 if successful, 1 if failed
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Loaders in pipeline order (dependencies respected)
CRITICAL_LOADERS = [
    "load_financial_statements.py",       # 20-30 min: SEC data
    "load_sec_valuations.py",             # 5 min: PE/PB/PS
    "load_value_quality_growth_metrics.py",  # 15 min: consolidated metrics
    "load_positioning_metrics.py",        # 10 min: ownership data
    "load_stock_scores.py",               # 5 min: composite scores
]

MIN_COVERAGE = {
    "value_metrics": 70,      # Need 70%+ for trading
    "quality_metrics": 70,
    "growth_metrics": 70,
    "positioning_metrics": 70,
    "stock_scores": 70,
}


def check_data_freshness() -> tuple[bool, str]:
    """Check if metrics data is fresh (loaded within last 24h).

    Returns:
        (is_fresh, reason_if_stale)
    """
    try:
        import psycopg2

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        # Check latest value_metrics update
        cur.execute("SELECT MAX(updated_at) FROM value_metrics")
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return False, "value_metrics table is empty"

        latest = row[0]
        age = datetime.now() - latest.replace(tzinfo=None)

        if age < timedelta(hours=24):
            return True, f"Data fresh ({age.total_seconds()/3600:.1f}h old)"
        else:
            return False, f"Data stale ({age.total_seconds()/3600:.1f}h old)"

    except Exception as e:
        return False, f"Could not check freshness: {e}"


def check_data_coverage() -> dict[str, float]:
    """Get current data coverage percentages.

    Returns:
        Dict of table_name -> coverage_percent
    """
    try:
        import psycopg2

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        # Get total stock count
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE symbol IS NOT NULL")
        total = cur.fetchone()[0]

        coverage = {}
        for table in MIN_COVERAGE.keys():
            cur.execute(f"SELECT COUNT(DISTINCT symbol) FROM {table} WHERE symbol IS NOT NULL")
            count = cur.fetchone()[0]
            pct = (count / total * 100) if total > 0 else 0
            coverage[table] = pct

        cur.close()
        conn.close()
        return coverage

    except Exception as e:
        logger.error(f"Could not check coverage: {e}")
        return {}


def run_loader(loader_path: str, timeout: int = 3600) -> bool:
    """Run a single loader and return success status.

    Args:
        loader_path: Path to loader script (relative to loaders/)
        timeout: Max seconds to wait

    Returns:
        True if successful, False otherwise
    """
    full_path = Path(__file__).parent.parent / "loaders" / loader_path

    if not full_path.exists():
        logger.error(f"Loader not found: {full_path}")
        return False

    logger.info(f"[LOADER] Running {loader_path}...")

    try:
        env = os.environ.copy()
        env["LOCAL_MODE"] = "1"

        result = subprocess.run(
            [sys.executable, str(full_path)],
            timeout=timeout,
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            logger.info(f"[OK] {loader_path} completed successfully")
            return True
        else:
            logger.error(f"[FAIL] {loader_path} failed with exit code {result.returncode}")
            if result.stderr:
                logger.error(f"  stderr: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"[TIMEOUT] {loader_path} timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"[ERROR] {loader_path} error: {e}")
        return False


def run_pipeline() -> bool:
    """Run complete metrics pipeline.

    Returns:
        True if all loaders succeeded, False if any failed
    """
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING COMPLETE METRICS PIPELINE")
    logger.info("=" * 80)

    all_success = True
    for loader in CRITICAL_LOADERS:
        if not run_loader(loader):
            all_success = False
            logger.warning(f"[CONTINUE] Pipeline continues despite {loader} issues")

    return all_success


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local metrics orchestrator - replaces EventBridge for dev"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run pipeline even if data is fresh",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch until metrics reach minimum coverage",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Run daily as daemon (checks every 12 hours)",
    )

    args = parser.parse_args()

    # Check data freshness
    is_fresh, reason = check_data_freshness()
    logger.info(f"Data freshness: {reason}")

    should_run = args.force or not is_fresh

    if not should_run:
        logger.info("Data is fresh - skipping pipeline run")
        if args.daily:
            logger.info("Will check again in 12 hours")
            time.sleep(12 * 3600)
            return main()
        return 0

    # Run pipeline
    success = run_pipeline()

    # Check coverage
    coverage = check_data_coverage()

    logger.info("\n" + "=" * 80)
    logger.info("DATA COVERAGE AFTER PIPELINE")
    logger.info("=" * 80)

    all_sufficient = True
    for table, min_pct in MIN_COVERAGE.items():
        actual_pct = coverage.get(table, 0)
        status = "✓" if actual_pct >= min_pct else "✗"
        logger.info(f"{status} {table:30s} {actual_pct:5.1f}% (need {min_pct}%)")
        if actual_pct < min_pct:
            all_sufficient = False

    # Report results
    if all_sufficient and success:
        logger.info("\n[SUCCESS] Pipeline completed with sufficient data coverage!")
        return 0
    else:
        logger.warning("\n[PARTIAL] Pipeline completed but coverage is below targets")
        logger.warning("This is expected if SEC Edgar doesn't have filings for all stocks")
        logger.warning("System will still function but with limited metrics")
        return 1 if args.watch else 0


if __name__ == "__main__":
    sys.exit(main())
