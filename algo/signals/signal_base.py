#!/usr/bin/env python3
"""Signal Base - Common interface for all signal types."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from algo.infrastructure.config.sql_intervals import get_interval_sql


class SignalBase(ABC):
    """Abstract base class for all signal types (momentum, patterns, options, swing)."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.signal_type = self.__class__.__name__

    @abstractmethod
    def generate(self, symbol: str, data: dict[str, Any]) -> dict[str, Any] | None: ...

    def format_signal(self, symbol: str, strength: float, reason: str) -> dict[str, Any]:
        """Standard signal formatting."""
        return {
            "symbol": symbol,
            "signal_type": self.signal_type,
            "strength": max(0, min(100, strength)),
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _period_return(self, cur: Any, symbol: str, end_date: Any, lookback_days: int) -> float:
        """Compute simple return over a lookback period.

        Args:
            cur: Database cursor
            symbol: Stock symbol
            end_date: End date for return calculation
            lookback_days: Number of days to look back

        Returns:
            Simple return as decimal (e.g., 0.15 for +15%)

        Raises:
            ValueError: If price data is missing or invalid for the period
        """
        interval_1d = get_interval_sql("1d")
        cur.execute(
            f"""
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - (%s * {interval_1d})
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(
                f"Period return data missing for {symbol} on {end_date} ({lookback_days}d lookback) - insufficient price history"
            )
        recent = float(row[0])
        oldest = float(row[1])
        if oldest <= 0:
            raise ValueError(f"Invalid historical price for {symbol}: oldest close {oldest} <= 0")
        return (recent - oldest) / oldest
