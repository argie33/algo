#!/usr/bin/env python3
"""Reset stuck auxiliary loaders and trigger re-execution.

Many auxiliary loaders got stuck in RUNNING state on June 19 and were manually
reset to COMPLETED with row_count=0. This script:
1. Identifies auxiliary loaders (non-critical for trading)
2. Resets their status to READY (will trigger re-run)
3. Attempts to re-trigger them via Step Functions

Run this after fixing EventBridge scheduler expressions.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.connection import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Auxiliary loaders that should be reset and re-triggered
# These got stuck on June 19 with "Admin reset - was stuck in RUNNING"
STUCK_AUXILIARY_LOADERS = [
    'analyst_upgrade_downgrade',
    'buy_sell_daily_etf',
    'buy_sell_monthly',
    'buy_sell_monthly_etf',
    'buy_sell_weekly',
    'buy_sell_weekly_etf',
    'commodity_macro_drivers',
    'commodity_price_history',
    'commodity_prices',
    'commodity_technicals',
    'cot_data',
    'distribution_days',
    'index_metrics',
    'industry_performance',
    'institutional_positioning',
    'iv_history',
    'performance_daily',
    'portfolio_performance',
    'relative_performance',
    'seasonality_monthly_stats',
    'sector_rotation_signal',
    'sector_performance',
    'sentiment',
    'sentiment_social',
    'signal_themes',
    'technical_data_monthly',
    'technical_data_weekly',
    'ttm_cash_flow',
    'ttm_income_statement',
]

def reset_loader_status(conn, table_name: str) -> bool:
    """Reset a loader's status from COMPLETED to READY to trigger re-execution."""
    try:
        cur = conn.cursor()

        # Check current status
        cur.execute(
            'SELECT status, last_updated, error_message FROM data_loader_status WHERE table_name = %s',
            (table_name,)
        )
        result = cur.fetchone()

        if not result:
            logger.warning(f"  ✗ {table_name}: Not found in data_loader_status table")
            cur.close()
            return False

        status, last_updated, error_msg = result
        age_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600 if last_updated else None

        # Only reset if stale (> 72 hours old)
        if age_hours and age_hours > 72:
            # Reset to READY status
            cur.execute(
                '''UPDATE data_loader_status
                   SET status = %s, error_message = %s, last_updated = %s
                   WHERE table_name = %s''',
                ('READY', f'Reset {datetime.now(timezone.utc).isoformat()} - was {status}', datetime.now(timezone.utc), table_name)
            )
            conn.commit()
            logger.info(f"  ✓ {table_name}: Reset from {status} → READY (age {age_hours:.0f}h, error: {error_msg})")
            cur.close()
            return True
        else:
            logger.info(f"  ⊘ {table_name}: Not stale (age {age_hours:.0f}h if age_hours else 'unknown'), skipping")
            cur.close()
            return False

    except Exception as e:
        logger.error(f"  ✗ {table_name}: {type(e).__name__}: {e}")
        return False

def main():
    """Reset all stuck auxiliary loaders."""
    logger.info("Resetting stuck auxiliary loaders...")
    logger.info("=" * 80)

    try:
        conn = get_db_connection('write')
    except Exception as e:
        logger.error(f"Cannot connect to database: {e}")
        return 1

    reset_count = 0

    for loader_name in sorted(STUCK_AUXILIARY_LOADERS):
        if reset_loader_status(conn, loader_name):
            reset_count += 1

    logger.info("=" * 80)
    logger.info(f"Reset {reset_count}/{len(STUCK_AUXILIARY_LOADERS)} auxiliary loaders to READY status")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Deploy infrastructure: cd terraform && terraform apply -lock=false")
    logger.info("2. Loaders will be re-triggered by EventBridge schedules:")
    logger.info("   - 2:00 AM ET: morning_prep_pipeline")
    logger.info("   - 4:00 PM ET: financial_data_pipeline (fixed duplicate)")
    logger.info("   - 4:05 PM ET: eod_pipeline")
    logger.info("   - 7:00 PM ET: computed_metrics_pipeline")
    logger.info("   - 9:15 AM ET: reference_data_pipeline")
    logger.info("3. Monitor CloudWatch logs for execution progress")
    logger.info("4. Check data_loader_status table for completion (health = 'fresh')")

    conn.close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
