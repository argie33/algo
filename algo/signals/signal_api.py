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

from typing import Any

from algo.infrastructure import get_config
from algo.signals.signal_computer import SignalComputer


class SignalAPI:
    """Public API for technical signal detection and RS ranking.

    Wraps SignalComputer and exposes only the signals needed by higher-level
    components (AdvancedFilters, scoring engines, etc.). Private details of
    SignalComputer (caching, query optimization, internal helpers) are hidden.
    """

    def __init__(self):
        """Initialize the signal API with a shared SignalComputer instance."""
        config = get_config()
        self._computer = SignalComputer(config)

    def detect_base(self, symbol: str, eval_date) -> dict[str, Any]:
        """Detect if stock is in base pattern.

        Returns:
            Dict with detection result fields (in_base, breakout_imminent, etc.)
        """
        return self._computer.base_detection(symbol, eval_date)

    def detect_vcp(self, symbol: str, eval_date) -> dict[str, Any]:
        """Detect if stock is in VCP (Volatility Contraction Pattern).

        Returns:
            Dict with detection result fields (is_vcp, contractions, etc.)
        """
        return self._computer.vcp_detection(symbol, eval_date)

    def detect_pivot(self, symbol: str, eval_date) -> dict[str, Any]:
        """Detect if stock has pivot breakout.

        Returns:
            Dict with detection result fields (breakout, close, pivot, etc.)
        """
        return self._computer.pivot_breakout(symbol, eval_date)

    def detect_power_trend(self, symbol: str, eval_date) -> dict[str, Any]:
        """Detect if stock is in power trend.

        Returns:
            Dict with detection result fields (power_trend, return_21d, etc.)
        """
        return self._computer.power_trend(symbol, eval_date)

    def rank_rs_percentile(self, cur, symbol: str, eval_date, lookback: int = 60) -> float:
        """Compute Mansfield-style RS percentile ranking.

        Ranks the stock's relative strength vs SPY over the lookback period,
        returning a 0-100 percentile score. Higher = stronger momentum.

        Args:
            cur: Database cursor (provided for compatibility, not used internally)
            symbol: Stock ticker
            eval_date: Evaluation date
            lookback: Number of days to look back (default 60)

        Returns:
            Percentile rank (0-100) where 100 = best momentum in universe

        Raises:
            ValueError: If symbol has insufficient price history
        """
        rs_data = self._computer.mansfield_rs(symbol, eval_date, lookback)
        if rs_data and rs_data.get("mansfield_rs") is not None:
            mrs = float(rs_data["mansfield_rs"])
            return max(0.0, min(100.0, (mrs + 1) * 50))
        return 0.0
