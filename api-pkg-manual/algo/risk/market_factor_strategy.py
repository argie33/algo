#!/usr/bin/env python3
"""Market exposure factor calculation strategies.

Each factor is an independent strategy that computes one component of the
overall market exposure score. Factors implement a common interface enabling
composition and independent testing.
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
