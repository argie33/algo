#!/usr/bin/env python3
"""PriceTransformer specialist - handles data transformation and normalization.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Transform and normalize raw price data from yfinance.
"""

import logging
from datetime import date, datetime
from typing import Any


logger = logging.getLogger(__name__)


class PriceTransformer:
    """Specialist for transforming price data.

    Handles:
    - Raw data normalization
    - Data type conversions
    - Field mapping and renaming
    - Trading day filtering
    - Timezone handling
    """

    def __init__(self, asset_class: str = "stock"):
        """Initialize PriceTransformer."""
        self.timezone = None
        self.asset_class = asset_class

    def transform_row(self, row: dict, symbol: str, date_val: Any) -> dict | None:
        """Transform raw yfinance row to canonical format.

        Args:
            row: Raw price data from yfinance
            symbol: Stock symbol
            date_val: Date for the price point

        Returns:
            Transformed row or None if transformation fails
        """
        try:
            transformed = {
                "symbol": symbol,
                "date": date_val,
                "open": self._normalize_numeric(row.get("Open")),
                "high": self._normalize_numeric(row.get("High")),
                "low": self._normalize_numeric(row.get("Low")),
                "close": self._normalize_numeric(row.get("Close")),
                "volume": self._normalize_volume(row.get("Volume")),
                "adj_close": self._normalize_numeric(row.get("Adj Close")),
            }
            return transformed
        except Exception as e:
            logger.warning(f"Failed to transform row for {symbol}: {e}")
            return None

    def _normalize_numeric(self, value: Any) -> float | None:
        """Normalize numeric value."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _normalize_volume(self, value: Any) -> int | None:
        """Normalize volume value."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def transform_batch(self, rows: list[dict], symbol: str) -> list[dict]:
        """Transform a batch of price rows.

        Args:
            rows: List of raw price data
            symbol: Stock symbol

        Returns:
            List of transformed rows
        """
        transformed = []
        for row in rows:
            # Extract date from row or index
            if hasattr(row, "name"):
                date_val = row.name
            elif "date" in row:
                date_val = row["date"]
            elif "Date" in row:
                date_val = row["Date"]
            else:
                logger.warning(f"Could not extract date from row for {symbol}")
                continue

            transformed_row = self.transform_row(row, symbol, date_val)
            if transformed_row:
                transformed.append(transformed_row)

        return transformed

    def set_timezone(self, tz: str) -> None:
        """Set timezone for date handling."""
        self.timezone = tz

    def validate_and_transform(self, rows: list[dict], tracker=None) -> list[dict]:
        """Validate and filter rows with trading day filtering and provenance tracking.

        Args:
            rows: Raw price data rows
            tracker: Optional DataProvenanceTracker for recording errors
        """
        if not rows:
            return []

        from algo.infrastructure import MarketCalendar
        from utils.data.tick_validator import validate_price_tick

        # CLUSTER 4 FIX: Batch-precompute all trading days in date range for O(1) lookup
        min_row_date = None
        max_row_date = None
        try:
            for row in rows:
                row_date_str = row.get("date")
                if row_date_str:
                    row_date = datetime.fromisoformat(row_date_str).date()
                    if min_row_date is None or row_date < min_row_date:
                        min_row_date = row_date
                    if max_row_date is None or row_date > max_row_date:
                        max_row_date = row_date
        except Exception as e:
            logger.warning(f"Could not determine trading day range from rows: {e}. Falling back to per-row checks.")
            min_row_date = None
            max_row_date = None

        # Precompute trading day set if we have a valid date range
        trading_day_set = None
        if min_row_date and max_row_date:
            try:
                trading_day_set = MarketCalendar.create_trading_day_set(min_row_date, max_row_date)
                logger.debug(
                    f"[CLUSTER_4_OPT] Precomputed {len(trading_day_set)} trading days in range [{min_row_date}, {max_row_date}]"
                )
            except Exception as e:
                logger.warning(f"Could not precompute trading days: {e}. Falling back to per-row checks.")
                trading_day_set = None

        # PHASE 1: Validation via tick validator for provenance tracking
        final_validated = []
        prior_close_by_symbol = {}
        non_trading_filtered = 0
        parse_errors = 0

        for row in rows:
            # CRITICAL: Filter out weekend/holiday data before any other validation
            row_date_str = row.get("date")
            symbol = row.get("symbol")
            try:
                row_date = datetime.fromisoformat(row_date_str).date()
                # CLUSTER 4 FIX: Use precomputed trading day set for O(1) lookup
                if trading_day_set is not None:
                    is_trading_day = row_date in trading_day_set
                else:
                    is_trading_day = MarketCalendar.is_trading_day(row_date)

                if not is_trading_day:
                    if tracker:
                        try:
                            tracker.record_error(
                                symbol=symbol,
                                error_type="NON_TRADING_DAY",
                                error_message="Data for non-trading day (weekend/holiday)",
                                resolution="rejected",
                            )
                        except Exception as e:
                            logger.warning(f"Could not record error for {symbol}: {e}")
                    non_trading_filtered += 1
                    logger.debug(f"[{symbol}] {row_date}: Non-trading day, rejecting")
                    continue
            except (ValueError, TypeError) as e:
                parse_errors += 1
                logger.warning(f"[{symbol}] Could not parse date {row_date_str}: {e}")
                continue

            # Validate price tick
            symbol_prior_close = prior_close_by_symbol.get(symbol)
            is_valid, errors = validate_price_tick(
                symbol=symbol,
                open_price=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("close"),
                volume=row.get("volume"),
                prior_close=symbol_prior_close,
                is_etf=(self.asset_class == "etf"),
            )

            if not is_valid:
                if tracker:
                    try:
                        tracker.record_error(
                            symbol=symbol,
                            error_type="DATA_INVALID",
                            error_message=", ".join(errors),
                            resolution="skipped",
                        )
                    except Exception as e:
                        logger.warning(f"Could not record error for {symbol}: {e}")
                logger.warning(f"[{symbol}] {row.get('date')}: {errors[0]}")
                continue

            # Track provenance for each valid tick
            if tracker:
                tracker.record_tick(
                    symbol=symbol,
                    tick_date=row.get("date"),
                    data=row,
                    source_api="yfinance",
                )

            final_validated.append(row)
            prior_close_by_symbol[symbol] = row.get("close")

        # Log data quality summary
        if non_trading_filtered > 0 or parse_errors > 0:
            total_input = len(rows)
            filtered_pct = (non_trading_filtered + parse_errors) / total_input * 100 if total_input > 0 else 0
            if rows:
                symbol = rows[0].get("symbol", "unknown")
                if filtered_pct > 5:
                    logger.warning(
                        f"[{symbol}] High rejection rate: {non_trading_filtered} non-trading-day + {parse_errors} parse errors "
                        f"out of {total_input} rows ({filtered_pct:.1f}%). This may indicate bad data or API issues."
                    )
                else:
                    logger.info(
                        f"[{symbol}] Filtered {non_trading_filtered} non-trading-day + {parse_errors} parse errors "
                        f"from {total_input} rows ({filtered_pct:.1f}%)"
                    )

        return final_validated
