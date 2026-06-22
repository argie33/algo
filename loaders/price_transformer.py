#!/usr/bin/env python3
"""PriceTransformer specialist - handles data transformation and normalization.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Transform and normalize raw price data from yfinance.
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class PriceTransformer:
    """Specialist for transforming price data.

    Handles:
    - Raw data normalization
    - Data type conversions
    - Field mapping and renaming
    - Timezone handling
    """

    def __init__(self):
        """Initialize PriceTransformer."""
        self.timezone = None

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
