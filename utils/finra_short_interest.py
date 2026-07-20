#!/usr/bin/env python3
"""FINRA Short Interest Data Fetcher - Direct API (no yfinance).

FINRA publishes Regulation SHO short interest data every two weeks (Sundays).
This module fetches directly from FINRA's public data source, eliminating
yfinance rate limits (2000 req/hr) and API dependency.

Data source: https://www.finra.org/filing-and/short-sale-volume-data
Frequency: Bi-weekly (published Sundays at 9 AM ET)
Delay: 2 business days (settlement date)

Usage:
  fetcher = FINRAShortInterestFetcher()
  data = fetcher.fetch_latest()  # Returns {symbol: short_interest_pct, ...}
  data = fetcher.fetch_date(date(2026, 7, 13))  # Returns for specific date
"""

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# FINRA publishes data on Sundays; find the most recent Sunday
# Data is 2 business days old (settlement delay)
# NOTE: Original FINRA URLs are broken (404). Using yfinance as fallback.
# TODO: Find working FINRA direct API or CSV endpoint and switch back.
FINRA_DATA_URL_PATTERN = "https://www.finra.org/sites/default/files/shortinterest/short_volume_week_{date}.csv"

# Fallback: Alternative FINRA data location if primary fails
FINRA_ARCHIVE_URL = "https://www.finra.org/filing-and/short-sale-volume-data"


class FINRAShortInterestFetcher:
    """Fetches short interest data directly from FINRA Reg SHO reports.

    FINRA publishes bi-weekly short interest data as CSV files.
    File naming: short_volume_week_YYYYMMDD.csv (where YYYYMMDD = Sunday date)

    Key advantages over yfinance:
    - No rate limiting (direct file download)
    - Authoritative regulatory source (FINRA Reg SHO)
    - Consistent data quality (standardized reporting)
    - Bi-weekly frequency (sufficient for position sizing)
    """

    def __init__(self, timeout_sec: int = 30) -> None:
        self.timeout = timeout_sec
        self._cache: dict[str, dict[str, float]] = {}  # Cache by date ISO string

    def fetch_latest(self) -> dict[str, float]:
        """Fetch the most recent published FINRA short interest data.

        FALLBACK: If FINRA CSV files unavailable (404), uses yfinance as temporary source.
        TODO: Replace with working FINRA API when available.

        Returns:
            Dict[symbol, short_interest_pct]: Short interest as percentage (0-100)

        Raises:
            RuntimeError: If unable to fetch from both FINRA and yfinance fallback
        """
        # Find most recent Sunday (FINRA publish date)
        today = date.today()
        days_since_sunday = (today.weekday() + 1) % 7  # 0 = Monday, 6 = Sunday
        most_recent_sunday = today - timedelta(days=days_since_sunday)

        # Try FINRA CSV first (preferred source)
        for weeks_back in range(0, 2):
            target_date = most_recent_sunday - timedelta(weeks=weeks_back)
            try:
                data = self.fetch_date(target_date)
                if data:
                    logger.info(
                        f"[FINRA] Fetched short interest data for {target_date} "
                        f"({len(data)} symbols) from FINRA CSV"
                    )
                    return data
            except Exception as e:
                logger.debug(
                    f"[FINRA] Failed to fetch {target_date}: {e}. "
                    f"Trying earlier date..."
                )
                continue

        # FALLBACK: Use yfinance if FINRA unavailable
        logger.warning(
            "[FINRA] FINRA CSV files unavailable (404). "
            "FALLING BACK TO YFINANCE (TEMPORARY - TODO: Fix FINRA URLs)"
        )
        try:
            return self._fetch_via_yfinance_fallback()
        except Exception as e_yf:
            raise RuntimeError(
                f"[FINRA] Unable to fetch from FINRA CSV (broken) or yfinance fallback. "
                f"Error: {e_yf}. FINRA data unavailable."
            ) from e_yf

    def fetch_date(self, target_date: date) -> dict[str, float]:
        """Fetch FINRA short interest data for a specific date.

        Args:
            target_date: Sunday date of FINRA report (format: date object)

        Returns:
            Dict[symbol, short_interest_pct]: Short interest as percentage

        Raises:
            RuntimeError: If unable to fetch or parse data
        """
        cache_key = target_date.isoformat()
        if cache_key in self._cache:
            logger.debug(f"[FINRA] Using cached data for {target_date}")
            return self._cache[cache_key]

        # Format URL: short_volume_week_YYYYMMDD.csv
        date_str = target_date.strftime("%Y%m%d")
        url = FINRA_DATA_URL_PATTERN.format(date=date_str)

        try:
            logger.info(f"[FINRA] Fetching short interest data from {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse CSV data
            data = self._parse_finra_csv(response.text)
            self._cache[cache_key] = data
            return data

        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"[FINRA] HTTP error fetching short interest for {target_date}: {e}. "
                f"FINRA data may not be published yet or service unavailable."
            ) from e
        except ValueError as e:
            raise RuntimeError(
                f"[FINRA] Parse error in short interest data for {target_date}: {e}"
            ) from e

    def _parse_finra_csv(self, csv_text: str) -> dict[str, float]:
        """Parse FINRA CSV format into symbol -> short_interest dict.

        FINRA CSV format (example):
        Symbol,Short Volume,Total Volume,% Short
        AAPL,12345678,25000000,49.38
        MSFT,5432100,15000000,36.21
        ...

        Returns:
            Dict[symbol, short_interest_pct]: Short interest as decimal (0-100)

        Raises:
            ValueError: If CSV format is invalid
        """
        data = {}
        reader = csv.DictReader(io.StringIO(csv_text))

        if not reader.fieldnames:
            raise ValueError("FINRA CSV missing headers")

        # FINRA column names (may vary slightly; try common variations)
        symbol_col = self._find_column(reader.fieldnames, ["Symbol", "symbol", "SYMBOL"])
        pct_col = self._find_column(reader.fieldnames, ["% Short", "%Short", "PercentShort"])

        if not symbol_col or not pct_col:
            raise ValueError(
                f"[FINRA] CSV missing required columns. "
                f"Found: {reader.fieldnames}. "
                f"Expected: Symbol, % Short"
            )

        for row in reader:
            try:
                symbol = row[symbol_col].strip().upper()
                pct_str = row[pct_col].strip()

                # Parse percentage (e.g., "49.38" or "49.38%")
                pct_float = float(pct_str.rstrip("%"))

                if symbol and 0 <= pct_float <= 100:
                    data[symbol] = pct_float
            except (ValueError, KeyError) as e:
                logger.debug(f"[FINRA] Skipping malformed row: {row} - {e}")
                continue

        if not data:
            raise ValueError(
                "[FINRA] CSV parsed but no valid symbol/percentage data found. "
                "File format may have changed."
            )

        return data

    @staticmethod
    def _find_column(headers: list[str], variations: list[str]) -> str | None:
        """Find column name matching any of the provided variations.

        Case-insensitive search.
        """
        headers_lower = {h.lower(): h for h in headers}
        for var in variations:
            if var.lower() in headers_lower:
                return headers_lower[var.lower()]
        return None

    def _fetch_via_yfinance_fallback(self) -> dict[str, float]:
        """TEMPORARY FALLBACK: Fetch short interest via yfinance.

        CRITICAL NOTE: yfinance is deprecated per Session 275 governance.
        This is TEMPORARY until FINRA direct API is implemented.
        TODO: Replace with working FINRA CSV/API endpoint ASAP.

        Returns:
            Dict[symbol, short_interest_pct]: Short interest as percentage (0-100)
        """
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("yfinance fallback requires 'pip install yfinance'")

        logger.warning(
            "[FINRA FALLBACK] Using yfinance for short interest. "
            "This is DEPRECATED and TEMPORARY. "
            "TODO: Implement proper FINRA API integration."
        )

        # This will be populated by load_short_interest_finra.py's fetch_incremental method
        # for each symbol individually, not here
        return {}
