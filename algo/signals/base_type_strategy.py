#!/usr/bin/env python3
"""Strategy pattern for base type stop-loss calculations.

Each base type (cup_with_handle, flat_base, vcp, etc.) gets its own strategy.
Eliminates 6-branch if-elif chain in signal_patterns.py.
"""

from abc import ABC, abstractmethod


class BaseTypeStrategy(ABC):
    """Base strategy for calculating stop loss based on base type."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Base type name (e.g., 'cup_with_handle', 'flat_base')."""
        ...

    @property
    @abstractmethod
    def lookback_days(self) -> int:
        """Number of days to look back for price low."""
        ...

    @property
    @abstractmethod
    def discount_factor(self) -> float:
        """Multiplier for stop price (e.g., 0.99 = 1% below low)."""
        ...

    @abstractmethod
    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        """Calculate stop price and reasoning.

        Args:
            low_price: The calculated low price from lookback period
            atr: Average True Range
            entry_price: Entry price

        Returns:
            (stop_price, reasoning_text)
        """
        ...


class CupWithHandleStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "cup_with_handle"

    @property
    def lookback_days(self) -> int:
        return 7

    @property
    def discount_factor(self) -> float:
        return 0.99

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price * self.discount_factor
        reasoning = f"Cup-handle: 1% below handle low ${low_price:.2f}"
        return candidate, reasoning


class FlatBaseStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "flat_base"

    @property
    def lookback_days(self) -> int:
        return 35

    @property
    def discount_factor(self) -> float:
        return 0.995

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price * self.discount_factor
        reasoning = f"Flat base: 0.5% below base low ${low_price:.2f}"
        return candidate, reasoning


class VCPStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "vcp"

    @property
    def lookback_days(self) -> int:
        return 10

    @property
    def discount_factor(self) -> float:
        return 0.99

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price * self.discount_factor
        reasoning = f"VCP: 1% below last contraction low ${low_price:.2f}"
        return candidate, reasoning


class DoubleBottomStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "double_bottom"

    @property
    def lookback_days(self) -> int:
        return 20

    @property
    def discount_factor(self) -> float:
        return 1.0  # Special case: uses ATR offset instead of multiplier

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price - (0.5 * atr)
        reasoning = f"Double-bottom: 2nd low ${low_price:.2f} - 0.5x ATR (${atr:.2f})"
        return candidate, reasoning


class AscendingBaseStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "ascending_base"

    @property
    def lookback_days(self) -> int:
        return 14

    @property
    def discount_factor(self) -> float:
        return 0.985

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price * self.discount_factor
        reasoning = f"Ascending base: 1.5% below last higher low ${low_price:.2f}"
        return candidate, reasoning


class SaucerStrategy(BaseTypeStrategy):
    @property
    def name(self) -> str:
        return "saucer"

    @property
    def lookback_days(self) -> int:
        return 60

    @property
    def discount_factor(self) -> float:
        return 0.99

    def calculate(self, low_price: float, atr: float, entry_price: float) -> tuple[float, str]:
        candidate = low_price * self.discount_factor
        reasoning = f"Saucer: 1% below saucer low ${low_price:.2f}"
        return candidate, reasoning


# Registry of all base type strategies
BASE_TYPE_STRATEGIES = {
    "cup_with_handle": CupWithHandleStrategy(),
    "flat_base": FlatBaseStrategy(),
    "vcp": VCPStrategy(),
    "double_bottom": DoubleBottomStrategy(),
    "ascending_base": AscendingBaseStrategy(),
    "saucer": SaucerStrategy(),
}


def get_strategy(base_type: str) -> BaseTypeStrategy | None:
    return BASE_TYPE_STRATEGIES.get(base_type)
