#!/usr/bin/env python3
"""Exposure Factor Calculator - Extract MarketExposure factors computation (1,500L)."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ExposureFactorStrategy(ABC):
    """Base strategy for market exposure factors."""

    @abstractmethod
    def calculate(self, market_data: dict[str, Any]) -> float: ...


class VolatilityFactor(ExposureFactorStrategy):
    """VIX-based volatility exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate volatility exposure.

        Raises ValueError if VIX data is missing - exposure calculations
        require accurate volatility; defaulting to 20 would mask data issues.
        """
        if "vix_level" not in market_data or market_data["vix_level"] is None:
            raise ValueError(
                "CRITICAL: VIX level missing from market data. "
                "Volatility exposure calculation requires live VIX data. "
                "Cannot proceed with default VIX value (would hide market risk)."
            )
        vix = float(market_data["vix_level"])
        return min(1.0, vix / 30.0)  # Normalized to [0,1]


class BetaFactor(ExposureFactorStrategy):
    """Market beta exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate beta exposure.

        Raises ValueError if correlation data is missing - exposure calculations
        require accurate beta; defaulting to 0.7 would mask missing market data.
        """
        if "correlation_to_market" not in market_data or market_data["correlation_to_market"] is None:
            raise ValueError(
                "CRITICAL: Market correlation missing from market data. "
                "Beta exposure calculation requires correlation metrics. "
                "Cannot proceed with default correlation value (would hide market risk)."
            )
        correlation = float(market_data["correlation_to_market"])
        return correlation


class LiquidityFactor(ExposureFactorStrategy):
    """Market liquidity exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate liquidity exposure.

        Raises ValueError if spread data is missing - exposure calculations
        require accurate liquidity metrics; defaulting to 5 bps would mask stale data.
        """
        if "spread_bps" not in market_data or market_data["spread_bps"] is None:
            raise ValueError(
                "CRITICAL: Bid-ask spread data missing from market data. "
                "Liquidity exposure calculation requires current spread metrics. "
                "Cannot proceed with default spread value (would hide liquidity risk)."
            )
        spread_basis_points = float(market_data["spread_bps"])
        return 1.0 / (1.0 + spread_basis_points / 100.0)  # Inverse function


class DrawdownFactor(ExposureFactorStrategy):
    """Current drawdown exposure factor."""

    def calculate(self, market_data: dict[str, Any]) -> float:
        """Calculate drawdown exposure.

        Raises ValueError if drawdown data is missing - exposure calculations
        require accurate risk metrics; defaulting to 0% would hide portfolio losses.
        """
        if "max_drawdown_pct" not in market_data or market_data["max_drawdown_pct"] is None:
            raise ValueError(
                "CRITICAL: Portfolio drawdown data missing from market data. "
                "Drawdown exposure calculation requires drawdown metrics. "
                "Cannot proceed with default value (would hide portfolio losses)."
            )
        max_dd = float(market_data["max_drawdown_pct"])
        return max(0.0, 1.0 - (abs(max_dd) / 100.0))  # Penalize drawdowns


class ExposureFactorCalculator:
    def __init__(self) -> None:
        self.factors = {
            "volatility": VolatilityFactor(),
            "beta": BetaFactor(),
            "liquidity": LiquidityFactor(),
            "drawdown": DrawdownFactor(),
        }

    def calculate_factor(self, name: str, market_data: dict[str, Any]) -> float:
        """Calculate single exposure factor.

        Raises ValueError if factor is unknown. Do not return 0.0 - that masks
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
                f"Unknown exposure factor: {name}. Exposure calculation incomplete. Cannot proceed without all factors."
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
