#!/usr/bin/env python3
"""PriceTransformer specialist - handles data transformation and normalization.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Transform and normalize raw price data from yfinance.
"""

import logging
from datetime import datetime
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
        self.timezone: str | None = None
        self.asset_class = asset_class

    def transform_row(self, row: dict[str, Any], symbol: str, date_val: Any) -> dict[str, Any]:
        """Transform raw yfinance row to canonical format. FAIL-FAST on data corruption.

        Args:
            row: Raw price data from yfinance
            symbol: Stock symbol
            date_val: Date for the price point

        Returns:
            Transformed row with all required OHLCV fields populated

        Raises:
            ValueError: If any OHLCV field is invalid or missing (fail-fast for data integrity)
        """
        try:
            open_price = self._normalize_numeric(row.get("Open"))
            high_price = self._normalize_numeric(row.get("High"))
            low_price = self._normalize_numeric(row.get("Low"))
            close_price = self._normalize_numeric(row.get("Close"))
            volume = self._normalize_volume(row.get("Volume"))
            adj_close = self._normalize_numeric(row.get("Adj Close"))

            transformed = {
                "symbol": symbol,
                "date": date_val,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
                "adj_close": adj_close,
            }
            return transformed
        except ValueError as e:
            raise ValueError(
                f"Price data transformation failed for {symbol} on {date_val}: {e}. "
                f"Cannot proceed with corrupted OHLCV data."
            ) from e

    def _normalize_numeric(self, value: Any) -> float:
        """Normalize numeric value. FAIL-FAST on invalid data.

        Raises ValueError if value cannot be converted to float (except None inputs).
        Returns float on success.
        """
        if value is None:
            raise ValueError("Price field is None - cannot be null in OHLCV data")
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Cannot convert price '{value}' ({type(value).__name__}) to float: {e}. "
                f"OHLCV data corruption detected."
            ) from e

    def _normalize_volume(self, value: Any) -> int:
        """Normalize volume value. FAIL-FAST on invalid data.

        Raises ValueError if value cannot be converted to int (except None inputs).
        Returns int on success.
        """
        if value is None:
            raise ValueError("Volume field is None - cannot be null in OHLCV data")
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Cannot convert volume '{value}' ({type(value).__name__}) to int: {e}. "
                f"OHLCV data corruption detected."
            ) from e

    def transform_batch(self, rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
        """Transform a batch of price rows.

        Args:
            rows: List of raw price data
            symbol: Stock symbol

        Returns:
            List of transformed rows

        Raises:
            ValueError: If any row transformation fails (fail-fast for data integrity)
        """
        transformed = []
        for row_idx, row in enumerate(rows):
            # Extract date from row or index
            if hasattr(row, "name"):
                date_val = row.name
            elif "date" in row:
                date_val = row["date"]
            elif "Date" in row:
                date_val = row["Date"]
            else:
                raise ValueError(
                    f"Cannot extract date from row {row_idx} for {symbol}. "
                    f"Row missing 'date', 'Date', or index.name. Cannot proceed with price data missing timestamps."
                )

            transformed_row = self.transform_row(row, symbol, date_val)
            transformed.append(transformed_row)

        return transformed

    def set_timezone(self, tz: str) -> None:
        """Set timezone for date handling."""
        self.timezone = tz

    def _extract_date_range(self, rows: list[dict[str, Any]]) -> tuple[Any, Any]:
        """Extract min/max dates from rows.

        Raises:
            ValueError: If date range cannot be determined (fail-fast for data integrity)
        """
        min_row_date = None
        max_row_date = None
        try:
            for row in rows:
                date_str = row.get("date")
                if date_str:
                    row_date = datetime.fromisoformat(date_str).date()
                    if min_row_date is None or row_date < min_row_date:
                        min_row_date = row_date
                    if max_row_date is None or row_date > max_row_date:
                        max_row_date = row_date
        except Exception as e:
            raise ValueError(
                f"Could not determine trading day range from {len(rows)} rows: {e}. "
                f"Date parsing failed—cannot proceed with price data missing valid dates."
            ) from e
        if min_row_date is None or max_row_date is None:
            raise ValueError(
                f"Could not extract date range from {len(rows)} rows. "
                f"All rows missing or had empty date fields. Cannot proceed."
            )
        return min_row_date, max_row_date

    def _precompute_trading_days(self, min_row_date: Any, max_row_date: Any) -> set[Any]:
        """Precompute trading days for O(1) lookups.

        Raises:
            ValueError: If trading day set cannot be created (fail-fast for data integrity)
        """
        if not min_row_date or not max_row_date:
            raise ValueError(
                f"Cannot precompute trading days: min_date={min_row_date}, max_date={max_row_date}. Date range invalid."
            )
        try:
            from algo.infrastructure import MarketCalendar

            trading_day_set = MarketCalendar.create_trading_day_set(min_row_date, max_row_date)
            logger.debug(
                f"[CLUSTER_4_OPT] Precomputed {len(trading_day_set)} trading days "
                f"in range [{min_row_date}, {max_row_date}]"
            )
            if isinstance(trading_day_set, set):
                return trading_day_set
            raise ValueError("MarketCalendar.create_trading_day_set did not return a set")
        except Exception as e:
            raise ValueError(
                f"Could not precompute trading days for range [{min_row_date}, {max_row_date}]: {e}. "
                f"MarketCalendar failed—cannot proceed without trading day validation."
            ) from e

    def _validate_row_trading_day(
        self, row_date_str: Any, row_date: Any, trading_day_set: set[Any] | None, symbol: str | None, tracker: Any
    ) -> bool:
        """Validate if row is from a trading day."""
        from algo.infrastructure import MarketCalendar

        if trading_day_set is not None:
            is_trading_day = row_date in trading_day_set
        else:
            is_trading_day = MarketCalendar.is_trading_day(row_date)

        if not is_trading_day and tracker:
            try:
                tracker.record_error(
                    symbol=symbol or "unknown",
                    error_type="NON_TRADING_DAY",
                    error_message="Data for non-trading day (weekend/holiday)",
                    resolution="rejected",
                )
            except Exception as e:
                raise ValueError(
                    f"Could not record error for {symbol}: {e}. Audit trail broken, cannot proceed."
                ) from e
        return is_trading_day

    def _validate_row_prices(
        self, row: dict[str, Any], symbol: str | None, prior_close_by_symbol: dict[str, float | None], tracker: Any
    ) -> tuple[bool, str | None]:
        """Validate price fields in row."""
        from utils.data.tick_validator import validate_price_tick

        open_val: float | None = row.get("open")
        high_val: float | None = row.get("high")
        low_val: float | None = row.get("low")
        close_val: float | None = row.get("close")
        volume_val: int | None = row.get("volume")

        if open_val is None or high_val is None or low_val is None or close_val is None or volume_val is None:
            return False, None

        if symbol is None:
            return False, None

        symbol_prior_close = prior_close_by_symbol.get(symbol)
        is_valid, errors = validate_price_tick(
            symbol=symbol,
            open_price=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=volume_val,
            prior_close=symbol_prior_close,
            is_etf=(self.asset_class == "etf"),
        )

        if not is_valid and tracker:
            try:
                tracker.record_error(
                    symbol=symbol,
                    error_type="DATA_INVALID",
                    error_message=", ".join(errors),
                    resolution="skipped",
                )
            except Exception as e:
                raise ValueError(
                    f"Could not record error for {symbol}: {e}. Audit trail broken, cannot proceed."
                ) from e
        return is_valid, errors[0] if errors else None

    def _process_row(
        self,
        row: dict[str, Any],
        trading_day_set: set[Any] | None,
        prior_close_by_symbol: dict[str, float | None],
        tracker: Any,
    ) -> tuple[bool, int, int]:
        """Process single row; returns (was_valid, non_trading_count, parse_error_count)."""
        row_date_str: str | None = row.get("date")
        symbol: str | None = row.get("symbol")

        try:
            if not row_date_str or not isinstance(row_date_str, str):
                raise ValueError(
                    f"[PRICE_TRANSFORMER] {symbol}: Row missing required date field — "
                    "cannot load price data without valid dates"
                )
            row_date = datetime.fromisoformat(row_date_str).date()
            if not self._validate_row_trading_day(row_date_str, row_date, trading_day_set, symbol, tracker):
                logger.debug(f"[{symbol}] {row_date}: Non-trading day, rejecting")
                return False, 1, 0
        except (ValueError, TypeError) as e:
            logger.warning(f"[{symbol}] Could not parse date {row_date_str}: {e}")
            return False, 0, 1

        if not symbol or not isinstance(symbol, str):
            logger.warning("[unknown] Missing symbol, skipping row")
            return False, 0, 1

        is_valid, error_msg = self._validate_row_prices(row, symbol, prior_close_by_symbol, tracker)
        if not is_valid:
            if error_msg:
                logger.warning(f"[{symbol}] {row.get('date')}: {error_msg}")
            return False, 0, 1

        if tracker:
            tracker.record_tick(
                symbol=symbol,
                tick_date=row.get("date"),
                data=row,
                source_api="yfinance",
            )
        prior_close_by_symbol[symbol] = row.get("close")
        return True, 0, 0

    def validate_and_transform(self, rows: list[dict[str, Any]], tracker: Any = None) -> list[dict[str, Any]]:
        """Validate and filter rows with trading day filtering and provenance tracking.

        Args:
            rows: Raw price data rows
            tracker: Optional DataProvenanceTracker for recording errors

        Raises:
            ValueError: If date range extraction or trading day precomputation fails
        """
        if not rows:
            return []

        min_row_date, max_row_date = self._extract_date_range(rows)
        if min_row_date is None or max_row_date is None:
            raise ValueError(
                f"Cannot extract date range from {len(rows)} rows. "
                f"All rows missing valid date fields. Cannot proceed with price data missing timestamps."
            )

        trading_day_set = self._precompute_trading_days(min_row_date, max_row_date)
        if trading_day_set is None:
            raise ValueError(
                f"Cannot precompute trading days for date range [{min_row_date}, {max_row_date}]. "
                f"MarketCalendar failed. Cannot proceed without trading day validation."
            )

        final_validated = []
        prior_close_by_symbol: dict[str, float | None] = {}
        non_trading_filtered = 0
        parse_errors = 0

        for row in rows:
            is_valid, non_trading, parse_error = self._process_row(row, trading_day_set, prior_close_by_symbol, tracker)
            if is_valid:
                final_validated.append(row)
            else:
                non_trading_filtered += non_trading
                parse_errors += parse_error

        # Log data quality summary
        if non_trading_filtered > 0 or parse_errors > 0:
            total_input = len(rows)
            filtered_pct = (non_trading_filtered + parse_errors) / total_input * 100 if total_input > 0 else 0
            if rows:
                symbol = rows[0].get("symbol", "unknown")
                if filtered_pct > 5:
                    logger.warning(
                        f"[{symbol}] High rejection rate: {non_trading_filtered} non-trading + "
                        f"{parse_errors} parse errors out of {total_input} rows ({filtered_pct:.1f}%). "
                        f"This may indicate bad data or API issues."
                    )
                else:
                    logger.info(
                        f"[{symbol}] Filtered {non_trading_filtered} non-trading-day + {parse_errors} parse errors "
                        f"from {total_input} rows ({filtered_pct:.1f}%)"
                    )

        return final_validated
