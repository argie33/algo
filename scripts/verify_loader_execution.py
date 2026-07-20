#!/usr/bin/env python3
"""Verify that critical loaders are executing and completing successfully.

SESSION 289 FIX: Only 2 of 30+ loaders have recent runs.
This script identifies which loaders are not executing and why.
"""

import logging
from datetime import datetime

import psycopg2

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Loaders that MUST run daily for orchestrator to function
CRITICAL_LOADERS = {
    "loadpricedaily": {"min_interval_hours": 24, "description": "Price data (required for Phase 1)"},
    "load_buy_sell_daily": {"min_interval_hours": 24, "description": "Buy/sell signals (required for Phase 7)"},
    "load_stock_scores": {"min_interval_hours": 24, "description": "Stock scores (required for Phase 5/7)"},
    "load_market_exposure_daily": {"min_interval_hours": 24, "description": "Market exposure (required for Phase 5)"},
    "technical_data_daily_vectorized": {"min_interval_hours": 24, "description": "Technical indicators (required for Phase 1)"},
    "load_market_health_daily": {"min_interval_hours": 24, "description": "Market breadth (required for Phase 1)"},
}

# Secondary loaders that improve signal quality but aren't critical
SECONDARY_LOADERS = {
    "load_trend_analysis": {"min_interval_hours": 48, "description": "Trend templates"},
    "load_sector_performance": {"min_interval_hours": 48, "description": "Sector rankings"},
    "load_earnings_calendar": {"min_interval_hours": 168, "description": "Earnings dates"},
}


def check_loader_execution() -> dict:
    """Check if loaders are executing. Returns status dict."""

    try:
        with DatabaseContext("read") as cur:
            results = {
                "critical": {},
                "secondary": {},
                "missing": [],
                "timestamp": datetime.now().isoformat(),
            }

            # Check critical loaders
            for loader_name, config in CRITICAL_LOADERS.items():
                cur.execute(
                    """
                    SELECT
                        loader_name,
                        status,
                        created_at,
                        EXTRACT(HOUR FROM NOW() - created_at) as hours_ago,
                        records_loaded,
                        error_message
                    FROM data_loader_runs
                    WHERE loader_name = %s
                    ORDER BY created_at DESC
                    LIMIT 3
                    """,
                    (loader_name,),
                )

                runs = cur.fetchall()
                if not runs:
                    results["missing"].append(loader_name)
                    results["critical"][loader_name] = {
                        "status": "MISSING",
                        "description": config["description"],
                        "last_run": None,
                        "recent_runs": [],
                        "issue": "No execution history",
                    }
                else:
                    last_run = runs[0]
                    hours_ago = float(last_run[3]) if last_run[3] else None
                    is_overdue = hours_ago and hours_ago > config["min_interval_hours"]

                    recent = [
                        {
                            "status": r[1],
                            "timestamp": str(r[2])[:19],
                            "records": r[4],
                            "error": r[5][:100] if r[5] else None,
                        }
                        for r in runs
                    ]

                    results["critical"][loader_name] = {
                        "status": "OVERDUE" if is_overdue else last_run[1].upper(),
                        "description": config["description"],
                        "last_run": str(runs[0][2])[:19] if runs else None,
                        "hours_ago": hours_ago,
                        "recent_runs": recent,
                        "issue": f"Not run in {int(hours_ago)}h (max {config['min_interval_hours']}h)"
                        if is_overdue
                        else None,
                    }

            # Check secondary loaders
            for loader_name, config in SECONDARY_LOADERS.items():
                cur.execute(
                    """
                    SELECT
                        loader_name,
                        status,
                        created_at,
                        EXTRACT(HOUR FROM NOW() - created_at) as hours_ago
                    FROM data_loader_runs
                    WHERE loader_name = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (loader_name,),
                )

                run = cur.fetchone()
                if not run:
                    results["secondary"][loader_name] = {
                        "status": "NEVER_RUN",
                        "description": config["description"],
                    }
                else:
                    hours_ago = float(run[3]) if run[3] else None
                    is_overdue = hours_ago and hours_ago > config["min_interval_hours"]
                    results["secondary"][loader_name] = {
                        "status": "OVERDUE" if is_overdue else run[1].upper(),
                        "description": config["description"],
                        "last_run": str(run[2])[:19],
                        "hours_ago": hours_ago,
                    }

            return results

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Failed to check loader status: {e}")
        return {"error": str(e)}


def main() -> int:
    """Check loader execution and report status."""
    logger.info("Checking loader execution status...")

    results = check_loader_execution()

    if "error" in results:
        logger.error(f"Database error: {results['error']}")
        return 1

    # Report critical loaders
    logger.info("\n=== CRITICAL LOADERS (Required Daily) ===\n")
    critical_failures = 0
    for loader_name, status in results["critical"].items():
        if status["status"] == "MISSING":
            logger.critical(f"  ❌ {loader_name}: NEVER RUN - {status['issue']}")
            critical_failures += 1
        elif status["status"] == "OVERDUE":
            logger.error(f"  ⚠️  {loader_name}: OVERDUE - {status['issue']}")
            critical_failures += 1
        elif status["status"] == "FAILED":
            logger.error(f"  ⚠️  {loader_name}: FAILED - {status['recent_runs'][0]['error']}")
            critical_failures += 1
        elif status["status"] == "SUCCESS":
            logger.info(f"  ✓ {loader_name}: OK (ran {int(status['hours_ago'])}h ago)")
        else:
            logger.warning(f"  ? {loader_name}: {status['status']} ({status['hours_ago']:.1f}h ago)")

    # Report secondary loaders
    if results["secondary"]:
        logger.info("\n=== SECONDARY LOADERS (Quality Improvement) ===\n")
        for loader_name, status in results["secondary"].items():
            if status["status"] == "NEVER_RUN":
                logger.warning(f"  - {loader_name}: Never run")
            elif status["status"] == "OVERDUE":
                logger.info(f"  ⚠️  {loader_name}: Overdue ({status['hours_ago']:.0f}h)")
            else:
                logger.info(f"  ✓ {loader_name}: {status['status']}")

    # Summary
    total_critical = len(results["critical"])
    missing = len([s for s in results["critical"].values() if s["status"] == "MISSING"])
    overdue = len([s for s in results["critical"].values() if s["status"] == "OVERDUE"])
    failed = len([s for s in results["critical"].values() if s["status"] == "FAILED"])
    ok = len([s for s in results["critical"].values() if s["status"] == "SUCCESS"])

    logger.info("\n=== SUMMARY ===")
    logger.info(f"Critical Loaders: {ok}/{total_critical} healthy")
    if missing:
        logger.critical(f"  {missing} never run")
    if overdue:
        logger.error(f"  {overdue} overdue")
    if failed:
        logger.error(f"  {failed} failed")

    # Exit code: 0 if all critical loaders OK, 1 if any critical issues
    return 1 if (missing + overdue + failed) > 0 else 0


if __name__ == "__main__":
    exit(main())
