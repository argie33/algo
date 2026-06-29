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
        """Fetch company info from yfinance for a symbol.

        Required fields (fail-fast on missing):
            - ticker: valid yfinance ticker object
            - longName/shortName: company name
            - exchange: stock exchange
            - sector: industry sector
            - industry: industry classification

        Optional fields (logged at DEBUG when missing):
            - website: company website URL
            - fullTimeEmployees: employee count
            - marketCap: market capitalization
        """
        ticker = get_ticker(symbol)
        if not ticker:
            logger.error(
                f"[COMPANY_PROFILE] {symbol}: Failed to fetch ticker object. "
                "Cannot retrieve company profile without valid yfinance ticker."
            )
            raise RuntimeError(
                f"[COMPANY_PROFILE] {symbol}: Failed to fetch ticker object"
            )
        try:
            info = ticker.info
            if not info or not isinstance(info, dict):
                logger.error(
                    f"[COMPANY_PROFILE] {symbol}: ticker.info returned {type(info).__name__} or empty. "
                    "Expected dict[str, Any] from yfinance."
                )
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: ticker.info invalid or empty"
                )

            # REQUIRED: Company name - fail fast if missing
            if info.get("longName"):
                company_name = info["longName"]
            elif info.get("shortName"):
                company_name = info["shortName"]
                logger.debug(f"[COMPANY_PROFILE] {symbol}: Using shortName as fallback for company name")
            else:
                logger.error(
                    f"[COMPANY_PROFILE] {symbol}: Missing company name (longName/shortName). "
                    "Company name is required for profile storage."
                )
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing company name (longName/shortName)"
                )

            # REQUIRED: Exchange - fail fast if missing
            exchange = info.get("exchange")
            if not exchange:
                logger.error(
                    f"[COMPANY_PROFILE] {symbol}: Missing exchange from yfinance. "
                    "Exchange is required for routing and compliance validation."
                )
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing exchange classification"
                )

            # REQUIRED: Sector - fail fast if missing
            sector = info.get("sector")
            if not sector:
                logger.error(
                    f"[COMPANY_PROFILE] {symbol}: Missing sector from yfinance. "
                    "Sector is required for position sizing and concentration checks."
                )
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing sector classification"
                )

            # REQUIRED: Industry - fail fast if missing
            industry = info.get("industry")
            if not industry:
                logger.error(
                    f"[COMPANY_PROFILE] {symbol}: Missing industry from yfinance. "
                    "Industry is required for sector analysis and clustering."
                )
                raise RuntimeError(
                    f"[COMPANY_PROFILE] {symbol}: Missing industry classification"
                )

            # OPTIONAL: Market cap - log if missing but do not fail
            market_cap = info.get("marketCap")
            if market_cap is None:
                market_cap = info.get("market_cap")
            if market_cap is None:
                logger.debug(f"[COMPANY_PROFILE] {symbol}: No market cap data available from yfinance")

            # OPTIONAL: Website - log if missing but do not fail
            website = info.get("website")
            if not website:
                logger.debug(f"[COMPANY_PROFILE] {symbol}: No website data available from yfinance")

            # OPTIONAL: Employee count - log if missing but do not fail
            employees = info.get("fullTimeEmployees")
            if not employees:
                logger.debug(f"[COMPANY_PROFILE] {symbol}: No employee count available from yfinance")

            logger.info(
                f"[COMPANY_PROFILE] {symbol}: Successfully loaded profile "
                f"(name={company_name}, exchange={exchange}, sector={sector}, industry={industry})"
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
                    "website": website,
                    "employees": employees,
                    "market_cap": (int(market_cap) if market_cap and market_cap > 0 else None),
                }
            ]
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(
                f"[COMPANY_PROFILE] {symbol}: Type error during profile fetch: {type(e).__name__}: {e}. "
                "Cannot proceed without valid sector/industry/exchange data."
            )
            raise RuntimeError(
                f"[COMPANY_PROFILE] {symbol}: Type error during profile parsing"
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(CompanyProfileLoader))
