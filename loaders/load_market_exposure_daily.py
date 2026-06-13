#!/usr/bin/env python3

"""
Load market_exposure_daily: Compute market regime + exposure % from price & market health data.

Runs during EOD pipeline (4:05 PM ET) to ensure market regime is available for dashboard
regardless of orchestrator halt status. If orchestrator Phase 3b halts before running,
this loader ensures MarketsHealth page has regime display.

Purpose:
- Computes daily market exposure percentage (0-100) from 12 quantitative factors
- Determines market regime (confirmed_uptrend, uptrend_under_pressure, caution, correction)
- Persists to market_exposure_daily table for API + dashboard consumption
- Runs independently of orchestrator to guarantee availability

Time: ~2-5 seconds (vectorized computation, minimal DB load)
"""

import sys
import os
import logging
from datetime import date as _date

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Compute and persist market_exposure_daily for latest trading date."""
    try:
        from algo.algo_market_exposure import MarketExposure
        from utils.database_context import DatabaseContext

        # Determine the latest trading date from price_daily
        latest_date = None
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1"
            )
            result = cur.fetchone()
            if result:
                latest_date = result[0]

        if not latest_date:
            logger.error("No price data available for SPY — cannot compute market exposure")
            sys.exit(1)

        logger.info(f"Computing market exposure for {latest_date}")

        # Compute market exposure (this persists to DB automatically)
        me = MarketExposure()
        result = me.compute(latest_date, force_recompute=True)

        if result.get('success') is False:
            logger.error(f"Market exposure computation failed: {result.get('error')}")
            sys.exit(1)

        logger.info(f"✓ Market exposure computed:")
        logger.info(f"  Regime: {result.get('regime')}")
        logger.info(f"  Exposure: {result.get('exposure_pct')}%")
        logger.info(f"  Raw score: {result.get('raw_score')}")

        if result.get('halt_reasons'):
            logger.info(f"  Halt reasons: {'; '.join(result['halt_reasons'])}")

        logger.info("✓ Loader completed successfully")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Market exposure loader failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
