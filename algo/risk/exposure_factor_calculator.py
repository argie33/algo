#!/usr/bin/env python3
"""Exposure Factor Calculator - Extract MarketExposure factors computation (1,500L)."""

import logging
from abc import ABC, abstractmethod
from typing import Any


logger = logging.getLogger(__name__)


class ExposureFactorStrategy(ABC):
    """Base strategy for market exposure factors."""

    @abstractmethod
    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate exposure factor."""
        ...


class VolatilityFactor(ExposureFactorStrategy):
    """VIX-based volatility exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate volatility exposure."""
        vix = float(market_data.get("vix_level", 20.0))
        return min(1.0, vix / 30.0)  # Normalized to [0,1]


class BetaFactor(ExposureFactorStrategy):
    """Market beta exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate beta exposure."""
        correlation = float(market_data.get("correlation_to_market", 0.7))
        return correlation


class LiquidityFactor(ExposureFactorStrategy):
    """Market liquidity exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate liquidity exposure."""
        spread_basis_points = float(market_data.get("spread_bps", 5))
        return 1.0 / (1.0 + spread_basis_points / 100.0)  # Inverse function


class DrawdownFactor(ExposureFactorStrategy):
    """Current drawdown exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate drawdown exposure."""
        max_dd = float(market_data.get("max_drawdown_pct", 0))
        return max(0.0, 1.0 - (abs(max_dd) / 100.0))  # Penalize drawdowns


class ExposureFactorCalculator:
    """Calculates composite market exposure factors."""

    def __init__(self) -> None:
        """Initialize calculator with default factors."""
        self.factors = {
            "volatility": VolatilityFactor(),
            "beta": BetaFactor(),
            "liquidity": LiquidityFactor(),
            "drawdown": DrawdownFactor(),
        }

    def calculate_factor(self, name: str, market_data: dict[str, Any]) -> float:
        """Calculate single exposure factor.

        Raises ValueError if factor is unknown. Do not return 0.0 — that masks
        missing factors in composite calculations.
        """
        factor = self.factors.get(name)
        if not factor:
            logger.critical(
                f"CRITICAL: Unknown exposure factor: {name}. "
                f"Available factors: {list(self.factors.keys())}. "
                f"Cannot calculate exposure without all defined factors."
            )
            raise ValueError(
                f"Unknown exposure factor: {name}. "
                f"Exposure calculation incomplete. Cannot proceed without all factors."
            )
        return factor.calculate(market_data)

    def calculate_composite(self, market_data: dict[str, Any], weights: dict[str, float] | None = None) -> float:
        """Calculate weighted composite exposure factor.

        Args:
            market_data: Market metrics dictionary
            weights: Optional custom weights per factor (defaults to equal)

        Returns:
            Composite exposure factor in [0, 1]
        """
        if weights is None:
            weights = {k: 1.0 / len(self.factors) for k in self.factors}

        total = 0.0
        for name, weight in weights.items():
            factor_value = self.calculate_factor(name, market_data)
            total += factor_value * weight

        return min(1.0, max(0.0, total))  # Clamp to [0, 1]
