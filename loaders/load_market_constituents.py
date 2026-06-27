#!/usr/bin/env python3
"""Market Constituents Loader - S&P 500 + Russell 2000 symbol membership (Market-wide).

Consolidates:
- load_stock_symbols.py (NASDAQ/NYSE tradable symbols)
- load_sp500_constituents.py (S&P 500 membership flag)
- load_russell2000_constituents.py (Russell 2000 membership flag)

Into a single atomic transaction to eliminate fragile cron-based ordering.

Run:
    python3 load_market_constituents.py
"""

import csv
import json
import logging
import os
import re
import socket
import sys
from datetime import date
from io import StringIO
from typing import Any

import pandas as pd
import requests

from loaders.runner import run_loader
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

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
    """Check if security should be excluded from tradable list."""
    return any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS)


class MarketConstituentsLoader(OptimalLoader):
    """Load all tradable symbols and mark S&P 500 / Russell 2000 membership."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        """Fetch all symbols and mark index membership.

        ATOMIC OPERATION:
        1. Fetch NASDAQ/NYSE symbols (primary dataset)
        2. Fetch S&P 500 constituents (enrichment)
        3. Fetch Russell 2000 constituents (enrichment)
        4. Return combined dataset with flags

        This eliminates the fragile cron-based ordering where sp500 and russell
        loaders depend on stock_symbols running first.
        """
        socket.setdefaulttimeout(15.0)

        try:
            # STEP 1: Fetch NASDAQ/NYSE symbols
            logger.info("STEP 1/3: Fetching NASDAQ/NYSE tradable symbols")
            base_symbols = self._fetch_nasdaq_symbols()

            if not base_symbols:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols fetched from NASDAQ/NYSE. "
                    "Cannot load market constituents without base symbol list."
                )

            logger.info(f"Fetched {len(base_symbols)} base symbols from NASDAQ/NYSE")

            # STEP 2: Fetch and index S&P 500 constituents
            logger.info("STEP 2/3: Fetching S&P 500 constituents")
            sp500_symbols = self._fetch_sp500_symbols()
            sp500_set = set(sp500_symbols) if sp500_symbols else set()
            logger.info(f"Fetched {len(sp500_set)} S&P 500 constituents")

            # STEP 3: Fetch and index Russell 2000 constituents
            logger.info("STEP 3/3: Fetching Russell 2000 constituents")
            russell_symbols = self._fetch_russell2000_symbols()
            russell_set = set(russell_symbols) if russell_symbols else set()
            logger.info(f"Fetched {len(russell_set)} Russell 2000 constituents")

            # Enrich base symbols with index membership flags
            for row in base_symbols:
                sym = row["symbol"]
                row["is_sp500"] = sym in sp500_set
                row["is_russell2000"] = sym in russell_set

            logger.info(
                f"Enriched {len(base_symbols)} symbols with index membership. "
                f"S&P 500: {sum(1 for r in base_symbols if r['is_sp500'])} "
                f"Russell 2000: {sum(1 for r in base_symbols if r['is_russell2000'])}"
            )

            return base_symbols

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"[MARKET_CONSTITUENTS] Failed to fetch constituent data: {e}") from e

    def _fetch_nasdaq_symbols(self) -> list[dict[str, Any]]:  # noqa: C901
        """Fetch tradable symbols from NASDAQ/NYSE with security filtering."""
        # Validate URLs
        for url, url_name in [
            (NASDAQ_URL, "NASDAQ_SYMBOLS_URL"),
            (OTHER_URL, "OTHER_SYMBOLS_URL"),
        ]:
            is_valid, error_msg = validate_url(url, allowed_domains=["nasdaqtrader.com"])
            if not is_valid:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] SSRF validation failed for {url_name}: {error_msg}. "
                    "Cannot fetch tradable symbols without valid data source."
                )

        try:
            logger.debug("Downloading NASDAQ list")
            try:
                nas_text = requests.get(NASDAQ_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] NASDAQ symbols fetch timeout. "
                    "Wikipedia API is unreachable or slow."
                ) from e

            logger.debug("Downloading OTHER list")
            try:
                oth_text = requests.get(OTHER_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] Other symbols fetch timeout. "
                    "NASDAQ API is unreachable or slow."
                ) from e

            rows = []
            etf_rows = []

            for text in [nas_text, oth_text]:
                reader = csv.DictReader(text.splitlines(), delimiter="|")
                for r in reader:
                    # CRITICAL: Symbol is required — explicit validation, no defaults
                    if "Symbol" not in r or not r["Symbol"]:
                        raise ValueError(
                            "[MARKET_CONSTITUENTS] Missing or empty 'Symbol' field in row. "
                            "Cannot process market constituent without symbol."
                        )
                    sym = r["Symbol"].strip()
                    if sym.startswith("File Creation Time"):
                        continue

                    # CRITICAL: Security Name is required
                    if "Security Name" not in r:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} missing required 'Security Name' field. "
                            "Cannot process market constituent without name."
                        )
                    name = r["Security Name"].strip()
                    if not name:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} has empty 'Security Name' field. "
                            "Cannot process market constituent with empty name."
                        )

                    # ETFs go to separate table (not stock_symbols)
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
                    if "etf" in name.lower() or "fund" in name.lower():
                        logger.debug(f"Excluding {sym} ({name}) by security name pattern")
                        continue

                    # CRITICAL: Listing Exchange is required
                    if "Listing Exchange" not in r or not r["Listing Exchange"]:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} missing or empty 'Listing Exchange' field. "
                            "Cannot determine proper exchange for market constituent."
                        )
                    exchange = r["Listing Exchange"].upper()
                    rows.append(
                        {
                            "symbol": sym,
                            "security_name": name,
                            "exchange": exchange,
                            "etf": "N",
                        }
                    )

            # Upsert ETFs to separate table
            if etf_rows:
                self._upsert_etf_symbols(etf_rows)

            if not rows:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols parsed from NASDAQ/NYSE data. "
                    "Cannot proceed with market constituent list."
                )
            return rows

        except (requests.RequestException, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch NASDAQ symbols: {e}. "
                "Cannot load market constituents without base symbol data."
            ) from e

    def _fetch_sp500_symbols(self) -> list[str]:
        """Fetch S&P 500 constituents from Wikipedia."""
        is_valid, error_msg = validate_url(SP500_URL, allowed_domains=["wikipedia.org"])
        if not is_valid:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] SSRF validation failed for S&P 500 URL: {error_msg}. "
                "Cannot fetch S&P 500 constituent data."
            )

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(SP500_URL, headers=headers, timeout=15)
            response.raise_for_status()

            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] Could not parse S&P 500 table from Wikipedia. "
                    "Cannot load S&P 500 constituent membership data."
                )

            df = tables[0]
            col = "Symbol" if "Symbol" in df.columns else "Ticker"

            if col not in df.columns:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] S&P 500 table missing {col} column. "
                    "Cannot extract S&P 500 constituents without symbol data."
                )

            symbols: list[str] = df[col].str.strip().tolist()
            return symbols

        except requests.exceptions.Timeout as e:
            raise RuntimeError(
                "[MARKET_CONSTITUENTS] S&P 500 fetch timeout. "
                "Wikipedia API is unreachable or slow."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch S&P 500: {e}. "
                "Cannot load S&P 500 constituent data."
            ) from e

    def _fetch_russell2000_symbols(self) -> list[str]:
        """Fetch Russell 2000 constituents from reliable source."""
        urls = [
            "https://www.multpl.com/russell-2000/table/by-date",
            "https://en.wikipedia.org/wiki/Russell_2000",
        ]

        for url in urls:
            is_valid, error_msg = validate_url(url, allowed_domains=["multpl.com", "wikipedia.org"])
            if not is_valid:
                logger.debug(f"SSRF prevention: Invalid Russell 2000 URL: {error_msg}")
                continue

            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                tables = pd.read_html(StringIO(response.text))
                if not tables:
                    logger.debug(f"No tables found at {url}")
                    continue

                for table in tables:
                    for col in ["Ticker", "Symbol", "symbol"]:
                        if col in table.columns:
                            symbols: list[str] = table[col].str.strip().tolist()
                            if symbols:
                                logger.debug(f"Found Russell 2000 data at {url} using column {col}")
                                return symbols

            except requests.exceptions.Timeout:
                logger.debug(f"Timeout fetching Russell 2000 from {url}")
                continue
            except Exception as e:
                logger.debug(f"Failed to fetch Russell 2000 from {url}: {e}")
                continue

        raise RuntimeError(
            "[MARKET_CONSTITUENTS] Failed to fetch Russell 2000 constituents from any available source. "
            "Cannot load Russell 2000 constituent membership data."
        )

    def _upsert_etf_symbols(self, etf_rows: list[dict[str, Any]]) -> None:
        """Refresh ETF symbols table (keep separate from tradable symbols)."""
        try:
            import psycopg2

            from utils.db.context import DatabaseContext

            with DatabaseContext("write") as cur:
                cur.execute("TRUNCATE TABLE etf_symbols")
                if etf_rows:
                    cur.executemany(
                        "INSERT INTO etf_symbols (symbol, security_name) VALUES (%s, %s)",
                        [(row["symbol"], row["security_name"]) for row in etf_rows],
                    )
            logger.info(f"Refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to refresh etf_symbols: {e}")


if __name__ == "__main__":
    sys.exit(run_loader(MarketConstituentsLoader, global_mode=True))
