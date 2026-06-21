#!/usr/bin/env python3
"""Data contexts for trade and position operations.

These dataclasses replace scattered parameters and improve code clarity
by grouping related fields into cohesive contexts.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


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
    swing_components: dict | None = None
    advanced_components: dict | None = None

    def __post_init__(self):
        """Convert prices to Decimal for consistency."""
        if not isinstance(self.entry_price, Decimal):
            self.entry_price = Decimal(str(self.entry_price))
        if not isinstance(self.shares, Decimal):
            self.shares = Decimal(str(self.shares))
        if not isinstance(self.stop_loss_price, Decimal):
            self.stop_loss_price = Decimal(str(self.stop_loss_price))

        # Convert target prices to Decimal if present
        if self.target_1_price is not None and not isinstance(self.target_1_price, Decimal):
            self.target_1_price = Decimal(str(self.target_1_price))
        if self.target_2_price is not None and not isinstance(self.target_2_price, Decimal):
            self.target_2_price = Decimal(str(self.target_2_price))
        if self.target_3_price is not None and not isinstance(self.target_3_price, Decimal):
            self.target_3_price = Decimal(str(self.target_3_price))


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

    def __post_init__(self):
        """Convert prices to Decimal."""
        if not isinstance(self.current_price, Decimal):
            self.current_price = Decimal(str(self.current_price))
        if not isinstance(self.entry_price, Decimal):
            self.entry_price = Decimal(str(self.entry_price))
        if not isinstance(self.active_stop, Decimal):
            self.active_stop = Decimal(str(self.active_stop))
        if not isinstance(self.init_stop, Decimal):
            self.init_stop = Decimal(str(self.init_stop))

        # Convert targets if present
        if self.target_1_price is not None and not isinstance(self.target_1_price, Decimal):
            self.target_1_price = Decimal(str(self.target_1_price))
        if self.target_2_price is not None and not isinstance(self.target_2_price, Decimal):
            self.target_2_price = Decimal(str(self.target_2_price))
        if self.target_3_price is not None and not isinstance(self.target_3_price, Decimal):
            self.target_3_price = Decimal(str(self.target_3_price))
        if self.prev_close is not None and not isinstance(self.prev_close, Decimal):
            self.prev_close = Decimal(str(self.prev_close))
