#!/usr/bin/env python3
"""Trade context consolidates all trade-related data into a single object.

Eliminates parameter explosion (22+ params) by grouping related fields.
Used throughout trade execution (entry, exit, sizing, validation, monitoring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class PriceContext:
    """Price levels and execution details for a trade."""

    entry_price: Decimal
    stop_loss_price: Decimal
    target_1_price: Decimal | None = None
    target_2_price: Decimal | None = None
    target_3_price: Decimal | None = None


@dataclass
class SignalContext:
    """All signal components and quality metrics."""

    trend_score: float | None = None
    base_type: str | None = None
    base_quality: str | None = None
    stage_phase: str | None = None
    rs_percentile: float | None = None
    advanced_components: dict[str, Any] | None = None


@dataclass
class MarketContext:
    """Market conditions at time of entry."""

    sector: str | None = None
    industry: str | None = None
    market_exposure_at_entry: float | None = None
    exposure_tier_at_entry: str | None = None


@dataclass
class ExecutionContext:
    """Execution parameters and configuration."""

    execution_mode: str = "auto"
    stop_method: str | None = None
    stop_reasoning: str | None = None


@dataclass
class TradeContext:
    """Complete trade execution context.

    Consolidates all trade-related data into a single object to replace
    parameter explosion in executor_entry_handler.execute_entry() and similar methods.

    Example:
        context = TradeContext(
            symbol="AAPL",
            shares=Decimal("100"),
            prices=PriceContext(...),
            signals=SignalContext(...),
            market=MarketContext(...),
            execution=ExecutionContext(),
            signal_date=date.today(),
        )
    """

    symbol: str
    shares: Decimal
    prices: PriceContext
    signals: SignalContext = field(default_factory=SignalContext)
    market: MarketContext = field(default_factory=MarketContext)
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    signal_date: date | None = None
    entry_date: date | None = None
    sqs: Any | None = None

    def __post_init__(self) -> None:
        """Normalize Decimal shares; normalize dates."""
        if not isinstance(self.shares, Decimal):
            self.shares = Decimal(str(self.shares))

        if self.signal_date is None:
            from datetime import datetime, timezone

            self.signal_date = datetime.now(timezone.utc).date()

        if self.entry_date is None:
            from datetime import datetime, timezone

            self.entry_date = datetime.now(timezone.utc).date()

    @classmethod
    def from_params(
        cls,
        symbol: str,
        entry_price: Decimal | float,
        shares: Decimal | float,
        stop_loss_price: Decimal | float,
        target_1_price: Decimal | float | None = None,
        target_2_price: Decimal | float | None = None,
        target_3_price: Decimal | float | None = None,
        signal_date: Any = None,
        entry_date: Any = None,
        sqs: Any | None = None,
        trend_score: float | None = None,
        base_type: str | None = None,
        base_quality: str | None = None,
        stage_phase: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        rs_percentile: float | None = None,
        market_exposure_at_entry: float | None = None,
        exposure_tier_at_entry: str | None = None,
        stop_method: str | None = None,
        stop_reasoning: str | None = None,
        advanced_components: dict[str, Any] | None = None,
        execution_mode: str = "auto",
        # DEPRECATED params (kept for backward compatibility, ignored)
        swing_score: float | None = None,
        swing_grade: str | None = None,
        swing_components: dict[str, Any] | None = None,
    ) -> TradeContext:
        """Factory method: construct from flat parameter list (for backward compatibility).

        SWING SCORE MIGRATION: swing_score, swing_grade, swing_components params deprecated.
        Kept for backward compatibility with old code but are no longer used.
        """
        prices = PriceContext(
            entry_price=Decimal(str(entry_price)),
            stop_loss_price=Decimal(str(stop_loss_price)),
            target_1_price=(Decimal(str(target_1_price)) if target_1_price is not None else None),
            target_2_price=(Decimal(str(target_2_price)) if target_2_price is not None else None),
            target_3_price=(Decimal(str(target_3_price)) if target_3_price is not None else None),
        )

        signals = SignalContext(
            trend_score=trend_score,
            base_type=base_type,
            base_quality=base_quality,
            stage_phase=stage_phase,
            rs_percentile=rs_percentile,
            advanced_components=advanced_components,
        )

        market = MarketContext(
            sector=sector,
            industry=industry,
            market_exposure_at_entry=market_exposure_at_entry,
            exposure_tier_at_entry=exposure_tier_at_entry,
        )

        execution = ExecutionContext(
            execution_mode=execution_mode,
            stop_method=stop_method,
            stop_reasoning=stop_reasoning,
        )

        return cls(
            symbol=symbol,
            shares=Decimal(str(shares)),
            prices=prices,
            signals=signals,
            market=market,
            execution=execution,
            signal_date=signal_date,
            entry_date=entry_date,
            sqs=sqs,
        )
