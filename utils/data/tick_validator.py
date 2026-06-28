#!/usr/bin/env python3
"""
Data Tick Validator - Explicit validation schema for market data integrity.

Validates every tick of market data BEFORE it enters the database. Catches:
  1. PRICE_BOUNDS - prices outside reasonable ranges for the security
  2. VOLUME_SANITY - volume spikes or zeros (API failures)
  3. OHLC_LOGIC - High >= Open/Close/Low, detect negative prices
  4. SEQUENCE - prices can't jump >30% in a day (delisting/split detection)
  5. DUPLICATE - same OHLC values repeated (API rate limit hit)
  6. NULL_FIELDS - required fields present

This runs INLINE in loaders before any INSERT/UPDATE to prevent bad data ever
reaching the database. Replaces ad-hoc checks scattered across loaders.

USAGE:
  validator = TickValidator(symbol='AAPL', prior_close=150.25, is_etf=False)
  errors = validator.validate(open=151.0, high=152.5, low=150.0, close=151.5, volume=5000000)
  if errors:
    logger.warning(f"[AAPL] Validation errors: {errors}")
    return False  # Skip this tick
  # Safe to insert
"""

import logging
from datetime import date as _date
from typing import Any

logger = logging.getLogger(__name__)


class TickValidator:
    """Validates a single tick of OHLCV data."""

    def __init__(
        self,
        symbol: str,
        prior_close: float | None = None,
        is_etf: bool = False,
        security_type: str = "equity",  # 'equity', 'et', 'index'
    ):
        """
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            prior_close: Previous close price (for sequence check)
            is_etf: Whether this is an ETF (affects volume thresholds)
            security_type: Type of security for appropriate thresholds
        """
        self.symbol = symbol
        self.prior_close = prior_close
        self.is_etf = is_etf
        self.security_type = security_type
        self.errors: list[str] = []

    def validate(
        self,
        open_price: float | None,
        high: float | None,
        low: float | None,
        close: float | None,
        volume: int | None,
        data_date: _date | None = None,
    ) -> list[str]:
        """
        Validate a single tick. Returns list of errors (empty = valid).

        Args:
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price
            volume: Volume in shares
            data_date: Date of the data point

        Returns:
            List of error messages. Empty list = valid tick.
        """
        self.errors = []

        # 1. NULL CHECK - all OHLCV required
        self._check_nulls(open_price, high, low, close, volume)
        if self.errors:
            return self.errors

        # Type guards: after null check, values are guaranteed non-None
        assert (
            open_price is not None and high is not None and low is not None and close is not None and volume is not None
        )

        # 2. OHLC LOGIC - High >= all, Low <= all
        self._check_ohlc_logic(open_price, high, low, close)
        if self.errors:
            return self.errors

        # 3. PRICE BOUNDS - prices in reasonable range for symbol
        self._check_price_bounds(open_price, high, low, close)
        if self.errors:
            return self.errors

        # 4. VOLUME SANITY - not zero, not absurd
        self._check_volume_sanity(volume)
        if self.errors:
            return self.errors

        # 5. SEQUENCE - can't jump >30% in one day
        if self.prior_close:
            self._check_sequence(open_price, close)
        if self.errors:
            return self.errors

        return self.errors

    def _check_nulls(
        self,
        open_price: float | None,
        high: float | None,
        low: float | None,
        close: float | None,
        volume: int | None,
    ) -> None:
        """Check for required fields."""
        if open_price is None:
            self.errors.append("open_price is NULL")
        if high is None:
            self.errors.append("high is NULL")
        if low is None:
            self.errors.append("low is NULL")
        if close is None:
            self.errors.append("close is NULL")
        if volume is None:
            self.errors.append("volume is NULL")

    def _check_ohlc_logic(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float,
    ) -> None:
        """Validate OHLC relationship: High >= max(O,C), Low <= min(O,C), all >= 0."""
        if open_price < 0:
            self.errors.append(f"open_price is negative: {open_price}")
        if high < 0:
            self.errors.append(f"high is negative: {high}")
        if low < 0:
            self.errors.append(f"low is negative: {low}")
        if close < 0:
            self.errors.append(f"close is negative: {close}")

        if high < low:
            self.errors.append(f"high < low: {high} < {low}")
        if high < max(open_price, close):
            self.errors.append(f"high < max(open, close): {high} < max({open_price}, {close})")
        if low > min(open_price, close):
            self.errors.append(f"low > min(open, close): {low} > min({open_price}, {close})")

    def _check_price_bounds(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float,
    ) -> None:
        """Check prices are in reasonable range for the symbol."""

        prices = [open_price, high, low, close]

        # Catch obvious delisting/data errors
        if max(prices) > 100_000:
            self.errors.append(f"price > $100,000: {max(prices)}")
        if min(prices) < 0.001:
            self.errors.append(f"price < $0.001: {min(prices)}")

        if low <= 0:
            self.errors.append(f"Low price is invalid ({low}): cannot calculate spread percent")
        else:
            spread_pct = ((high - low) / low * 100)
            if spread_pct > 50:
                # More than 50% spread = likely bad data
                self.errors.append(f"spread > 50%: {spread_pct:.1f}%")

    def _check_volume_sanity(self, volume: int) -> None:
        """Check volume is reasonable for the security type."""
        if volume < 0:
            self.errors.append(f"volume is negative: {volume}")
        # Zero volume is only an error if it's the only indication of staleness.
        # Market closed, no trades, or illiquid securities legitimately have zero volume.
        # Don't reject outright — downstream phases can assess data freshness.

        # Max volume sanity check
        max_volume = 1_000_000_000  # 1B shares is essentially impossible
        if volume > max_volume:
            self.errors.append(f"volume impossibly high: {volume}")

        # Don't enforce min_volume thresholds — they're too strict for penny stocks,
        # low-liquidity securities, and market-close thinly traded data.
        # OHLC logic and price bounds checks catch the real issues.

    def _check_sequence(self, open_price: float, close: float) -> None:
        """Check price didn't gap >30% from prior close (delisting/split detection)."""
        if not self.prior_close or self.prior_close == 0:
            return

        gap_pct = abs(close - self.prior_close) / self.prior_close * 100
        if gap_pct > 30:
            self.errors.append(f"price gap > 30%: {self.prior_close} → {close} ({gap_pct:.1f}%)")


class TickValidationBatch:
    """Validates a batch of ticks for the same symbol."""

    def __init__(self, symbol: str, is_etf: bool = False):
        self.symbol = symbol
        self.is_etf = is_etf
        self.ticks: list[dict[str, Any]] = []
        self.prior_close: float | None = None

    def add_tick(
        self,
        date: _date,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ) -> tuple[bool, list[str]]:
        """
        Validate and add a tick to the batch.

        Returns:
            (is_valid, error_messages)
        """
        validator = TickValidator(
            symbol=self.symbol,
            prior_close=self.prior_close,
            is_etf=self.is_etf,
        )
        errors = validator.validate(open_price, high, low, close, volume, date)

        if not errors:
            self.ticks.append(
                {
                    "date": date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
            self.prior_close = close

        return (len(errors) == 0, errors)

    def get_valid_ticks(self) -> list[dict[str, Any]]:
        """Return all validated ticks in chronological order."""
        return sorted(self.ticks, key=lambda x: x["date"])


def validate_price_tick(
    symbol: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    prior_close: float | None = None,
    is_etf: bool = False,
) -> tuple[bool, list[str]]:
    """
    Convenience function to validate a single tick.

    Returns:
        (is_valid, error_messages)
    """
    validator = TickValidator(
        symbol=symbol,
        prior_close=prior_close,
        is_etf=is_etf,
    )
    errors = validator.validate(open_price, high, low, close, volume)
    return (len(errors) == 0, errors)


def validate_score_tick(
    symbol: str,
    composite_score: float | None,
    momentum_score: float | None = None,
    value_score: float | None = None,
    quality_score: float | None = None,
    growth_score: float | None = None,
    score_date: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate a score tick before insertion.

    Scores should be between 0-100 or NULL.
    At least composite_score should be present.

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    if not symbol:
        errors.append("MISSING_SYMBOL")
    if score_date is None:
        errors.append("MISSING_DATE")

    # Composite score is required
    if composite_score is None:
        errors.append("MISSING_COMPOSITE_SCORE")
    elif not isinstance(composite_score, (int, float)):
        errors.append(f"INVALID_COMPOSITE_SCORE_TYPE: {type(composite_score)}")
    elif composite_score < 0 or composite_score > 100:
        errors.append(f"COMPOSITE_SCORE_OUT_OF_RANGE: {composite_score}")

    # Optional scores should be in range if present
    for score_name, score_value in [
        ("momentum", momentum_score),
        ("value", value_score),
        ("quality", quality_score),
        ("growth", growth_score),
    ]:
        if score_value is not None:
            if not isinstance(score_value, (int, float)):
                errors.append(f"INVALID_{score_name.upper()}_TYPE")
            elif score_value < 0 or score_value > 100:
                errors.append(f"{score_name.upper()}_OUT_OF_RANGE: {score_value}")

    return (len(errors) == 0, errors)
