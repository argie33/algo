#!/usr/bin/env python3
"""yfinance Snapshot Loader - Fetch all yfinance data once per symbol, store in DB.

Consolidates redundant yfinance calls from value_metrics, positioning_metrics, stability_metrics.
Single fetch per symbol → DB → all loaders read from table.

Data:
- PE, PB, PS ratios (for value_metrics)
- Dividend yield, FCF yield (for value_metrics)
- Institutional holdings, insider holdings (for positioning_metrics)
- Beta, volatility (for stability_metrics)

Fetches once per symbol, caches 24 hours. Eliminates 6x redundant API calls.
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from utils.external.yfinance import YFinanceWrapper
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class YFinanceSnapshotLoader(OptimalLoader):
    """Fetch all yfinance data once per symbol, store in yfinance_snapshot table."""

    table_name = "yfinance_snapshot"
    primary_key = ("symbol",)
    watermark_field = "fetched_at"
    exclude_etfs_from_symbols = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch all yfinance data for a symbol, store as single snapshot record.

        Returns all metrics in one row to avoid 6 separate yfinance API calls.
        """
        try:
            ticker = YFinanceWrapper.get_ticker(symbol)
            if not ticker:
                logger.info(f"[YFINANCE_SNAPSHOT] Ticker not found: {symbol}")
                return self._unavailable_record(symbol, "Ticker not found")

            info = ticker.info
            if not info or not isinstance(info, dict):
                logger.info(f"[YFINANCE_SNAPSHOT] No info for {symbol}")
                return self._unavailable_record(symbol, "No ticker info available")

            # Extract all yfinance metrics into single snapshot
            return [
                {
                    "symbol": symbol,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    # Value metrics (PE, PB, PS, dividend)
                    "pe_ratio": info.get("trailingPE"),
                    "pb_ratio": info.get("priceToBook"),
                    "ps_ratio": info.get("priceToSalesTrailing12Months"),
                    "peg_ratio": info.get("pegRatio"),
                    "dividend_yield": info.get("dividendYield"),
                    "fcf_yield": info.get("freeCashflow", 0) / (info.get("marketCap", 1) or 1)
                    if info.get("marketCap")
                    else None,
                    # Positioning metrics (institutional/insider holdings, short interest)
                    "held_percent_insiders": info.get("insidersPercentHeld"),
                    "held_percent_institutions": info.get("heldPercentInstitutions"),
                    "short_interest": info.get("shortPercentOfFloat"),
                    # Stability metrics (beta, volatility)
                    "beta": info.get("beta"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "market_cap": info.get("marketCap"),
                    # Raw data for debugging
                    "data_available": True,
                    "unavailable_reason": None,
                }
            ]

        except Exception as e:
            logger.error(f"[YFINANCE_SNAPSHOT] Error fetching {symbol}: {e}")
            return self._unavailable_record(symbol, str(e)[:255])

    def _unavailable_record(self, symbol: str, reason: str) -> list[dict[str, Any]]:
        """Return unavailable record with explicit reason."""
        return [
            {
                "symbol": symbol,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "pe_ratio": None,
                "pb_ratio": None,
                "ps_ratio": None,
                "peg_ratio": None,
                "dividend_yield": None,
                "fcf_yield": None,
                "held_percent_insiders": None,
                "held_percent_institutions": None,
                "short_interest": None,
                "beta": None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
                "market_cap": None,
                "data_available": False,
                "unavailable_reason": reason,
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(YFinanceSnapshotLoader))
