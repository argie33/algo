#!/usr/bin/env python3
"""Bootstrap missing dashboard data to resolve 503 errors.

Populates circuit_breaker_status and market_sentiment tables with initial data
so dashboard doesn't return 503 errors while loaders run on their schedule.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
import psycopg2
import psycopg2.extras

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


def bootstrap_circuit_breaker_status() -> None:
    """Populate circuit_breaker_status table with today's data if empty."""
    with DatabaseContext("write", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        today = datetime.now(EASTERN_TZ).date()

        # Check if data already exists
        cur.execute("SELECT 1 FROM circuit_breaker_status WHERE check_date = %s", (today,))
        if cur.fetchone():
            logger.info(f"Circuit breaker data already exists for {today}")
            return

        # Insert safe default values
        cur.execute("""
            INSERT INTO circuit_breaker_status (
                check_date, portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
                consecutive_losses, open_risk_pct, vix_level, market_stage,
                spy_prior_day_change_pct, win_rate_last_30_pct,
                triggered_count, any_triggered
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            today,
            Decimal("0.00"),     # portfolio_drawdown_pct
            Decimal("0.00"),     # daily_loss_pct
            Decimal("0.00"),     # weekly_loss_pct
            0,                    # consecutive_losses
            Decimal("0.00"),     # open_risk_pct
            Decimal("20.00"),    # vix_level (reasonable default)
            2,                    # market_stage (neutral)
            Decimal("0.00"),     # spy_prior_day_change_pct
            Decimal("50.00"),    # win_rate_last_30_pct (neutral default)
            0,                    # triggered_count
            False,                # any_triggered
        ))
        logger.info(f"Bootstrapped circuit_breaker_status for {today}")


def bootstrap_market_sentiment() -> None:
    """Populate market_sentiment table with today's data if empty."""
    with DatabaseContext("write", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        today = datetime.now(EASTERN_TZ).date()

        # Check if data already exists
        cur.execute("SELECT 1 FROM market_sentiment WHERE date = %s", (today,))
        if cur.fetchone():
            logger.info(f"Market sentiment data already exists for {today}")
            return

        # Insert safe default values (neutral fear/greed, balanced sentiment)
        cur.execute("""
            INSERT INTO market_sentiment (
                date, fear_greed_index, put_call_ratio, vix, sentiment_score,
                bullish_pct, bearish_pct, neutral_pct
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            today,
            Decimal("50.0000"),  # fear_greed_index (neutral: 50 out of 100)
            Decimal("1.0000"),   # put_call_ratio (neutral: ~1.0)
            Decimal("20.0000"),  # vix (normal)
            Decimal("0.0000"),   # sentiment_score (neutral)
            Decimal("33.33"),    # bullish_pct
            Decimal("33.33"),    # bearish_pct
            Decimal("33.34"),    # neutral_pct
        ))
        logger.info(f"Bootstrapped market_sentiment for {today}")


def main() -> None:
    """Bootstrap missing data."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        logger.info("Bootstrapping missing dashboard data...")
        bootstrap_circuit_breaker_status()
        bootstrap_market_sentiment()
        logger.info("Bootstrap complete")
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
