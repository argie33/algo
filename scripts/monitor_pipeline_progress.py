#!/usr/bin/env python3
"""Real-time pipeline progress monitor.

Shows loader status, metric table coverage, and estimated completion.
Run in a loop to watch progress: while true; do python3 monitor_pipeline_progress.py; sleep 30; done
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def get_loader_status() -> dict:
    """Get loader progress from data_loader_status table."""
    try:
        with DatabaseContext("read", timeout=5) as cur:
            cur.execute(
                """
                SELECT table_name, loader_name, progress_pct, estimated_completion_time,
                       symbols_loaded, symbols_total, status, last_update
                FROM data_loader_status
                WHERE DATE(last_update) = %s
                ORDER BY last_update DESC
                LIMIT 20
                """,
                (date.today(),),
            )
            return {row[0]: row for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Failed to query loader status: {e}")
        return {}


def get_metric_coverage() -> dict:
    """Get current coverage for each metric table."""
    tables = {
        "positioning_metrics": ("Positioning", 0.70),
        "value_metrics": ("Value", 0.80),
        "growth_metrics": ("Growth", 0.70),
        "quality_metrics": ("Quality", 0.70),
        "stability_metrics": ("Stability", 0.85),
    }

    coverage = {}
    try:
        with DatabaseContext("read", timeout=5) as cur:
            for table, (label, threshold) in tables.items():
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE data_unavailable = false")
                available = cur.fetchone()[0] if cur.fetchone() else 0

                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = cur.fetchone()[0] if cur.fetchone() else 0

                pct = (available / total * 100) if total > 0 else 0
                status = "✓" if pct >= threshold * 100 else "✗" if total > 0 else "⏳"

                coverage[table] = {
                    "label": label,
                    "available": available,
                    "total": total,
                    "pct": pct,
                    "threshold": threshold * 100,
                    "status": status,
                }
    except Exception as e:
        logger.error(f"Failed to query metric coverage: {e}")

    return coverage


def get_stock_scores_status() -> dict:
    """Check if stock_scores loader can run (upstream validation)."""
    try:
        with DatabaseContext("read", timeout=5) as cur:
            # Check required metrics
            required = ["value_metrics", "positioning_metrics", "stability_metrics"]
            upstream_ok = True

            for table in required:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE data_unavailable = false")
                available = cur.fetchone()[0] if cur.fetchone() else 0

                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = cur.fetchone()[0] if cur.fetchone() else 0

                coverage = (available / total * 100) if total > 0 else 0

                if coverage < 70:
                    upstream_ok = False
                    logger.warning(f"  ⚠ {table}: {coverage:.1f}% (need 70%)")

            # Check optional metrics
            for table in ["growth_metrics", "quality_metrics"]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = cur.fetchone()[0] if cur.fetchone() else 0

                if total == 0:
                    logger.warning(f"  ⚠ {table}: empty (loader may not have run)")

            return {"upstream_ready": upstream_ok}
    except Exception as e:
        logger.error(f"Failed to check stock_scores prerequisites: {e}")
        return {"upstream_ready": False, "error": str(e)}


def main():
    now = datetime.now(EASTERN_TZ)
    logger.info("\n" + "="*80)
    logger.info(f"PIPELINE PROGRESS MONITOR — {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("="*80)

    # Loader status
    logger.info("\n📊 LOADER STATUS (from data_loader_status):")
    loaders = get_loader_status()
    if loaders:
        for _table, status_row in loaders.items():
            if status_row:
                _table_name, loader, progress, eta, loaded, total, _status_str, last_update = status_row
                logger.info(
                    f"  {loader:<30} {progress:>6.1f}% ({loaded:>5}/{total:<5}) "
                    f"ETA: {eta} Last: {last_update}"
                )
    else:
        logger.info("  (No recent loader status found)")

    # Metric table coverage
    logger.info("\n📈 METRIC TABLE COVERAGE:")
    coverage = get_metric_coverage()
    all_ok = True
    for _table, info in coverage.items():
        status = info["status"]
        pct = info["pct"]
        threshold = info["threshold"]
        available = info["available"]
        total = info["total"]

        if total == 0:
            logger.info(f"  {status} {info['label']:<12} (0 rows — loader may not have run)")
            all_ok = False
        else:
            logger.info(
                f"  {status} {info['label']:<12} {pct:>6.1f}% "
                f"({available:>5}/{total:<5}) threshold: {threshold:>5.0f}%"
            )
            if pct < threshold:
                all_ok = False

    # Stock scores readiness
    logger.info("\n📋 STOCK SCORES LOADER READINESS:")
    scores_status = get_stock_scores_status()
    if scores_status.get("upstream_ready"):
        logger.info("  ✓ All upstream metrics ready — stock_scores can run")
    else:
        logger.info("  ✗ Upstream metrics incomplete — stock_scores will wait")

    # Summary
    logger.info("\n" + "="*80)
    if all_ok and scores_status.get("upstream_ready"):
        logger.info("✓ PIPELINE STATUS: All metrics loaded, stock_scores should run next")
    elif all_ok:
        logger.info("⏳ PIPELINE STATUS: Metrics loaded, waiting for stock_scores...")
    else:
        logger.info("⏳ PIPELINE STATUS: Metrics still loading, please wait...")
    logger.info("="*80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
