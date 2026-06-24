#!/usr/bin/env python3
"""Data contexts for trade and position operations.

These dataclasses replace scattered parameters and improve code clarity
by grouping related fields into cohesive contexts.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from algo.trading.helpers import safe_decimal


@dataclass
class TradeContext:
    """Complete context for a trade entry operation.

    Replaces 26 individual parameters in execute_trade(), dramatically improving
    readability and maintainability.
    """

    # CORE TRADE PARAMETERS (required)
    symbol: str
    entry_price: Decimal | float
    shares: Decimal | float
    stop_loss_price: Decimal | float

    # PRICE TARGETS (optional)
    target_1_price: Decimal | float | None = None
    target_2_price: Decimal | float | None = None
    target_3_price: Decimal | float | None = None

    # TIMING (optional, defaults to now)
    signal_date: date | None = None
    entry_date: date | None = None

    # SIGNAL METRICS (optional)
    sqs: Any | None = None
    trend_score: float | None = None
    swing_score: float | None = None
    swing_grade: str | None = None
    base_type: str | None = None
    base_quality: str | None = None
    stage_phase: str | None = None

    # CONTEXT & MARKET (optional)
    sector: str | None = None
    industry: str | None = None
    rs_percentile: float | None = None
    market_exposure_at_entry: float | None = None
    exposure_tier_at_entry: str | None = None

    # STOP REASONING (optional)
    stop_method: str | None = None
    stop_reasoning: str | None = None

    # COMPONENT DATA (optional)
    swing_components: dict[str, Any] | None = None
    advanced_components: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Convert prices to Decimal for consistency.

        Raises:
            RuntimeError: If any required price is missing or cannot be converted.
                 Entry price, shares, and stop loss are required.
        """
        self.entry_price = safe_decimal(self.entry_price)
        self.shares = safe_decimal(self.shares)
        self.stop_loss_price = safe_decimal(self.stop_loss_price)
        if self.target_1_price is not None:
            self.target_1_price = safe_decimal(self.target_1_price, allow_none=False)
        if self.target_2_price is not None:
            self.target_2_price = safe_decimal(self.target_2_price, allow_none=False)
        if self.target_3_price is not None:
            self.target_3_price = safe_decimal(self.target_3_price, allow_none=False)


@dataclass
class PositionContext:
    """Complete context for a position evaluation.

    Replaces 18 individual parameters in _evaluate_position(), eliminating
    parameter bloat and improving argument order flexibility.
    """

    # CORE POSITION STATE
    symbol: str
    current_price: Decimal | float
    entry_price: Decimal | float
    active_stop: Decimal | float
    init_stop: Decimal | float

    # TARGETS & HITS
    target_1_price: Decimal | float | None = None
    target_2_price: Decimal | float | None = None
    target_3_price: Decimal | float | None = None
    target_hits: int = 0

    # TIME & VOLUME
    current_date: date | None = None
    days_held: int = 0
    dist_days_today: int = 0
    prev_close: Decimal | float | None = None

    # HIT TIMING (when each target was hit)
    t1_hit_time: date | None = None
    t2_hit_time: date | None = None
    t3_hit_time: date | None = None

    def __post_init__(self) -> None:
        """Convert prices to Decimal.

        Raises:
            RuntimeError: If any required price is missing or cannot be converted.
                 Current price, entry price, and stops are required.
        """
        self.current_price = safe_decimal(self.current_price)
        self.entry_price = safe_decimal(self.entry_price)
        self.active_stop = safe_decimal(self.active_stop)
        self.init_stop = safe_decimal(self.init_stop)
        if self.target_1_price is not None:
            self.target_1_price = safe_decimal(self.target_1_price, allow_none=False)
        if self.target_2_price is not None:
            self.target_2_price = safe_decimal(self.target_2_price, allow_none=False)
        if self.target_3_price is not None:
            self.target_3_price = safe_decimal(self.target_3_price, allow_none=False)
        if self.prev_close is not None:
            self.prev_close = safe_decimal(self.prev_close, allow_none=False)
