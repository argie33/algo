#!/usr/bin/env python3
"""SignalAPI - Public contract for technical signal queries.

Provides a clean facade over SignalComputer's detection and ranking methods.
Clients (AdvancedFilters, scoring engines) use this public API instead of
accessing private methods on SignalComputer.

This design:
- Decouples clients from SignalComputer internals
- Makes signal dependencies explicit and testable
- Allows SignalComputer refactoring without breaking clients
- Centralizes all signal query logic in one place
"""

from typing import cast

from algo.signals.signal_computer import SignalComputer


class SignalAPI:
    """Public API for technical signal detection and RS ranking.

    Wraps SignalComputer and exposes only the signals needed by higher-level
    components (AdvancedFilters, scoring engines, etc.). Private details of
    SignalComputer (caching, query optimization, internal helpers) are hidden.
    """

    def __init__(self):
        """Initialize the signal API with a shared SignalComputer instance."""
        self._computer = SignalComputer()

    def detect_base(self, symbol: str, eval_date) -> bool:
        """Detect if stock is in base pattern.

        Args:
            symbol: Stock ticker
            eval_date: Evaluation date

        Returns:
            True if stock matches base detection criteria, False otherwise
        """
        return cast(bool, self._computer.base_detection(symbol, eval_date))

    def detect_vcp(self, symbol: str, eval_date) -> bool:
        """Detect if stock is in VCP (Volatility Contraction Pattern).

        Args:
            symbol: Stock ticker
            eval_date: Evaluation date

        Returns:
            True if stock matches VCP detection criteria, False otherwise
        """
        return cast(bool, self._computer.vcp_detection(symbol, eval_date))

    def detect_pivot(self, symbol: str, eval_date) -> bool:
        """Detect if stock has pivot breakout.

        Args:
            symbol: Stock ticker
            eval_date: Evaluation date

        Returns:
            True if stock matches pivot breakout criteria, False otherwise
        """
        return cast(bool, self._computer.pivot_breakout(symbol, eval_date))

    def detect_power_trend(self, symbol: str, eval_date) -> bool:
        """Detect if stock is in power trend.

        Args:
            symbol: Stock ticker
            eval_date: Evaluation date

        Returns:
            True if stock matches power trend criteria, False otherwise
        """
        return cast(bool, self._computer.power_trend(symbol, eval_date))

    def rank_rs_percentile(self, cur, symbol: str, eval_date, lookback: int = 60) -> float:
        """Compute Mansfield-style RS percentile ranking.

        Ranks the stock's relative strength vs SPY over the lookback period,
        returning a 0-100 percentile score. Higher = stronger momentum.

        This method encapsulates the batch-cached percentile computation that
        was previously accessed as a private method (_rs_percentile_vs_spy).

        Args:
            cur: Database cursor (will be passed to SignalComputer)
            symbol: Stock ticker
            eval_date: Evaluation date
            lookback: Number of days to look back (default 60)

        Returns:
            Percentile rank (0-100) where 100 = best momentum in universe

        Raises:
            ValueError: If symbol has insufficient price history
        """
        return cast(float, self._computer._rs_percentile_vs_spy(cur, symbol, eval_date, lookback))

    def compute_period_return(self, cur, symbol: str, end_date, lookback_days: int) -> float:
        """Compute simple period return.

        Args:
            cur: Database cursor
            symbol: Stock ticker
            end_date: End date for return calculation
            lookback_days: Number of days to look back

        Returns:
            Simple return as decimal (e.g., 0.15 for +15%)

        Raises:
            ValueError: If price data is missing or invalid
        """
        return cast(float, self._computer._period_return(cur, symbol, end_date, lookback_days))

    def clear_cache(self):
        """Clear all internal signal caches.

        Use after bulk operations or when stale data is suspected.
        """
        self._computer.clear_cache()
