#!/usr/bin/env python3
"""Filter Registry - centralized definition of advanced signal filters.

This module provides a single source of truth for all filter weights, thresholds,
and validation rules used by AdvancedFilters. Instead of hardcoding these values
scattered throughout the class, they are defined here and validated once at startup.

Benefits:
1. Single source of truth for all filter parameters
2. Easy to adjust thresholds without diving into method implementations
3. Clear documentation of filter design rationale
4. Centralized validation of filter definitions
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FilterWeight:
    """A scoring weight for a filter component."""

    name: str
    value: float
    category: str
    description: str

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Weight {self.name} cannot be negative: {self.value}")


@dataclass(frozen=True)
class FilterThreshold:
    """A validation threshold for filter gates."""

    name: str
    value: Any
    value_type: str  # 'int', 'float', 'bool', 'str'
    description: str

    def __post_init__(self) -> None:
        # Validate type
        type_map = {"int": int, "float": float, "bool": bool, "str": str}
        if self.value_type not in type_map:
            raise ValueError(f"Invalid type for threshold {self.name}: {self.value_type}")


class FilterRegistry:
    """Registry of all filter weights and thresholds for signal scoring."""

    # ============= MOMENTUM WEIGHTS (sum component = 40) =============
    WEIGHTS = {
        # Momentum category (total: 40)
        "momentum_rs": FilterWeight(
            name="momentum_rs",
            value=15,  # Mansfield RS vs SPY
            category="Momentum",
            description="Mansfield relative strength percentile vs SPY",
        ),
        "momentum_sector": FilterWeight(
            name="momentum_sector",
            value=10,
            category="Momentum",
            description="Sector momentum rank within top N strong sectors",
        ),
        "momentum_industry": FilterWeight(
            name="momentum_industry",
            value=5,
            category="Momentum",
            description="Industry momentum (top quartile only)",
        ),
        "momentum_volume": FilterWeight(
            name="momentum_volume",
            value=5,
            category="Momentum",
            description="Volume confirmation (ratio vs 50-day average)",
        ),
        "momentum_price_trend": FilterWeight(
            name="momentum_price_trend",
            value=5,
            category="Momentum",
            description="Price trend alignment (Elder Triple Screen)",
        ),
        # Quality category (total: 30)
        "quality_ibd": FilterWeight(
            name="quality_ibd",
            value=15,
            category="Quality",
            description="IBD composite score (40-90 range)",
        ),
        "quality_financial": FilterWeight(
            name="quality_financial",
            value=8,
            category="Quality",
            description="Financial quality score (fundamentals)",
        ),
        "quality_earnings": FilterWeight(
            name="quality_earnings",
            value=7,
            category="Quality",
            description="Earnings quality score (surprise/beat history)",
        ),
        # Catalyst category (total: 15)
        "catalyst_growth": FilterWeight(
            name="catalyst_growth",
            value=7,
            category="Catalyst",
            description="Growth metrics (3-year CAGR + momentum)",
        ),
        "catalyst_analyst": FilterWeight(
            name="catalyst_analyst",
            value=5,
            category="Catalyst",
            description="Analyst upgrades net of downgrades (90-day window)",
        ),
        "catalyst_insider": FilterWeight(
            name="catalyst_insider",
            value=3,
            category="Catalyst",
            description="Insider buying net of selling (60-day window)",
        ),
        # Risk category (total: 15) — lower is BETTER for risk
        "risk_extension": FilterWeight(
            name="risk_extension",
            value=13,
            category="Risk",
            description="Extension above 50-day SMA (negative = extra risk)",
        ),
        "risk_earnings_proximity": FilterWeight(
            name="risk_earnings_proximity",
            value=2,
            category="Risk",
            description="Proximity to earnings announcement",
        ),
    }

    # ============= THRESHOLDS (config-driven validation gates) =============
    THRESHOLDS = {
        # Hard-fail gates
        "block_days_before_earnings": FilterThreshold(
            name="block_days_before_earnings",
            value=5,
            value_type="int",
            description="Days before earnings to block entry",
        ),
        "max_extension_above_50ma_pct": FilterThreshold(
            name="max_extension_above_50ma_pct",
            value=15.0,
            value_type="float",
            description="Maximum entry extension above 50-day SMA (%)",
        ),
        "min_avg_daily_dollar_volume": FilterThreshold(
            name="min_avg_daily_dollar_volume",
            value=500_000.0,
            value_type="float",
            description="Minimum average daily dollar volume (50-day average)",
        ),
        "strong_sector_top_n": FilterThreshold(
            name="strong_sector_top_n",
            value=5,
            value_type="int",
            description="Number of sectors to classify as 'strong'",
        ),
        "require_strong_sector": FilterThreshold(
            name="require_strong_sector",
            value=False,
            value_type="bool",
            description="Whether entry sector must be in top N strong sectors",
        ),
        # Scoring sub-thresholds (for compute, not hard-fail)
        "volume_ratio_breakeven": FilterThreshold(
            name="volume_ratio_breakeven",
            value=0.8,
            value_type="float",
            description="Volume ratio below which score starts at 0",
        ),
        "volume_ratio_full_points": FilterThreshold(
            name="volume_ratio_full_points",
            value=1.5,
            value_type="float",
            description="Volume ratio at which score reaches maximum points",
        ),
        "ibd_composite_min": FilterThreshold(
            name="ibd_composite_min",
            value=40.0,
            value_type="float",
            description="IBD composite score floor (0 pts below this)",
        ),
        "ibd_composite_max": FilterThreshold(
            name="ibd_composite_max",
            value=90.0,
            value_type="float",
            description="IBD composite score ceiling (full pts at this)",
        ),
        "financial_quality_neutral": FilterThreshold(
            name="financial_quality_neutral",
            value=50.0,
            value_type="float",
            description="Financial quality score = neutral (0 pts)",
        ),
        "financial_quality_max": FilterThreshold(
            name="financial_quality_max",
            value=100.0,
            value_type="float",
            description="Financial quality score = full pts",
        ),
        "eps_3y_cagr_threshold": FilterThreshold(
            name="eps_3y_cagr_threshold",
            value=20.0,
            value_type="float",
            description="EPS 3-year CAGR threshold for growth score (% per year)",
        ),
        "revenue_3y_cagr_threshold": FilterThreshold(
            name="revenue_3y_cagr_threshold",
            value=15.0,
            value_type="float",
            description="Revenue 3-year CAGR threshold for growth score (% per year)",
        ),
        "analyst_net_positive_threshold": FilterThreshold(
            name="analyst_net_positive_threshold",
            value=-3,
            value_type="int",
            description="Analyst net actions: score goes from 0 to max at this spread",
        ),
        "analyst_net_full_score": FilterThreshold(
            name="analyst_net_full_score",
            value=5,
            value_type="int",
            description="Analyst net actions: score capped at this positive value",
        ),
        "insider_buy_sell_threshold": FilterThreshold(
            name="insider_buy_sell_threshold",
            value=500_000.0,
            value_type="float",
            description="Insider transaction value threshold (net buys > 0, capped at $500k)",
        ),
        "extension_risk_sweet_spot_pct": FilterThreshold(
            name="extension_risk_sweet_spot_pct",
            value=5.0,
            value_type="float",
            description="Extension above SMA_50 = sweet spot (0-5%)",
        ),
        "extension_risk_moderate_pct": FilterThreshold(
            name="extension_risk_moderate_pct",
            value=10.0,
            value_type="float",
            description="Extension above SMA_50 = moderate risk (5-10%)",
        ),
        "extension_risk_high_pct": FilterThreshold(
            name="extension_risk_high_pct",
            value=15.0,
            value_type="float",
            description="Extension above SMA_50 = high risk (10-15%)",
        ),
        "earnings_proximity_safe_days": FilterThreshold(
            name="earnings_proximity_safe_days",
            value=30,
            value_type="int",
            description="Days to earnings = full risk score (≥30d = safe)",
        ),
    }

    # ============= SUBSCORES (components of composite score) =============
    SUBSCORE_CAPS = {
        "momentum": 40.0,  # Maximum points from all momentum filters
        "quality": 30.0,  # Maximum points from all quality filters
        "catalyst": 15.0,  # Maximum points from all catalyst filters
        "risk": 15.0,  # Maximum points from all risk filters
    }

    @classmethod
    def validate(cls) -> None:
        """Validate that weights and thresholds sum correctly.

        Raises:
            ValueError: If weights don't sum to 100 or any config is invalid
        """
        # Validate weight totals by category
        momentum_total = sum(w.value for w in cls.WEIGHTS.values() if w.category == "Momentum")
        quality_total = sum(w.value for w in cls.WEIGHTS.values() if w.category == "Quality")
        catalyst_total = sum(w.value for w in cls.WEIGHTS.values() if w.category == "Catalyst")
        risk_total = sum(w.value for w in cls.WEIGHTS.values() if w.category == "Risk")

        if momentum_total != cls.SUBSCORE_CAPS["momentum"]:
            raise ValueError(f"Momentum weights sum to {momentum_total}, expected {cls.SUBSCORE_CAPS['momentum']}")
        if quality_total != cls.SUBSCORE_CAPS["quality"]:
            raise ValueError(f"Quality weights sum to {quality_total}, expected {cls.SUBSCORE_CAPS['quality']}")
        if catalyst_total != cls.SUBSCORE_CAPS["catalyst"]:
            raise ValueError(f"Catalyst weights sum to {catalyst_total}, expected {cls.SUBSCORE_CAPS['catalyst']}")
        if risk_total != cls.SUBSCORE_CAPS["risk"]:
            raise ValueError(f"Risk weights sum to {risk_total}, expected {cls.SUBSCORE_CAPS['risk']}")

        # Validate that subscore caps sum to 100
        total = sum(cls.SUBSCORE_CAPS.values())
        if total != 100.0:
            raise ValueError(f"Subscore caps sum to {total}, expected 100.0")

    @classmethod
    def get_weight(cls, name: str) -> float:
        """Get a weight value by name.

        Raises:
            KeyError: If weight not found
        """
        return cls.WEIGHTS[name].value

    @classmethod
    def get_threshold(cls, name: str) -> Any:
        """Get a threshold value by name.

        Raises:
            KeyError: If threshold not found
        """
        return cls.THRESHOLDS[name].value

    @classmethod
    def get_subscore_cap(cls, category: str) -> float:
        """Get the maximum score for a subscore category.

        Raises:
            KeyError: If category not found
        """
        return cls.SUBSCORE_CAPS[category]


# Validate at module load time (fail-fast on config errors)
FilterRegistry.validate()
