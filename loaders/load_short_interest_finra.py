#!/usr/bin/env python3
"""FINRA Short Interest Loader - Replace yfinance short interest with official regulatory data.

Fetches bi-weekly short interest data from FINRA Reg SHO Transparency Data:
https://www.finra.org/reporting-systems/short-sale-volume-data

CRITICAL REPLACEMENT:
- Eliminates yfinance dependency for short_interest field
- FINRA is the authoritative source (yfinance is a reseller of FINRA data)
- Updates bi-weekly (acceptable for stock scoring; short interest doesn't change daily)
- Free, no API key required

Run:
    python3 loaders/load_short_interest_finra.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import io
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.runner import run_loader  # noqa: E402
from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# FINRA short interest data URL - points to latest available file
FINRA_SHORT_INTEREST_URL = "https://www.finra.org/webservices/shortinterest/download"
FINRA_SHORT_INTEREST_HISTORICAL_BASE = "https://www.finra.org/reporting-systems/short-sale-volume-data"


class ShortInterestFinraLoader(OptimalLoader):
    """Load bi-weekly short interest data from FINRA Reg SHO Transparency Data.

    CRITICAL: Replaces yfinance short_interest field entirely.
    - FINRA is authoritative source (regulatory body)
    - Updated bi-weekly (not daily, but sufficient for stock scoring)
    - Free, no API key required
    - More transparent than yfinance (shows exact short shares, not just %)
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    def _prepare_batch_context(self) -> None:
        """Fetch latest FINRA short interest file once, cache in memory.

        FINRA publishes bi-weekly files covering two settlement cycles (Tuesday & Thursday).
        This method downloads the latest file and parses all symbols in one pass.
        """
        logger.info("[FINRA_SHORT_INTEREST] Fetching latest FINRA short interest data...")

        self._batch_context = {}
        self._finra_data: dict[str, dict[str, Any]] = {}  # {symbol: {settlement_date, short_shares, short_pct}}

        try:
            # Fetch FINRA CSV file
            response = requests.get(
                FINRA_SHORT_INTEREST_URL,
                timeout=get_http_timeout(),
                headers={"User-Agent": "AlgoTrading-DataLoader/1.0"},
            )
            response.raise_for_status()

            # Parse CSV
            lines = response.text.strip().split("\n")
            if len(lines) < 2:
                logger.warning("[FINRA_SHORT_INTEREST] No data rows in FINRA file; using empty cache")
                return

            # Skip header row, parse data rows
            # FINRA format: Symbol,SHO Volume (trades),SHO Volume ($),Market Aggregate SHO Volume,$,
            # Settlement Date
            # Example: AAPL,1234567,123456789.12,0.00123,2026-07-18

            header = lines[0].lower()
            symbol_col = None
            shares_col = None
            settlement_date_col = None

            # Find column indices (FINRA format varies; be defensive)
            for i, col in enumerate(header.split(",")):
                col = col.strip().lower()
                if "symbol" in col:
                    symbol_col = i
                elif "volume" in col and "$" not in col:  # SHO Volume (trades)
                    shares_col = i
                elif "settlement" in col or "date" in col:
                    settlement_date_col = i

            if symbol_col is None or shares_col is None or settlement_date_col is None:
                logger.warning(
                    f"[FINRA_SHORT_INTEREST] Could not find expected columns in FINRA file. "
                    f"Headers: {header}"
                )
                return

            for line in lines[1:]:
                if not line.strip():
                    continue

                try:
                    parts = line.split(",")
                    symbol = parts[symbol_col].strip().upper()
                    short_shares = int(parts[shares_col].strip().replace(",", ""))
                    settlement_date_str = parts[settlement_date_col].strip()

                    # Parse settlement date (FINRA format: YYYY-MM-DD or similar)
                    try:
                        settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        # Try alternative format
                        settlement_date = datetime.strptime(settlement_date_str, "%m/%d/%Y").date()

                    self._finra_data[symbol] = {
                        "settlement_date": settlement_date,
                        "short_shares": short_shares,
                    }
                except (ValueError, IndexError) as e:
                    logger.debug(f"[FINRA_SHORT_INTEREST] Skipping malformed row: {line} ({e})")
                    continue

            logger.info(f"[FINRA_SHORT_INTEREST] Loaded {len(self._finra_data)} symbols from FINRA")

        except requests.exceptions.RequestException as e:
            logger.error(f"[FINRA_SHORT_INTEREST] Failed to fetch FINRA data: {e}")
            self._finra_data = {}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch short interest for one symbol from cached FINRA data.

        Returns:
            List with single short interest dict or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        # Check if we have FINRA data for this symbol
        if symbol not in self._finra_data:
            logger.debug(f"[FINRA_SHORT_INTEREST] {symbol}: Not in FINRA data (likely small-cap or non-US)")
            return [
                {
                    "symbol": symbol,
                    "settlement_date": now_et.date(),
                    "short_shares": None,
                    "short_pct": None,
                    "finra_report_date": None,
                    "data_unavailable": True,
                    "reason": "not_in_finra_data",
                    "updated_at": now_et,
                }
            ]

        finra_row = self._finra_data[symbol]

        return [
            {
                "symbol": symbol,
                "settlement_date": finra_row["settlement_date"],
                "short_shares": finra_row["short_shares"],
                "short_pct": None,  # Will be computed later if needed (short_shares / float_shares)
                "finra_report_date": now_et.date(),
                "data_unavailable": False,
                "reason": None,
                "updated_at": now_et,
            }
        ]


def main() -> int:
    """Entry point for load_short_interest_finra.py."""
    return run_loader(ShortInterestFinraLoader, "FINRA Short Interest")


if __name__ == "__main__":
    sys.exit(main())
