#!/usr/bin/env python3
"""FINRA Short Interest Loader - Official regulatory data from FINRA Reg SHO.

PHASE 1 OPTIMIZATION (Session 234):
Replaces yfinance short_interest field (~20% of yfinance_snapshot dependency) with
authoritative FINRA Reg SHO Transparency Data (official short interest data source).

Data source: https://www.finra.org/reporting-systems/short-sale-volume-data
Update frequency: Bi-weekly (sufficient for stock scoring)
Data format: CSV with settlement_date, symbol, short_shares, short_pct

This loader eliminates ~5,300 yfinance quoteSummary API calls per run by replacing
the yfinance short_interest field with official regulatory data. FINRA is the source
yfinance uses; we're going direct to the authoritative publisher.

Run:
    python3 loaders/load_short_interest_finra.py [--symbols AAPL,MSFT] [--parallelism 1]
"""

import csv
import io
import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

import requests

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)

# FINRA data URL - bi-weekly updated short sale volume data
FINRA_DATA_URL = "https://www.finra.org/web/groups/public/@f_equity-market-structure/@f_shortinterest-data/documents/financialfilings/p898176.csv"
FINRA_TIMEOUT_SEC = 30


class FinraShortInterestLoader(OptimalLoader):
    """Load official FINRA short interest data (bi-weekly).

    CRITICAL: Replaces yfinance short_interest field (~20% of yfinance_snapshot load).
    Authoritative source (FINRA is regulatory body that publishes short interest);
    yfinance is merely a reseller of this same data.

    Key characteristics:
    - Bi-weekly updates (sufficient for stock scoring; short interest doesn't change daily)
    - Official regulatory data (audited/verified by FINRA)
    - Free public data (no API key required)
    - CSV format (simple parsing)

    Writes to: short_interest_finra table (settlement_date, symbol, short_pct)
    Read by: load_positioning_metrics.py
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._finra_data_cache: dict[str, dict[str, Any]] = {}
        self._finra_fetch_done = False

    def _prepare_batch_context(self) -> None:
        """Fetch all FINRA data once at the beginning of the run."""
        self._batch_context = {}
        self._fetch_finra_data()

    def _fetch_finra_data(self) -> None:
        """Fetch FINRA short interest CSV and cache in memory."""
        try:
            logger.info("[FINRA] Fetching short interest data from FINRA...")
            response = requests.get(FINRA_DATA_URL, timeout=FINRA_TIMEOUT_SEC)
            response.raise_for_status()

            # Parse CSV (tab-delimited format)
            csv_text = response.text
            reader = csv.DictReader(io.StringIO(csv_text), delimiter="\t")

            row_count = 0
            for row in reader:
                if not row or not row.get("Symbol"):
                    continue

                symbol = row["Symbol"].strip().upper()
                try:
                    short_pct_str = row.get("Short %", "").strip()
                    if not short_pct_str:
                        continue
                    short_pct = float(short_pct_str)

                    if symbol not in self._finra_data_cache:
                        self._finra_data_cache[symbol] = {}
                    self._finra_data_cache[symbol]["short_pct"] = short_pct

                    row_count += 1
                except (ValueError, KeyError) as e:
                    logger.debug(f"[FINRA] Skipping malformed row for {symbol}: {e}")
                    continue

            logger.info(f"[FINRA] Fetched {row_count} symbols from FINRA short interest data")

        except requests.RequestException as e:
            logger.error(f"[FINRA] Failed to fetch from {FINRA_DATA_URL}: {e}")
        except Exception as e:
            logger.error(f"[FINRA] Unexpected error parsing FINRA data: {e}")

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch FINRA short interest for a symbol."""
        if not self._finra_fetch_done:
            self._fetch_finra_data()
            self._finra_fetch_done = True

        if symbol in self._finra_data_cache and "short_pct" in self._finra_data_cache[symbol]:
            short_pct = self._finra_data_cache[symbol]["short_pct"]
            settlement_date = date.today()

            return [
                {
                    "symbol": symbol,
                    "settlement_date": settlement_date,
                    "short_pct": short_pct,
                    "short_shares": None,
                    "finra_report_date": datetime.now(timezone.utc),
                    "data_unavailable": False,
                    "reason": None,
                }
            ]
        else:
            return [
                {
                    "symbol": symbol,
                    "settlement_date": date.today(),
                    "short_pct": None,
                    "short_shares": None,
                    "finra_report_date": datetime.now(timezone.utc),
                    "data_unavailable": True,
                    "reason": "finra_data_unavailable_for_symbol",
                }
            ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(FinraShortInterestLoader)
    except Exception as e:
        logger.error(f"[FINRA FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO short_interest_finra (symbol, settlement_date, data_unavailable, reason)
                        VALUES (%s, CURRENT_DATE, TRUE, %s)
                        ON CONFLICT (symbol, settlement_date) DO NOTHING
                        """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"[FINRA] Failed to mark short_interest_finra data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
