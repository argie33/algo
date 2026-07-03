#!/usr/bin/env python3
"""yfinance Snapshot Loader - Fetch ALL yfinance data once per symbol, store in DB.

CRITICAL FIX 2026-07-02: Consolidates 30,000+ redundant yfinance API calls by having
6+ loaders read from a single snapshot table instead of each calling yfinance separately.

Consolidates redundant calls from:
- value_metrics (PE, PB, PS, dividend)
- positioning_metrics (institutional/insider holdings, short interest)
- stability_metrics (beta, volatility)
- company_profile (sector, industry, country)
- earnings_history (earnings dates)
- earnings_calendar (next earnings date)
- analyst_upgrade_downgrade (analyst counts)
- analyst_sentiment_analysis (recommendation key, analyst counts)

Single fetch per symbol → yfinance_snapshot table → all loaders read from table.
Fetches once per symbol, caches 24 hours. Eliminates 30,000+ redundant API calls.
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
                return []

            info = ticker.info
            if not info or not isinstance(info, dict):
                logger.info(f"[YFINANCE_SNAPSHOT] No info for {symbol}")
                return []

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
                    "fcf_yield": (
                        info["freeCashflow"] / info["marketCap"]
                        if "freeCashflow" in info and "marketCap" in info
                        and info["freeCashflow"] is not None and info["marketCap"] is not None
                        else None
                    ),
                    # Positioning metrics (institutional/insider holdings, short interest)
                    "held_percent_insiders": info.get("insidersPercentHeld"),
                    "held_percent_institutions": info.get("heldPercentInstitutions"),
                    "short_interest": info.get("shortPercentOfFloat"),
                    # Stability metrics (beta, volatility)
                    "beta": info.get("beta"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "market_cap": info.get("marketCap"),
                    # Company profile data (for load_company_profile.py)
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "country": info.get("country"),
                    "exchange": info.get("exchange"),
                    "website": info.get("website"),
                    "long_name": info.get("longName"),
                    # Earnings data (for load_earnings_history.py, load_earnings_calendar.py)
                    "earnings_dates": info.get("earningsDates"),
                    "earnings_date": info.get("earningsDate"),
                    # Analyst data (for load_analyst_upgrade_downgrade.py, load_analyst_sentiment_analysis.py)
                    "recommendation_key": info.get("recommendationKey"),
                    "number_of_analysts": info.get("numberOfAnalystOpinions"),
                    "analysts_underweight": info.get("numberOfAnalystsWhoUnderweight"),
                    "analysts_overweight": info.get("numberOfAnalystsWhoOverweight"),
                    "analysts_hold": info.get("numberOfAnalystsWhoHold"),
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
                "sector": None,
                "industry": None,
                "country": None,
                "exchange": None,
                "website": None,
                "long_name": None,
                "earnings_dates": None,
                "earnings_date": None,
                "recommendation_key": None,
                "number_of_analysts": None,
                "analysts_underweight": None,
                "analysts_overweight": None,
                "analysts_hold": None,
                "data_available": False,
                "unavailable_reason": reason,
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(YFinanceSnapshotLoader))
