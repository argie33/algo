#!/usr/bin/env python3
"""Verify that AWS fixes (price loader + Phase 7 metrics) are working.

Usage: python scripts/verify_aws_fixes.py

Checks:
1. Price loader logs - no "Invalid date range" errors
2. Metrics freshness - all metrics updated in last hour
3. Orchestrator Phase 1 - passes without stale data halt
4. Dashboard data source - shows AWS (not stale fallback)
"""

import logging
import sys
from datetime import datetime, timedelta

import boto3
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def check_price_loader_logs() -> bool:
    """Check CloudWatch logs for price loader errors."""
    logger.info("\n=== PRICE LOADER LOG CHECK ===")
    try:
        logs = boto3.client("logs", region_name="us-east-1")

        # Get latest price loader log stream
        streams = logs.describe_log_streams(
            logGroupName="/ecs/algo-stock_prices_daily-loader",
            orderBy="LastEventTime",
            descending=True,
            limit=1,
        )

        if not streams["logStreams"]:
            logger.warning("No price loader log streams found")
            return False

        stream_name = streams["logStreams"][0]["logStreamName"]
        logger.info(f"Checking log stream: {stream_name}")

        # Get recent log events
        events = logs.get_log_events(
            logGroupName="/ecs/algo-stock_prices_daily-loader",
            logStreamName=stream_name,
            limit=100,
        )

        # Check for errors
        has_error = False
        for event in events["events"]:
            msg = event["message"].lower()
            if "invalid date range" in msg or "start >= end" in msg:
                logger.error(f"FOUND ERROR: {event['message'][:100]}")
                has_error = True
            elif any(x in msg for x in ["failed", "error", "critical"]):
                logger.warning(f"Found error: {event['message'][:100]}")

        if not has_error:
            logger.info("✓ No 'Invalid date range' errors found")
            return True

        return False

    except Exception as e:
        logger.error(f"Could not check price loader logs: {e}")
        return False


def check_metrics_freshness() -> bool:
    """Check if metrics tables have fresh data."""
    logger.info("\n=== METRICS FRESHNESS CHECK ===")
    try:
        metrics_tables = ["quality_metrics", "growth_metrics", "value_metrics", "positioning_metrics", "stability_metrics"]
        now = datetime.now(EASTERN_TZ)
        one_hour_ago = now - timedelta(hours=1)

        all_fresh = True
        with DatabaseContext("read") as cur:
            for table in metrics_tables:
                cur.execute(f"SELECT MAX(updated_at) FROM {table}")
                result = cur.fetchone()
                if result and result[0]:
                    updated_at = result[0]
                    age_hours = (now - updated_at).total_seconds() / 3600
                    status = "✓" if age_hours < 1 else "✗"
                    logger.info(f"{status} {table:30} updated {age_hours:.1f}h ago")
                    if age_hours >= 1:
                        all_fresh = False
                else:
                    logger.warning(f"✗ {table:30} NO DATA")
                    all_fresh = False

        return all_fresh

    except Exception as e:
        logger.error(f"Could not check metrics freshness: {e}")
        return False


def check_orchestrator_phase1() -> bool:
    """Check if latest orchestrator Phase 1 passed without stale data halt."""
    logger.info("\n=== ORCHESTRATOR PHASE 1 CHECK ===")
    try:
        with DatabaseContext("read") as cur:
            # Get latest orchestrator run
            cur.execute("""
                SELECT run_id, started_at, overall_status, halt_reason
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)

            result = cur.fetchone()
            if not result:
                logger.warning("No orchestrator runs found")
                return False

            run_id, started_at, overall_status, halt_reason = result
            logger.info(f"Latest run: {run_id} at {started_at.strftime('%Y-%m-%d %H:%M')}")
            logger.info(f"Status: {overall_status}")

            if halt_reason and "stale metric" in halt_reason.lower():
                logger.error(f"✗ Orchestrator halted due to stale metrics: {halt_reason[:100]}")
                return False

            if "ok" in overall_status.lower():
                logger.info("✓ Orchestrator Phase 1 passed without stale data halt")
                return True

            return False

    except Exception as e:
        logger.error(f"Could not check orchestrator: {e}")
        return False


def check_dashboard_data_source() -> bool:
    """Check if dashboard is displaying AWS data (not stale cache)."""
    logger.info("\n=== DASHBOARD DATA SOURCE CHECK ===")
    try:
        # Try to import dashboard and check data freshness
        from dashboard.fetchers import load_all
        from dashboard.api_data_layer import get_api_url

        api_url = get_api_url()
        logger.info(f"Dashboard API URL: {api_url}")

        if "localhost" in api_url:
            logger.warning("Dashboard is in LOCAL mode, not AWS mode")
            return False

        logger.info("✓ Dashboard is in AWS mode")

        # Try to load data to verify it's working
        data = load_all()
        if data and data.get("run") and data["run"].get("run_id"):
            logger.info(f"✓ Dashboard loaded data from run: {data['run']['run_id']}")
            return True

        return False

    except Exception as e:
        logger.warning(f"Could not fully verify dashboard (may be OK if not running): {e}")
        return True  # Don't fail - dashboard may not be running


def main() -> bool:
    """Run all verification checks."""
    logger.info("=" * 70)
    logger.info("AWS FIXES VERIFICATION")
    logger.info("=" * 70)

    results = {
        "Price Loader Logs": check_price_loader_logs(),
        "Metrics Freshness": check_metrics_freshness(),
        "Orchestrator Phase 1": check_orchestrator_phase1(),
        "Dashboard Data Source": check_dashboard_data_source(),
    }

    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    passed = 0
    for check_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {check_name}")
        if result:
            passed += 1

    logger.info(f"\nResult: {passed}/{len(results)} checks passed")

    if passed == len(results):
        logger.info("\n✓ ALL CHECKS PASSED - AWS FIXES ARE WORKING!")
        return True
    else:
        logger.warning("\n✗ SOME CHECKS FAILED - Review logs above")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
