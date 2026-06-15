#!/usr/bin/env python3
"""Circuit breaker to halt trading when signals are stale (ROOT CAUSE #4 fix)."""

import logging
from datetime import datetime, timezone
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class StaleSignalCircuitBreaker:
    """Prevent trading when signals are based on stale price data.

    Threshold varies by day:
    - Weekdays: Price data must be <24 hours old (same-day or previous day)
    - Weekends: Price data must be from latest trading day (Fri-Sat/Sun is OK)
    """

    WEEKDAY_STALE_THRESHOLD_HOURS = 24  # During trading week
    WEEKEND_STALE_THRESHOLD_HOURS = 72  # During weekends (Fri EOD acceptable Sat/Sun)

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
        try:
            with DatabaseContext("read") as cur:
                # Get latest price data available
                cur.execute("SELECT MAX(date) FROM price_daily")
                latest_price_date = cur.fetchone()[0]

                # Get latest signal data available
                cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                latest_signal_date = cur.fetchone()[0]

                if not latest_signal_date or not latest_price_date:
                    return False, "No signals or prices in database"

                # Check if signals are based on latest price data
                if latest_signal_date < latest_price_date:
                    gap_days = (latest_price_date - latest_signal_date).days
                    msg = (
                        f"Signals lag price data by {gap_days}d (signals from old data)"
                    )
                    logger.critical(f"CIRCUIT BREAKER OPEN: {msg}")
                    return False, msg

                # Check if price data itself is too old (varies by day of week)
                from algo.infrastructure import MarketCalendar

                now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()
                price_age_hours = (now_et - latest_price_date).days * 24

                # Determine threshold based on whether today is a trading day
                is_trading_today = MarketCalendar.is_trading_day(now_et)
                threshold = (
                    StaleSignalCircuitBreaker.WEEKDAY_STALE_THRESHOLD_HOURS
                    if is_trading_today
                    else StaleSignalCircuitBreaker.WEEKEND_STALE_THRESHOLD_HOURS
                )

                if price_age_hours >= threshold:
                    msg = f"Price data {price_age_hours}h old (exceeds {threshold}h threshold)"
                    logger.warning(f"CIRCUIT BREAKER OPEN: {msg}")
                    return False, msg

                # Signals are based on latest available price data
                msg = (
                    f"Signals FRESH: based on latest price data ({latest_signal_date})"
                )
                logger.info(msg)
                return True, msg

        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return False, f"Circuit breaker check failed: {e}"

    @staticmethod
    def assert_signals_fresh() -> None:
        """Raise exception if signals are stale. Call before trading operations."""
        is_safe, message = StaleSignalCircuitBreaker.check_signal_freshness()
        if not is_safe:
            logger.critical(f"HALTING TRADING: {message}")
            raise RuntimeError(f"CIRCUIT BREAKER: {message}")

def protect_trading_operation(func):
    """Decorator to halt trading operations if signals are stale."""

    def wrapper(*args, **kwargs):
        is_safe, message = StaleSignalCircuitBreaker.check_signal_freshness()
        if not is_safe:
            logger.critical(f"BLOCKING OPERATION: {message}")
            raise RuntimeError(f"Trading blocked: {message}")
        return func(*args, **kwargs)

    return wrapper
