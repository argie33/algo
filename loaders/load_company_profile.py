#!/usr/bin/env python3
"""Company Profile Loader - populate from yfinance with sector/industry enrichment."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.external.yfinance import get_ticker
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    """Load company profiles with sector and industry from yfinance."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Fetch company info from yfinance for a symbol."""
        ticker = get_ticker(symbol)
        if not ticker:
            raise RuntimeError(
                f"[COMPANY_PROFILE] Failed to fetch ticker for {symbol}. "
                "Cannot retrieve company profile without valid ticker."
            )
        try:
            info = ticker.info
            if not info or not isinstance(info, dict):
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: ticker.info is {type(info).__name__} or empty. "
                    "Cannot fetch company profile without valid info dict[str, Any]."
                )
            # Market cap (optional but valuable for analysis)
            market_cap = info.get("marketCap")
            if market_cap is None:
                market_cap = info.get("market_cap")

            # Company name is REQUIRED - fail fast if missing
            if "longName" in info and info["longName"]:
                company_name = info["longName"]
            elif "shortName" in info and info["shortName"]:
                company_name = info["shortName"]
                logger.debug(f"{symbol}: Using shortName instead of longName for company name")
            else:
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing company name (longName/shortName). "
                    "Cannot store company profile without a name."
                )

            # Exchange is REQUIRED for routing/compliance
            exchange = info.get("exchange")
            if not exchange:
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing exchange. "
                    "Cannot store company profile without exchange information."
                )

            # Sector is REQUIRED for position sizing and concentration checks
            sector = info.get("sector")
            if not sector:
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing sector classification. "
                    "Sector data is required for position sizing and sector concentration limits."
                )

            # Industry is REQUIRED for sector analysis and position management
            industry = info.get("industry")
            if not industry:
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing industry classification. "
                    "Industry data is required for sector rotation and clustering."
                )

            return [
                {
                    "symbol": symbol,
                    "ticker": symbol,
                    "short_name": company_name,
                    "long_name": company_name,
                    "display_name": company_name,
                    "sector": sector,
                    "industry": industry,
                    "exchange": exchange,
                    "website": info.get("website"),
                    "employees": info.get("fullTimeEmployees"),
                    "market_cap": (int(market_cap) if market_cap and market_cap > 0 else None),
                }
            ]
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[COMPANY_PROFILE] Failed to fetch profile for {symbol}: {e}. "
                "Cannot proceed without sector/industry data."
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(CompanyProfileLoader))
