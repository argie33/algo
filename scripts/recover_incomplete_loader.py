#!/usr/bin/env python3
"""Manual recovery for incomplete loaders - re-trigger with optimal settings.

Usage:
    python scripts/recover_incomplete_loader.py              # Recover price_daily
    python scripts/recover_incomplete_loader.py --all        # Recover all critical loaders
    python scripts/recover_incomplete_loader.py --monitor    # Monitor without retry

Exit Codes:
    0 = Recovery succeeded or loader already complete
    1 = Recovery failed or timeout
"""

import sys
import time
import logging
import json
import argparse
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def check_loader_status(loader_name: str = "price_daily"):
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    symbols_loaded,
                    symbol_count,
                    ROUND(100.0 * symbols_loaded / NULLIF(symbol_count, 0), 1) as coverage_pct,
                    status,
                    error_message,
                    last_updated,
                    execution_started
                FROM data_loader_status
                WHERE table_name = %s
                ORDER BY last_updated DESC
                LIMIT 1
            """, (loader_name,))

            row = cur.fetchone()
            if not row:
                return None

            loaded, total, pct, status, error, updated, started = row
            return {
                'loader': loader_name,
                'loaded': loaded or 0,
                'total': total or 0,
                'coverage_pct': pct or 0.0,
                'status': status,
                'error': error,
                'last_updated': updated,
                'execution_started': started,
            }

    except Exception as e:
        logger.error(f"Database error: {e}")
        return None


def trigger_loader_retry(loader_name: str) -> bool:
    """Trigger loader retry via Lambda."""
    try:
        import os
        import boto3

        logger.info(f"Triggering retry for {loader_name}...")

        lambda_client = boto3.client(
            "lambda",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )

        response = lambda_client.invoke(
            FunctionName="algo-trigger-loaders",
            InvocationType="RequestResponse",
            Payload=json.dumps({"loader_name": loader_name}).encode("utf-8"),
        )

        if response.get("StatusCode") != 200 or response.get("FunctionError"):
            payload = response.get("Payload", {}).read().decode("utf-8") if response.get("Payload") else "{}"
            logger.error(f"Trigger failed: {payload}")
            return False

        logger.info(f"✅ Retry triggered for {loader_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to trigger retry: {e}")
        return False


def monitor_loader_recovery(loader_name: str, timeout_seconds: int = 600) -> tuple[bool, dict]:
    """Monitor loader status until recovery or timeout.

    Args:
        loader_name: Loader to monitor
        timeout_seconds: Max wait time (10 minutes = 600s typical)

    Returns:
        (recovered: bool, final_status: dict)
    """
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
    check_interval = 10  # Check every 10 seconds
    last_pct = 0.0
    check_count = 0

    while datetime.now(timezone.utc) < deadline:
        status = check_loader_status(loader_name)

        if not status:
            logger.warning("Could not check status (database error) — still waiting...")
            time.sleep(check_interval)
            continue

        pct = status['coverage_pct']
        check_count += 1

        # Show progress every 30 seconds
        if check_count % 3 == 0 or pct > last_pct:
            elapsed = timeout_seconds - int((deadline - datetime.now(timezone.utc)).total_seconds())
            logger.info(f"[{elapsed}s] {loader_name}: {pct:.1f}% ({status['loaded']}/{status['total']} symbols)")
            last_pct = pct

        if pct >= 75.0:
            logger.info(f"✅ RECOVERED: {loader_name} at {pct:.1f}% coverage")
            return True, status

        if status['status'] == 'COMPLETED' and pct < 75.0:
            logger.error(f"❌ Loader completed but still incomplete: {pct:.1f}%")
            if status['error']:
                logger.error(f"   Error: {status['error'][:150]}")
            return False, status

        time.sleep(check_interval)

    # Timeout
    final_status = check_loader_status(loader_name) or {}
    final_pct = final_status.get('coverage_pct', 0.0)
    logger.warning(
        f"⏱️ Timeout: {loader_name} still running after {timeout_seconds}s "
        f"(currently {final_pct:.1f}%). Will complete in background."
    )
    logger.info(f"   Check status: python scripts/verify_prices_loaded.py")
    return False, final_status


def recover_loader(loader_name: str = "price_daily", monitor_only: bool = False) -> int:
    """Recover a single loader.

    Returns:
        0 = Success or already recovered
        1 = Failed or timeout
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Recovering {loader_name}...")
    logger.info(f"{'='*60}\n")

    # Step 1: Check current status
    logger.info(f"📊 Checking {loader_name} status...")
    status = check_loader_status(loader_name)

    if not status:
        logger.error(f"Could not get status for {loader_name}")
        return 1

    pct = status['coverage_pct']
    logger.info(f"   Loaded: {status['loaded']}/{status['total']} ({pct:.1f}%)")
    logger.info(f"   Status: {status['status']}")
    logger.info(f"   Last updated: {status['last_updated']}")

    if pct >= 75.0:
        logger.info(f"✅ Already recovered ({pct:.1f}% >= 75%)")
        return 0

    if status['error']:
        logger.info(f"   Error: {status['error'][:150]}")

    if monitor_only:
        logger.info("\n⏳ Monitoring only (not triggering retry)...")
        recovered, final = monitor_loader_recovery(loader_name)
        return 0 if recovered else 1

    # Step 2: Trigger retry
    logger.info(f"\n⚡ Triggering retry...")
    if not trigger_loader_retry(loader_name):
        logger.error("Failed to trigger retry")
        return 1

    # Step 3: Monitor recovery
    logger.info(f"\n⏳ Waiting for recovery (up to 10 minutes)...\n")
    recovered, final_status = monitor_loader_recovery(loader_name)

    if recovered:
        logger.info(f"\n✅ SUCCESS: {loader_name} recovered to {final_status['coverage_pct']:.1f}%")
        logger.info(f"   Ready for trading. Run: python scripts/run_local_orchestrator.py --morning")
        return 0
    else:
        logger.warning(f"\n⚠️ INCOMPLETE: {loader_name} at {final_status.get('coverage_pct', 0):.1f}%")
        logger.info(f"   Still loading in background. Check status later:")
        logger.info(f"   python scripts/verify_prices_loaded.py")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Recover incomplete loaders from production issues"
    )
    parser.add_argument(
        "--loader",
        default="price_daily",
        help="Loader to recover (default: price_daily)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Recover all critical loaders (price_daily, market_health_daily, etc.)"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor without triggering new retry"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds (default: 600 = 10 minutes)"
    )

    args = parser.parse_args()

    critical_loaders = [
        "price_daily",
        "market_health_daily",
        "market_exposure_daily",
        "technical_data_daily",
    ]

    loaders_to_recover = critical_loaders if args.all else [args.loader]

    all_succeeded = True
    for loader in loaders_to_recover:
        result = recover_loader(loader, monitor_only=args.monitor)
        if result != 0:
            all_succeeded = False

    logger.info(f"\n{'='*60}")
    if all_succeeded:
        logger.info("✅ All loaders recovered successfully")
        logger.info(f"{'='*60}\n")
        return 0
    else:
        logger.warning("⚠️ Some loaders still incomplete (check status later)")
        logger.info(f"{'='*60}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
