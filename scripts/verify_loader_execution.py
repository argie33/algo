#!/usr/bin/env python3
"""Verify that critical loaders are executing and completing successfully.

SESSION 289 FIX: Only 2 of 30+ loaders have recent runs.
This script identifies which loaders are not executing and why.

REWRITTEN: The original version queried data_loader_runs (a loader_name-keyed
execution log), but confirmed live that table only ever contains 5 distinct
loader_name values (loadpricedaily, swing_trader_scores[_vectorized],
technical_data_daily[_vectorized]) - none of the current loaders for
buy_sell_daily, stock_scores, market_exposure_daily, market_health_daily,
trend_template_data, sector_performance, or earnings_calendar_sec have ever
written to it. Every one of those was unconditionally reported "MISSING -
No execution history" regardless of actual system health - the exact
symptom the Session 289 docstring above describes, except the real cause was
that this script (and much of what it checked for) predates the loader
consolidation and everyone since has tracked loader health through
data_loader_status instead (table_name-keyed, one current-state row per
table, actively maintained - confirmed live and matches
scripts/monitor_data_staleness.py's canonical source). Rewritten to query
that table directly instead of reinventing staleness classification.
"""

import logging
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as Psycopg2Cursor

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Loaders that MUST run daily for orchestrator to function, keyed by the
# data_loader_status.table_name they actually write to.
CRITICAL_LOADERS = {
    "price_daily": "Price data (required for Phase 1)",
    "buy_sell_daily": "Buy/sell signals (required for Phase 7)",
    "stock_scores": "Stock scores (required for Phase 5/7)",
    "market_exposure_daily": "Market exposure (required for Phase 5)",
    "technical_data_daily": "Technical indicators (required for Phase 1)",
    "market_health_daily": "Market breadth (required for Phase 1)",
}

# Secondary loaders that improve signal quality but aren't critical
SECONDARY_LOADERS = {
    "trend_template_data": "Trend templates",
    "sector_performance": "Sector rankings",
    "earnings_calendar_sec": "Earnings dates",
}

# data_loader_status.status values that mean "this table is fine" - HEALTHY is
# the obvious case; COMPLETED/RUNNING cover a loader mid-flight when this
# script happens to run concurrently with the pipeline.
OK_STATUSES = {"HEALTHY", "COMPLETED", "RUNNING"}
# DEPRECATED means the table is intentionally no longer authoritative (a newer
# consolidated loader replaced it) - not a failure, shouldn't count against
# either summary.
DEPRECATED_STATUSES = {"DEPRECATED"}


def _fetch_status(cur: Psycopg2Cursor, table_name: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT status, latest_date, age_days, row_count, stale_threshold_days,
               error_message, reason, last_updated
        FROM data_loader_status
        WHERE table_name = %s
        """,
        (table_name,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "status": row[0],
        "latest_date": row[1],
        "age_days": row[2],
        "row_count": row[3],
        "stale_threshold_days": row[4],
        "error_message": row[5],
        "reason": row[6],
        "last_updated": row[7],
    }


def check_loader_execution() -> dict[str, Any]:
    """Check if loaders are executing. Returns status dict."""

    try:
        with DatabaseContext("read") as cur:
            results: dict[str, Any] = {
                "critical": {},
                "secondary": {},
                "timestamp": datetime.now().isoformat(),
            }

            for table_name, description in CRITICAL_LOADERS.items():
                info = _fetch_status(cur, table_name)
                if info is None:
                    results["critical"][table_name] = {
                        "status": "NOT_TRACKED",
                        "description": description,
                        "issue": "No row in data_loader_status - table_name may be wrong or monitoring hasn't run",
                    }
                else:
                    results["critical"][table_name] = {**info, "description": description}

            for table_name, description in SECONDARY_LOADERS.items():
                info = _fetch_status(cur, table_name)
                if info is None:
                    results["secondary"][table_name] = {
                        "status": "NOT_TRACKED",
                        "description": description,
                    }
                else:
                    results["secondary"][table_name] = {**info, "description": description}

            return results

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Failed to check loader status: {e}")
        return {"error": str(e)}


def main() -> int:
    """Check loader execution and report status."""
    logger.info("Checking loader execution status (via data_loader_status)...")

    results = check_loader_execution()

    if "error" in results:
        logger.error(f"Database error: {results['error']}")
        return 1

    logger.info("\n=== CRITICAL LOADERS (Required Daily) ===\n")
    critical_failures = 0
    for table_name, info in results["critical"].items():
        status = info["status"]
        if status in OK_STATUSES:
            age = info.get("age_days")
            logger.info(f"  {table_name}: {status} (age={age}d, rows={info.get('row_count')})")
        elif status in DEPRECATED_STATUSES:
            logger.info(f"  - {table_name}: DEPRECATED ({info.get('reason', 'no reason recorded')})")
        elif status == "NOT_TRACKED":
            logger.critical(f"  {table_name}: {info['issue']}")
            critical_failures += 1
        else:
            # MISSING, STALE, VERY_STALE, or any other status data_loader_status assigns
            logger.error(
                f"  ⚠️  {table_name}: {status} "
                f"(age={info.get('age_days')}d, threshold={info.get('stale_threshold_days')}d, "
                f"error={info.get('error_message') or info.get('reason')})"
            )
            critical_failures += 1

    if results["secondary"]:
        logger.info("\n=== SECONDARY LOADERS (Quality Improvement) ===\n")
        for table_name, info in results["secondary"].items():
            status = info["status"]
            if status in OK_STATUSES:
                logger.info(f"  {table_name}: {status}")
            elif status in DEPRECATED_STATUSES:
                logger.info(f"  - {table_name}: DEPRECATED ({info.get('reason', 'no reason recorded')})")
            elif status == "NOT_TRACKED":
                logger.warning(f"  ? {table_name}: not tracked in data_loader_status")
            else:
                logger.warning(f"  {table_name}: {status} (age={info.get('age_days')}d)")

    total_critical = len(results["critical"])
    ok = len([s for s in results["critical"].values() if s["status"] in OK_STATUSES])

    logger.info("\n=== SUMMARY ===")
    logger.info(f"Critical Loaders: {ok}/{total_critical} healthy")
    if critical_failures:
        logger.error(f"  {critical_failures} critical loader(s) need attention")

    return 1 if critical_failures > 0 else 0


if __name__ == "__main__":
    exit(main())
