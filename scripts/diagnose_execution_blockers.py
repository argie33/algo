#!/usr/bin/env python3
"""Comprehensive diagnostic script to identify orchestrator execution blockers.

Checks:
1. Database connectivity and schema
2. EventBridge scheduler configuration
3. Lambda function configuration
4. Data loader status
5. Recent orchestrator execution history
6. API endpoint functionality
7. Signal generation and persistence
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import psycopg2
from botocore.exceptions import BotoCoreError, ClientError

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def check_database_connectivity():
    """Check if database is accessible and has required tables."""
    logger.info("\n" + "=" * 70)
    logger.info("1. DATABASE CONNECTIVITY")
    logger.info("=" * 70)

    try:
        with DatabaseContext("read", timeout=10) as cur:
            # Check if required tables exist
            tables = [
                'algo_orchestrator_runs',
                'algo_signals',
                'buy_sell_daily',
                'price_daily',
                'stock_scores',
                'data_loader_status'
            ]

            for table in tables:
                cur.execute(f"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (table,))
                exists = cur.fetchone()[0]
                status = "✓" if exists else "✗"
                logger.info(f"  {status} Table '{table}': {'EXISTS' if exists else 'MISSING'}")

            logger.info("[OK] Database connectivity test passed")
            return True
    except Exception as e:
        logger.error(f"[ERROR] Database connectivity failed: {e}")
        return False


def check_orchestrator_runs():
    """Check recent orchestrator execution history."""
    logger.info("\n" + "=" * 70)
    logger.info("2. ORCHESTRATOR EXECUTION HISTORY")
    logger.info("=" * 70)

    try:
        with DatabaseContext("read", timeout=10) as cur:
            # Get last 5 runs
            cur.execute("""
                SELECT
                    run_id,
                    run_date,
                    started_at,
                    completed_at,
                    overall_status,
                    execution_time_seconds,
                    halt_reason
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 5
            """)

            runs = cur.fetchall()
            if not runs:
                logger.warning("[WARNING] No orchestrator runs found in database")
                return False

            logger.info(f"[OK] Found {len(runs)} recent runs:")
            for run in runs:
                run_id, run_date, started, completed, status, exec_time, halt = run
                if started:
                    hours_ago = (datetime.now(timezone.utc) - started.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    logger.info(
                        f"  • {run_id} ({run_date}): {status} — "
                        f"{hours_ago:.1f}h ago, {exec_time:.1f}s execution"
                    )

            # Check if last run is recent (within last 24 hours)
            last_run = runs[0]
            if last_run[2]:
                hours_since_last = (datetime.now(timezone.utc) - last_run[2].replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if hours_since_last > 24:
                    logger.warning(f"[WARNING] Last run was {hours_since_last:.1f} hours ago - orchestrator not executing regularly")
                    return False
                else:
                    logger.info(f"[OK] Last run was {hours_since_last:.1f} hours ago")
                    return True
    except Exception as e:
        logger.error(f"[ERROR] Failed to check orchestrator runs: {e}")
        return False


def check_data_loader_status():
    """Check status of critical data loaders."""
    logger.info("\n" + "=" * 70)
    logger.info("3. DATA LOADER STATUS")
    logger.info("=" * 70)

    try:
        with DatabaseContext("read", timeout=10) as cur:
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    completion_pct,
                    last_updated,
                    error_message
                FROM data_loader_status
                WHERE table_name IN (
                    'price_daily', 'stock_scores', 'technical_data_daily',
                    'growth_metrics', 'quality_metrics', 'value_metrics'
                )
                ORDER BY last_updated DESC
            """)

            loaders = cur.fetchall()
            if not loaders:
                logger.warning("[WARNING] No loader status found")
                return False

            all_fresh = True
            for table_name, status, completion_pct, last_updated, error in loaders:
                if last_updated:
                    hours_ago = (datetime.now(timezone.utc) - last_updated.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    freshness = "✓" if hours_ago < 24 else "✗"
                    logger.info(
                        f"  {freshness} {table_name}: {status} — "
                        f"{completion_pct:.1f}% complete, {hours_ago:.1f}h old"
                    )
                    if hours_ago > 24 or completion_pct < 95:
                        all_fresh = False

            if all_fresh:
                logger.info("[OK] All critical loaders are fresh and complete")
            else:
                logger.warning("[WARNING] Some loaders are stale or incomplete")

            return all_fresh
    except Exception as e:
        logger.error(f"[ERROR] Failed to check loader status: {e}")
        return False


def check_signals():
    """Check if signals are being generated and persisted."""
    logger.info("\n" + "=" * 70)
    logger.info("4. SIGNAL GENERATION AND PERSISTENCE")
    logger.info("=" * 70)

    try:
        with DatabaseContext("read", timeout=10) as cur:
            # Count signals by date
            cur.execute("""
                SELECT
                    DATE(signal_date) as date,
                    COUNT(*) as count,
                    MAX(created_at) as latest
                FROM algo_signals
                WHERE signal_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(signal_date)
                ORDER BY date DESC
                LIMIT 7
            """)

            signals = cur.fetchall()
            if not signals:
                logger.warning("[WARNING] No signals found in algo_signals table")
                return False

            logger.info(f"[OK] Found {sum(s[1] for s in signals)} signals in last 7 days:")
            for date, count, latest in signals:
                if latest:
                    hours_ago = (datetime.now(timezone.utc) - latest.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    logger.info(f"  • {date}: {count} signals (latest {hours_ago:.1f}h ago)")

            # Check if buy_sell_daily is fresh
            cur.execute("SELECT MAX(date) FROM buy_sell_daily")
            result = cur.fetchone()
            if result and result[0]:
                days_old = (datetime.now().date() - result[0]).days
                if days_old > 1:
                    logger.warning(f"[WARNING] buy_sell_daily is {days_old} days old")
                    return False
                else:
                    logger.info(f"[OK] buy_sell_daily is fresh ({days_old} days old)")
                    return True
            else:
                logger.warning("[WARNING] buy_sell_daily table is empty")
                return False
    except Exception as e:
        logger.error(f"[ERROR] Failed to check signals: {e}")
        return False


def check_eventbridge_scheduler():
    """Check EventBridge scheduler configuration."""
    logger.info("\n" + "=" * 70)
    logger.info("5. EVENTBRIDGE SCHEDULER CONFIGURATION")
    logger.info("=" * 70)

    try:
        scheduler = boto3.client("scheduler", region_name="us-east-1")

        # List schedules
        response = scheduler.list_schedules(MaxResults=50)
        algo_schedules = [s for s in response.get("Schedules", []) if "algo" in s["Name"].lower()]

        if not algo_schedules:
            logger.warning("[WARNING] No EventBridge schedules found with 'algo' in name")
            return False

        logger.info(f"[OK] Found {len(algo_schedules)} EventBridge schedules:")
        all_enabled = True
        for sched in algo_schedules:
            state = sched.get("State", "UNKNOWN")
            status = "✓" if state == "ENABLED" else "✗"
            logger.info(f"  {status} {sched['Name']}: {state}")
            if state != "ENABLED":
                all_enabled = False

        return all_enabled
    except ClientError as e:
        logger.warning(f"[WARNING] Could not access EventBridge: {e} (may lack AWS permissions)")
        return None  # Can't determine
    except Exception as e:
        logger.error(f"[ERROR] Failed to check EventBridge: {e}")
        return False


def check_lambda_function():
    """Check Lambda function configuration."""
    logger.info("\n" + "=" * 70)
    logger.info("6. LAMBDA FUNCTION CONFIGURATION")
    logger.info("=" * 70)

    try:
        lambda_client = boto3.client("lambda", region_name="us-east-1")

        # Get function configuration
        function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "algo-algo-dev")
        response = lambda_client.get_function(FunctionName=function_name)

        config = response["Configuration"]
        logger.info(f"[OK] Lambda function '{function_name}' configuration:")
        logger.info(f"  • Runtime: {config.get('Runtime')}")
        logger.info(f"  • Timeout: {config.get('Timeout')}s")
        logger.info(f"  • Memory: {config.get('MemorySize')}MB")
        logger.info(f"  • Reserved Concurrency: {config.get('ReservedConcurrentExecutions', 'Not set')}")

        # Check for recent errors in CloudWatch logs
        logs = boto3.client("logs", region_name="us-east-1")
        log_group = f"/aws/lambda/{function_name}"

        try:
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=1
            )

            if streams.get("logStreams"):
                latest_stream = streams["logStreams"][0]
                logger.info(f"  • Latest log stream: {latest_stream['logStreamName']}")

                # Get recent events
                events = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=latest_stream["logStreamName"],
                    limit=10
                )

                error_count = sum(1 for e in events["events"] if "ERROR" in e["message"] or "CRITICAL" in e["message"])
                if error_count > 0:
                    logger.warning(f"  [WARNING] {error_count} errors found in recent logs")
                    return False
        except Exception as e:
            logger.debug(f"Could not check CloudWatch logs: {e}")

        return True
    except ClientError as e:
        logger.warning(f"[WARNING] Could not access Lambda: {e} (may lack AWS permissions)")
        return None  # Can't determine
    except Exception as e:
        logger.error(f"[ERROR] Failed to check Lambda function: {e}")
        return False


def check_api_endpoints():
    """Check if API endpoints are responding."""
    logger.info("\n" + "=" * 70)
    logger.info("7. API ENDPOINT STATUS")
    logger.info("=" * 70)

    try:
        # This would require making HTTP requests to the API
        # Skip for now as it requires understanding the API endpoint configuration
        logger.info("[SKIPPED] API endpoint checks require endpoint URL configuration")
        return None
    except Exception as e:
        logger.error(f"[ERROR] Failed to check API endpoints: {e}")
        return False


def main():
    """Run all diagnostic checks."""
    logger.info("\n" + "=" * 70)
    logger.info("ALGO ORCHESTRATOR EXECUTION BLOCKER DIAGNOSTICS")
    logger.info("=" * 70)

    results = {
        "database": check_database_connectivity(),
        "orchestrator_runs": check_orchestrator_runs(),
        "data_loaders": check_data_loader_status(),
        "signals": check_signals(),
        "eventbridge": check_eventbridge_scheduler(),
        "lambda": check_lambda_function(),
        "api": check_api_endpoints(),
    }

    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    for check, result in results.items():
        status = "✓" if result is True else "✗" if result is False else "?" if result is None else "?"
        logger.info(f"  {status} {check}: {result}")

    failures = [k for k, v in results.items() if v is False]
    if failures:
        logger.warning(f"\n[BLOCKING ISSUES FOUND] {len(failures)} checks failed: {', '.join(failures)}")
        return 1
    else:
        logger.info("\n[OK] All diagnostic checks passed or were skipped (unavailable)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
