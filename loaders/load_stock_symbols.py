#!/usr/bin/env python3
"""Stock Symbols Loader - Load all tradable symbols from NASDAQ/NYSE."""

import csv
import logging
import os
import re
import socket
import sys
from datetime import date
from typing import List, Optional

import requests

from utils.infrastructure.timeout import ExecutionTimeout
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv(
    "NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
)
OTHER_URL = os.getenv(
    "OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
)

EXCLUSION_PATTERNS = [
    r"\bpreferred\b",
    r"\bwarrant(s)?\b",
    r"\bunit(s)?\b",
    r"\bconvertible\b",
    r"\bpreferred share(s)?\b",
    r"\btest stock\b",
    r"\bfund\b",
    r"\bblank check\b",
    r"\bspac\b",
    r"\bspecial purpose\b",
    r"\binvestment corp\b",
    r"\betn\b",
    r"\bexchange[- ]traded note\b",
    r"\betf\b",
    r"\bnotes?\b.*\bdue\b",  # bonds/notes with maturity date
    r"\bclosed[- ]end\b",
    r"\b2x\b",
    r"\b3x\b",
    r"\binverse\b",
]


def should_exclude(name: str) -> bool:
    return any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS)


class StockSymbolsLoader(OptimalLoader):
    """Load stock symbols from NASDAQ and NYSE."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch all stock symbols from NASDAQ/NYSE with timeout protection.

        Also populates etf_symbols table with ETF-flagged symbols so that
        the anti-join filter in /api/scores/stockscores can exclude them.
        """
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        try:
            logger.info("Downloading NASDAQ list")
            try:
                nas_text = requests.get(NASDAQ_URL, timeout=15).text
            except requests.exceptions.Timeout:
                logger.error("NASDAQ symbols fetch timeout")
                return None
            except requests.exceptions.ConnectionError:
                logger.error("NASDAQ symbols connection error")
                return None

            logger.info("Downloading OTHER list")
            try:
                oth_text = requests.get(OTHER_URL, timeout=15).text
            except requests.exceptions.Timeout:
                logger.error("Other symbols fetch timeout")
                return None
            except requests.exceptions.ConnectionError:
                logger.error("Other symbols connection error")
                return None

            rows = []
            etf_rows = []
            for text in [nas_text, oth_text]:
                reader = csv.DictReader(text.splitlines(), delimiter="|")
                for r in reader:
                    sym = r.get("Symbol", "").strip()
                    if not sym or sym.startswith("File Creation Time"):
                        continue
                    name = r.get("Security Name", "").strip()

                    # ETF-flagged symbols go into etf_symbols table (not stock_symbols)
                    if r.get("ETF", "").upper() == "Y":
                        etf_rows.append({"symbol": sym, "security_name": name})
                        continue

                    if should_exclude(name):
                        continue
                    if re.match(r"^[A-Z]+\.[A-Z]$", sym):
                        continue
                    if r.get("Test Issue", "").upper() == "Y":
                        continue
                    if r.get("Financial Status", "").strip() == "D":
                        continue

                    # Exclude by security name as well (catches mislabeled ETFs)
                    if "etf" in name.lower() or "fund" in name.lower():
                        logger.debug(f"Excluding {sym} ({name}) by security name pattern")
                        continue

                    rows.append(
                        {
                            "symbol": sym,
                            "security_name": name,
                            "exchange": r.get("Listing Exchange", "NASDAQ").upper(),
                            "etf": "N",
                        }
                    )

            # Populate etf_symbols so the anti-join in /api/scores/stockscores works
            if etf_rows:
                self._upsert_etf_symbols(etf_rows)

            return rows if rows else None

        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return None

    def _upsert_etf_symbols(self, etf_rows: List[dict]) -> None:
        """Replace ETF symbols in etf_symbols table to keep it in sync with source data.

        Truncates the table first to ensure it only contains current ETFs from NASDAQ/NYSE,
        then reloads. This prevents stale entries for delisted ETFs and ensures the table
        never gets out of sync with the source.
        """
        try:
            from utils.db.context import DatabaseContext

            with DatabaseContext("write") as cur:
                # Truncate to clear stale ETF entries (e.g., from delistings)
                cur.execute("TRUNCATE TABLE etf_symbols")
                logger.debug("Truncated etf_symbols table")

                # Bulk insert fresh ETF data
                for row in etf_rows:
                    cur.execute(
                        """
                        INSERT INTO etf_symbols (symbol, security_name)
                        VALUES (%s, %s)
                    """,
                        (row["symbol"], row["security_name"]),
                    )
            logger.info(f"Refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except Exception as e:
            logger.warning(f"Failed to refresh etf_symbols: {e}")


def main():
    try:
        # Execution timeout: Fetch 2 files + parse typically takes 10-20s
        # Set limit to 2 min (120s) to catch hanging requests early
        with ExecutionTimeout(max_seconds=120, label="load_stock_symbols"):
            loader = StockSymbolsLoader()
            result = loader.load_global()

            if result > 0:
                logger.info(f"SUCCESS: {result} symbols loaded")
                return 0
            else:
                logger.warning("COMPLETED: No symbols loaded")
                return 0
    except Exception as e:
        logger.error(f"Stock symbols load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
