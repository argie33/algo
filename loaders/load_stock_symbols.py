#!/usr/bin/env python3
"""Stock Symbols Loader - Load all tradable symbols from NASDAQ/NYSE."""

import csv
import json
import logging
import os
import re
import socket
import sys
from datetime import date
from typing import Optional

import psycopg2
import requests

from loaders.runner import run_loader
from utils.infrastructure.timeout import ExecutionTimeout
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")

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

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch all stock symbols from NASDAQ/NYSE with timeout protection.

        Also populates etf_symbols table with ETF-flagged symbols so that
        the anti-join filter in /api/scores/stockscores can exclude them.

        All symbols in stock_symbols are marked with etf='N' (non-ETF). ETF symbols
        are never inserted into stock_symbols; they are stored in etf_symbols.
        The API filter uses etf='N' to exclude ETFs.
        """
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        # SECURITY FIX S-05: Validate URLs to prevent SSRF attacks
        for url, url_name in [
            (NASDAQ_URL, "NASDAQ_SYMBOLS_URL"),
            (OTHER_URL, "OTHER_SYMBOLS_URL"),
        ]:
            is_valid, error_msg = validate_url(url, allowed_domains=["nasdaqtrader.com"])
            if not is_valid:
                logger.error(f"SSRF prevention: Invalid {url_name}: {error_msg}")
                return None

        try:
            logger.info("Downloading NASDAQ list")
            try:
                nas_text = requests.get(NASDAQ_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                error_msg = "NASDAQ symbols fetch timeout"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
            except requests.exceptions.ConnectionError as e:
                error_msg = "NASDAQ symbols connection error"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

            logger.info("Downloading OTHER list")
            try:
                oth_text = requests.get(OTHER_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                error_msg = "Other symbols fetch timeout"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
            except requests.exceptions.ConnectionError as e:
                error_msg = "Other symbols connection error"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

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

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _upsert_etf_symbols(self, etf_rows: list[dict]) -> None:
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

                # Bulk insert fresh ETF data in single statement
                if etf_rows:
                    cur.executemany(
                        """
                        INSERT INTO etf_symbols (symbol, security_name)
                        VALUES (%s, %s)
                    """,
                        [(row["symbol"], row["security_name"]) for row in etf_rows],
                    )
            logger.info(f"Refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to refresh etf_symbols: {e}")


if __name__ == "__main__":
    sys.exit(run_loader(StockSymbolsLoader, global_mode=True))
