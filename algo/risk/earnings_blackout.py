#!/usr/bin/env python3
"""Earnings date awareness and blackout enforcement.

Prevents entries ±N days around earnings announcements to avoid whipsaws.
Default: ±7 days from earnings date is a blackout period.
"""

import psycopg2
import psycopg2.errors
from utils.db import DatabaseContext
from datetime import timedelta, date as _date
from typing import Dict, Any
import logging
from algo.infrastructure import MarketCalendar

logger = logging.getLogger(__name__)

try:
    from algo.reporting import AlertManager
except ImportError:

    class AlertManager:  # type: ignore
        def critical(self, *args, **kwargs):
            pass


class EarningsBlackout:
    """Enforce earnings date blackout windows."""

    def __init__(self, config):
        if config is None:
            raise ValueError(
                "EarningsBlackout requires explicit config parameter (dependency injection)"
            )
        self.config = config
        self.days_before = int(self.config.get("earnings_blackout_days_before", 7))
        self.days_after = int(self.config.get("earnings_blackout_days_after", 3))

    def run(self, symbol: str, eval_date: _date) -> Dict[str, Any]:
        """Check if eval_date is in earnings blackout window (Issue #27: trading day aware).

        Uses MarketCalendar to compute trading days, not calendar days.
        If earnings_calendar table doesn't exist, passes through.
        """
        try:
            with DatabaseContext("read") as cur:
                # Issue #27: Compute trading day windows instead of calendar days
                # Count back N trading days before, forward N trading days after
                lookback_date = eval_date - timedelta(
                    days=self.days_before * 2
                )  # Conservative estimate
                lookahead_date = eval_date + timedelta(days=self.days_after * 2)

                cur.execute(
                    """SELECT earnings_date FROM earnings_calendar
                       WHERE symbol = %s
                       AND earnings_date >= %s
                       AND earnings_date <= %s
                       ORDER BY earnings_date LIMIT 1""",
                    (symbol, lookback_date, lookahead_date),
                )
                row = cur.fetchone()

            if row:
                earnings_date = row[0]
                # Count trading days between eval_date and earnings_date
                trading_days_away = 0
                current = eval_date
                direction = 1 if earnings_date >= eval_date else -1
                while current != earnings_date:
                    current += timedelta(days=direction)
                    if MarketCalendar.is_trading_day(current):
                        trading_days_away += 1

                # Check if within blackout window (in trading days, not calendar days)
                if trading_days_away <= (
                    self.days_after if direction > 0 else self.days_before
                ):
                    return {
                        "pass": False,
                        "reason": f"Earnings on {earnings_date} ({trading_days_away} trading days away)",
                    }

            return {
                "pass": True,
                "reason": f"No earnings in ±{self.days_before}/{self.days_after} trading days",
            }
        except psycopg2.errors.UndefinedTable:
            logger.info(
                f"Earnings calendar not yet populated; skipping blackout for {symbol}"
            )
            return {
                "pass": True,
                "reason": "Earnings calendar not available (pass-through)",
            }
        except Exception as e:
            logger.error(
                f"Earnings blackout check error for {symbol}: {e} — FAILING CLOSED (blocking trade)"
            )
            return {
                "pass": False,
                "reason": f"Earnings check failed: {str(e)[:50]} (fail-closed for safety)",
            }

    def get_upcoming_earnings(self, symbol: str, days_ahead: int = 30) -> list:
        """Get upcoming earnings for symbol."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT earnings_date FROM earnings_calendar
                       WHERE symbol = %s
                       AND earnings_date >= %s
                       AND earnings_date <= %s
                       ORDER BY earnings_date""",
                    (
                        symbol,
                        _date.today(),
                        _date.today() + timedelta(days=days_ahead),
                    ),
                )
                rows = cur.fetchall()

            return [{"date": row[0]} for row in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
            return []


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()
    eb = EarningsBlackout(config=config)

    # Test
    result = eb.run("AAPL", _date(2026, 5, 15))
    logger.info(f"AAPL earnings check (2026-05-15): {result}")

    upcoming = eb.get_upcoming_earnings("AAPL")
    logger.info(f"AAPL upcoming earnings: {upcoming}")
