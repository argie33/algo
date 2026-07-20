#!/usr/bin/env python3
"""Manually trigger critical loaders to ensure data is fresh.

SESSION 289 FIX: Metric loaders not executing automatically via EventBridge.
This script manually triggers the critical loaders to get fresh data for orchestrator.
"""

import logging
import sys

from utils.db.context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Critical loaders that must run for orchestrator to function
CRITICAL_LOADERS = {
    "stock_scores": "load_stock_scores",
    "market_exposure": "load_market_exposure_daily",
    "buy_sell": "load_buy_sell_daily",
}


def trigger_loader(loader_name: str) -> bool:
    """Trigger a loader to run. Returns True if successful."""
    try:
        logger.info(f"Triggering loader: {loader_name}")

        # Import the loader module dynamically
        loader_module = __import__(f"loaders.{CRITICAL_LOADERS[loader_name]}", fromlist=[""])

        # Check if loader has a run function
        if hasattr(loader_module, "run"):
            logger.info(f"  Running {loader_name} via run() function")
            result = loader_module.run()
            logger.info(f"  Result: {result}")
            return True
        else:
            logger.error(f"  No run() function found in {loader_module}")
            return False

    except Exception as e:
        logger.error(f"Failed to trigger {loader_name}: {type(e).__name__}: {e}")
        return False


def check_loader_freshness() -> dict:
    """Check if critical loaders have fresh data."""
    try:
        with DatabaseContext("read") as cur:
            status = {}

            critical_tables = {
                "stock_scores": "Should have composite_score values",
                "market_exposure_daily": "Should have exposure percentages",
                "buy_sell_daily": "Should have BUY/SELL signals",
            }

            for table, description in critical_tables.items():
                cur.execute(f"""
                SELECT COUNT(*) as total,
                       COUNT(DISTINCT DATE(updated_at)) as distinct_dates
                FROM {table}
                WHERE updated_at > NOW() - INTERVAL '24 hours'
                """)

                total, dates = cur.fetchone()
                status[table] = {
                    "rows": total,
                    "dates": dates,
                    "fresh": total > 0,
                    "description": description,
                }
                logger.info(f"  {table:30s}: {total:7d} rows from {dates} dates - {description}")

            return status

    except Exception as e:
        logger.error(f"Failed to check loader freshness: {e}")
        return {}


def main() -> int:
    """Main entry point."""
    logger.info("=== CRITICAL LOADER TRIGGER ===\n")

    # First, check current status
    logger.info("1. Checking current data freshness...")
    check_loader_freshness()

    # Trigger loaders
    logger.info("\n2. Triggering critical loaders...")
    results = {}
    for loader_key, _loader_name in CRITICAL_LOADERS.items():
        success = trigger_loader(loader_key)
        results[loader_key] = success
        if success:
            logger.info(f"  SUCCESS: {loader_key}")
        else:
            logger.error(f"  FAILED: {loader_key}")

    # Check status after
    logger.info("\n3. Checking data freshness after load...")
    check_loader_freshness()

    # Summary
    logger.info("\n=== SUMMARY ===\n")
    success_count = sum(1 for v in results.values() if v)
    logger.info(f"Loaders triggered: {success_count}/{len(results)} successful")

    if success_count > 0:
        logger.info("\nData should now be fresher. Orchestrator should work correctly.")
        return 0
    else:
        logger.error("\nNo loaders triggered successfully. Check error logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
