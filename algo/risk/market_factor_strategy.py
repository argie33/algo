#!/usr/bin/env python3
"""Market exposure factor calculation strategies.

Each factor is an independent strategy that computes one component of the
overall market exposure score. Factors implement a common interface enabling
composition and independent testing.

DEAD CODE - CONFIRMED UNUSED (2026-08-10): this base class and every subclass under
algo/risk/factors/ are never imported outside that package - see
algo/risk/factors/__init__.py for the full explanation. Production market exposure
scoring runs through algo/risk/market_factor_calculator.py's MarketFactorCalculator
instead, a separate class with the same responsibilities that has drifted from this
one. Do not assume fixing a bug here changes real trading behavior.
"""

from abc import ABC, abstractmethod
from typing import Any

from utils.db.context import DatabaseContext


class MarketFactorStrategy(ABC):
    """Base class for market exposure factor calculations.

    Enables composition: MarketExposure orchestrates multiple strategies,
    each responsible for one factor, decoupled from overall scoring logic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Factor name (e.g., 'trend_30wk', 'vix', 'momentum')."""
        ...

    @property
    @abstractmethod
    def weight(self) -> float:
        """Weight in overall score (0-100 scale, sum across all factors = 100)."""
        ...

    @abstractmethod
    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate factor value and scoring details.

        Args:
            eval_date: Date to evaluate
            cur: Database cursor

        Returns dict with:
            - score: float (0-100), the factor's contribution
            - reason: str, explanation of calculation
            - error: str (optional), if calculation failed
            - details: dict (optional), diagnostic data
        """
        ...

    def _with_cursor(self, operation: Any) -> Any:
        """Execute operation with a read-only database cursor."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except Exception as e:
            raise RuntimeError(f"Database operation failed: {e}") from e
