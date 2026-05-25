#!/usr/bin/env python3
"""
On-Demand Data Refresh Script

Runs critical data loaders to refresh company profiles and stock scores.
Use this when data is stale or you need immediate updates.

Usage:
  python3 scripts/refresh_data_on_demand.py                # Run all
  python3 scripts/refresh_data_on_demand.py --profiles     # Only company profiles
  python3 scripts/refresh_data_on_demand.py --scores       # Only stock scores
  python3 scripts/refresh_data_on_demand.py --metrics      # Only metrics
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.env_loader import load_env
from utils.db_connection import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def refresh_company_profiles():
    """Refresh company profile data."""
    logger.info("=" * 70)
    logger.info("REFRESHING: Company Profiles")
    logger.info("=" * 70)

    try:
        from loaders.load_company_profile import CompanyProfileLoader

        loader = CompanyProfileLoader()
        symbols = loader.get_active_symbols()

        if not symbols:
            logger.warning("No symbols found to load")
            return False

        logger.info(f"Loading profiles for {len(symbols)} symbols...")
        result = loader.load_incremental(None)

        if result:
            logger.info(f"✓ Successfully loaded company profiles")

            # Verify data freshness
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT MAX(created_at) FROM company_profile")
                max_date = cur.fetchone()[0]
                cur.close()
                conn.close()

                if max_date:
                    age = (datetime.now() - max_date.replace(tzinfo=None)).days
                    logger.info(f"  Newest record age: {age} days")
                    if age > 1:
                        logger.warning(f"  ⚠ Data is {age} days old (consider running again)")

            return True
        else:
            logger.error("✗ Failed to load company profiles")
            return False

    except Exception as e:
        logger.error(f"✗ Error loading company profiles: {e}", exc_info=True)
        return False


def refresh_stock_scores():
    """Refresh stock scores data."""
    logger.info("=" * 70)
    logger.info("REFRESHING: Stock Scores & Metrics")
    logger.info("=" * 70)

    try:
        from loaders.load_algo_metrics_daily import AlgoMetricsLoader

        loader = AlgoMetricsLoader()
        symbols = loader.get_active_symbols()

        if not symbols:
            logger.warning("No symbols found to load")
            return False

        logger.info(f"Loading metrics for {len(symbols)} symbols...")
        result = loader.load_incremental(None)

        if result:
            logger.info(f"✓ Successfully loaded stock scores and metrics")

            # Verify data freshness
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT MAX(created_at) FROM stock_scores")
                max_date = cur.fetchone()[0]
                cur.close()
                conn.close()

                if max_date:
                    age = (datetime.now() - max_date.replace(tzinfo=None)).days
                    logger.info(f"  Newest record age: {age} days")
                    if age > 1:
                        logger.warning(f"  ⚠ Data is {age} days old (consider running again)")

            return True
        else:
            logger.error("✗ Failed to load stock scores")
            return False

    except Exception as e:
        logger.error(f"✗ Error loading stock scores: {e}", exc_info=True)
        return False


def refresh_growth_metrics():
    """Refresh growth metrics."""
    logger.info("=" * 70)
    logger.info("REFRESHING: Growth Metrics")
    logger.info("=" * 70)

    try:
        from loaders.load_growth_metrics import GrowthMetricsLoader

        loader = GrowthMetricsLoader()
        symbols = loader.get_active_symbols()

        if not symbols:
            logger.warning("No symbols found to load")
            return False

        logger.info(f"Loading growth metrics for {len(symbols)} symbols...")
        result = loader.load_incremental(None)

        if result:
            logger.info(f"✓ Successfully loaded growth metrics")
            return True
        else:
            logger.error("✗ Failed to load growth metrics")
            return False

    except Exception as e:
        logger.error(f"✗ Error loading growth metrics: {e}", exc_info=True)
        return False


def verify_data_freshness():
    """Verify data freshness across critical tables."""
    logger.info("=" * 70)
    logger.info("DATA FRESHNESS CHECK")
    logger.info("=" * 70)

    conn = get_db_connection()
    if not conn:
        logger.error("✗ Could not connect to database")
        return False

    try:
        cur = conn.cursor()

        tables = [
            ('price_daily', 'Prices'),
            ('technical_data_daily', 'Technicals'),
            ('buy_sell_daily', 'Signals'),
            ('company_profile', 'Company Profiles'),
            ('stock_scores', 'Stock Scores'),
        ]

        all_fresh = True
        for table, label in tables:
            cur.execute(f"SELECT MAX(created_at) FROM {table}")
            result = cur.fetchone()
            max_date = result[0] if result else None

            if max_date:
                age = (datetime.now() - max_date.replace(tzinfo=None)).days
                status = "✓" if age <= 1 else "⚠"
                logger.info(f"  {status} {label:.<25} {age:>2} days old")

                if age > 7:
                    all_fresh = False
                    logger.warning(f"    CRITICAL: Data is {age} days old!")
            else:
                logger.warning(f"  ✗ {label:.<25} NO DATA")
                all_fresh = False

        cur.close()
        return all_fresh

    except Exception as e:
        logger.error(f"✗ Error checking data freshness: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def main():
    """Main entry point."""
    load_env()

    parser = argparse.ArgumentParser(
        description="Refresh critical data on demand",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/refresh_data_on_demand.py              # Refresh all
  python3 scripts/refresh_data_on_demand.py --profiles   # Only profiles
  python3 scripts/refresh_data_on_demand.py --scores     # Only scores
  python3 scripts/refresh_data_on_demand.py --metrics    # Only metrics
        """
    )

    parser.add_argument('--profiles', action='store_true', help='Refresh company profiles only')
    parser.add_argument('--scores', action='store_true', help='Refresh stock scores only')
    parser.add_argument('--metrics', action='store_true', help='Refresh growth/quality metrics')
    parser.add_argument('--verify', action='store_true', help='Verify data freshness only')

    args = parser.parse_args()

    # If no specific option, run all
    run_all = not (args.profiles or args.scores or args.metrics or args.verify)

    results = {}

    try:
        if args.verify or run_all:
            results['freshness_check'] = verify_data_freshness()

        if args.profiles or run_all:
            results['profiles'] = refresh_company_profiles()

        if args.scores or run_all:
            results['scores'] = refresh_stock_scores()

        if args.metrics or run_all:
            results['metrics'] = refresh_growth_metrics()

        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("REFRESH SUMMARY")
        logger.info("=" * 70)

        for task, success in results.items():
            status = "✓ PASSED" if success else "✗ FAILED"
            logger.info(f"  {task:.<30} {status}")

        all_success = all(results.values())

        if all_success:
            logger.info("")
            logger.info("✓ All data refresh operations completed successfully")
            return 0
        else:
            logger.warning("")
            logger.warning("✗ Some refresh operations failed - check logs above")
            return 1

    except KeyboardInterrupt:
        logger.info("")
        logger.info("User interrupted - stopping refresh")
        return 130
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
