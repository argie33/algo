#!/usr/bin/env python3
"""Circuit breaker to halt trading when signals are stale (ROOT CAUSE #4 fix)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


class StaleSignalCircuitBreaker:
    """Prevent trading when signals are based on stale price data.

    Threshold: price_daily's latest date must be no older than the most recent trading
    day strictly before today - i.e. up to one trading day of lag is normal (the EOD
    loader publishes day D's close sometime after D's market close, so the freshest data
    available before D+1's own close is D's). This is trading-day-aware, not a flat
    calendar-day count: it correctly tolerates a 3-calendar-day gap on a Monday (Friday's
    close) or a longer gap after a holiday, the same way Phase 1 (price_daily) and
    Phase 7 (buy_sell_daily lookback) already do.
    """

    @staticmethod
    def check_signal_freshness() -> tuple[bool, str]:
        """Check if signals are based on fresh price data (ROOT CAUSE #4 fix).

        The real metric is not signal DATE but DATA FRESHNESS:
        - Are signals generated from the LATEST AVAILABLE price data?
        - Is that price data not too old?

        Returns:
            (is_safe: bool, message: str)
            - is_safe=True if signals based on current price data
            - is_safe=False if signals based on stale price data
        """
        from datetime import timedelta
        from algo.infrastructure import MarketCalendar

        try:
            with DatabaseContext("read") as cur:
                # Get latest price data available
                cur.execute("SELECT MAX(date) FROM price_daily")
                row = cur.fetchone()
                latest_price_date = row[0] if row and row[0] is not None else None

                # Get latest signal data available
                cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                row = cur.fetchone()
                latest_signal_date = row[0] if row and row[0] is not None else None

                if not latest_signal_date or not latest_price_date:
                    return False, "No signals or prices in database"

                # Check if signals lag price data by more than 1 trading day
                # Normal operation: price_daily has today's close, signals computed from yesterday's data = 1 day lag
                # This is acceptable - today's technical indicators need yesterday's close to compute them.
                # Block only if lag exceeds 1 trading day (indicates signal generation stalled or price loader is fresh)
                if latest_signal_date < latest_price_date:
                    gap_days = (latest_price_date - latest_signal_date).days

                    # Allow up to 1 trading day of lag (normal case)
                    # Get the trading day strictly before latest_price_date
                    expected_signal_date = MarketCalendar.get_previous_trading_day(
                        latest_price_date - timedelta(days=1)
                    )

                    if expected_signal_date and latest_signal_date < expected_signal_date:
                        # Gap exceeds 1 trading day - signals are truly stale
                        msg = f"Signals lag price data by {gap_days}d (signals from old data)"
                        logger.critical(f"CIRCUIT BREAKER OPEN: {msg}")
                        return False, msg
                    else:
                        # Lag is 1 trading day or less (normal) - signals are FRESH
                        logger.info(
                            f"Signals lag price data by {gap_days}d (normal): "
                            f"price_daily={latest_price_date}, signals={latest_signal_date}"
                        )

                # Check if price data itself is too old, relative to the actual previous
                # trading day (not a flat weekday/weekend calendar-day count - see class
                # docstring). CRITICAL FIX (2026-07-27): the old flat threshold (1 calendar
                # day on weekdays) fired on every Monday and every post-holiday trading day,
                # since Friday's close is always >=3 calendar days old by Monday even though
                # it's the correct, most-recent-available data. Reproduced live: real
                # wall-clock Monday 2026-07-27, real price_daily MAX=2026-07-24 (Friday),
                # would have blocked every Phase 8 entry all session.
                now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()
                expected_min_price_date = MarketCalendar.get_previous_trading_day(now_et - timedelta(days=1))

                if expected_min_price_date and latest_price_date < expected_min_price_date:
                    days_old = (now_et - latest_price_date).days
                    msg = (
                        f"Price data {days_old}d old (latest: {latest_price_date}, "
                        f"expected at least {expected_min_price_date})"
                    )
                    logger.warning(f"CIRCUIT BREAKER OPEN: {msg}")
                    return False, msg

                # Signals are based on latest available price data
                msg = f"Signals FRESH: based on latest price data ({latest_signal_date})"
                logger.info(msg)
                return True, msg

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            msg = f"Operation failed: {e}. Circuit breaker check failed: {e}"
            raise RuntimeError(msg) from e

    @staticmethod
    def assert_signals_fresh() -> None:
        """Raise exception if signals are stale. Call before trading operations."""
        is_safe, message = StaleSignalCircuitBreaker.check_signal_freshness()
        if not is_safe:
            logger.critical(f"HALTING TRADING: {message}")
            raise RuntimeError(f"CIRCUIT BREAKER: {message}")


def protect_trading_operation(func: Any) -> Any:
    """Decorator to halt trading operations if signals are stale."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        is_safe, message = StaleSignalCircuitBreaker.check_signal_freshness()
        if not is_safe:
            logger.critical(f"BLOCKING OPERATION: {message}")
            raise RuntimeError(f"Trading blocked: {message}")
        return func(*args, **kwargs)

    return wrapper
