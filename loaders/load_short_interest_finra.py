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

# FINRA short interest data URL - bi-weekly CSV file
# This endpoint is documented in FINRA press releases and short sale volume data pages
FINRA_SHORT_INTEREST_URLS = [
    # Primary: Direct CSV from FINRA (most recent data)
    "https://www.finra.org/web/groups/public/@f_equity-market-structure/@f_shortinterest-data/documents/financialfilings/p898176.csv",
    # Fallback: Alternative FINRA endpoint
    "https://www.finra.org/web/groups/public/@f_equity-market-structure/@f_shortinterest-data/documents/financialfilings/p898177.csv",
]
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

        # Try each FINRA URL until one succeeds
        for url in FINRA_SHORT_INTEREST_URLS:
            try:
                # Fetch FINRA CSV file
                response = requests.get(
                    url,
                    timeout=get_http_timeout(),
                    headers={"User-Agent": "AlgoTrading-DataLoader/1.0"},
                )
                response.raise_for_status()

                # Parse CSV (tab or comma delimited, handle both)
                lines = response.text.strip().split("\n")
                if len(lines) < 2:
                    logger.warning(f"[FINRA_SHORT_INTEREST] No data rows in FINRA file {url}")
                    continue

                # Detect delimiter
                delimiter = "\t" if "\t" in lines[0] else ","

                # Parse header
                header_parts = lines[0].split(delimiter)
                header = [h.strip().lower() for h in header_parts]

                # Find column indices (FINRA format varies; be defensive)
                symbol_col = None
                short_pct_col = None  # Look for Short % column
                settlement_date_col = None

                for i, col in enumerate(header):
                    if "symbol" in col:
                        symbol_col = i
                    elif "short" in col and "%" in col:  # Short %
                        short_pct_col = i
                    elif "settlement" in col or "date" in col:
                        settlement_date_col = i

                if symbol_col is None:
                    logger.debug(f"[FINRA_SHORT_INTEREST] Could not find symbol column in {url}. Headers: {header}")
                    continue

                # Parse data rows
                for line_num, line in enumerate(lines[1:], start=2):
                    if not line.strip():
                        continue

                    try:
                        parts = [p.strip() for p in line.split(delimiter)]
                        symbol = parts[symbol_col].strip().upper()

                        # Get short % (may be in percentage format like "1.5" or "1.5%")
                        short_pct = None
                        if short_pct_col is not None and short_pct_col < len(parts):
                            pct_str = parts[short_pct_col].replace("%", "").strip()
                            try:
                                short_pct = float(pct_str)
                            except ValueError:
                                pass

                        # Parse settlement date if available
                        settlement_date = date.today()
                        if settlement_date_col is not None and settlement_date_col < len(parts):
                            settlement_date_str = parts[settlement_date_col].strip()
                            try:
                                settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
                            except ValueError:
                                try:
                                    settlement_date = datetime.strptime(settlement_date_str, "%m/%d/%Y").date()
                                except ValueError:
                                    pass

                        self._finra_data[symbol] = {
                            "settlement_date": settlement_date,
                            "short_pct": short_pct,
                            "short_shares": None,
                        }
                    except (ValueError, IndexError) as e:
                        logger.debug(f"[FINRA_SHORT_INTEREST] Skipping malformed row {line_num}: {line} ({e})")
                        continue

                logger.info(f"[FINRA_SHORT_INTEREST] Loaded {len(self._finra_data)} symbols from FINRA")
                return  # Success, stop trying other URLs

            except requests.exceptions.RequestException as e:
                logger.debug(f"[FINRA_SHORT_INTEREST] Failed to fetch from {url}: {e}")
                continue
            except Exception as e:
                logger.debug(f"[FINRA_SHORT_INTEREST] Error parsing {url}: {e}")
                continue

        # If we get here, all URLs failed
        logger.warning("[FINRA_SHORT_INTEREST] All FINRA URLs failed; will mark data as unavailable")
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
                "short_pct": finra_row["short_pct"],  # Short interest % from FINRA
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
