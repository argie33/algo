#!/usr/bin/env python3
"""Circuit breaker to halt trading when signals are stale (ROOT CAUSE #4 fix)."""

import logging
from datetime import datetime, timedelta, timezone
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class StaleSignalCircuitBreaker:
    """Prevent trading when signals are too stale (>24 hours)."""

    STALE_THRESHOLD_HOURS = 24  # Halt trading if signals older than this

    @staticmethod
    def check_signal_freshness() -> tuple[bool, str]:
        """Check if signals are fresh enough for trading.

        Returns:
            (is_safe: bool, message: str)
            - is_safe=True if signals fresh (<24 hours)
            - is_safe=False if signals stale (≥24 hours)
        """
        try:
            with DatabaseContext('read') as cur:
                cur.execute('SELECT MAX(date) FROM buy_sell_daily')
                max_signal_date = cur.fetchone()[0]

                if not max_signal_date:
                    return False, "No signals in database"

                now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()
                signal_age_hours = (now_et - max_signal_date).days * 24

                if signal_age_hours >= StaleSignalCircuitBreaker.STALE_THRESHOLD_HOURS:
                    msg = f"CIRCUIT BREAKER OPEN: Signals {signal_age_hours}h stale (threshold: {StaleSignalCircuitBreaker.STALE_THRESHOLD_HOURS}h)"
                    logger.critical(msg)
                    return False, msg
                else:
                    msg = f"Signals fresh: {signal_age_hours}h old (safe for trading)"
                    logger.info(msg)
                    return True, msg

        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            # Fail-safe: block trading if we can't verify freshness
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
