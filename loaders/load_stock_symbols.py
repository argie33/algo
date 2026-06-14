#!/usr/bin/env python3
"""Stock Symbols Loader - Load all tradable symbols from NASDAQ/NYSE."""
import sys
from pathlib import Path

# Add project root to sys.path BEFORE importing utils module
loader_dir = Path(__file__).parent
project_root = loader_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from datetime import date
from typing import Optional, List
import os
import re
import csv
import requests

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")

EXCLUSION_PATTERNS = [
    r"\bpreferred\b", r"\bwarrant(s)?\b", r"\bunit(s)?\b", r"\bconvertible\b",
    r"\bpreferred share(s)?\b", r"\btest stock\b", r"\bfund\b", r"\bblank check\b",
    r"\bspac\b", r"\bspecial purpose\b", r"\binvestment corp\b",
    r"\betn\b", r"\bexchange[- ]traded note\b", r"\betf\b",
    r"\bnotes?\b.*\bdue\b",  # bonds/notes with maturity date
    r"\bclosed[- ]end\b", r"\b2x\b", r"\b3x\b", r"\binverse\b",
]

def should_exclude(name: str) -> bool:
    return any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS)

from loaders.loader_helper import setup_imports
setup_imports()

class StockSymbolsLoader(OptimalLoader):
    """Load stock symbols from NASDAQ and NYSE."""
    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch all stock symbols from NASDAQ/NYSE.

        Also populates etf_symbols table with ETF-flagged symbols so that
        the anti-join filter in /api/scores/stockscores can exclude them.
        """
        try:
            logger.info("Downloading NASDAQ list")
            nas_text = requests.get(NASDAQ_URL, timeout=15).text
            logger.info("Downloading OTHER list")
            oth_text = requests.get(OTHER_URL, timeout=15).text

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
                        etf_rows.append({'symbol': sym, 'security_name': name})
                        continue

                    if should_exclude(name):
                        continue
                    if re.match(r'^[A-Z]+\.[A-Z]$', sym):
                        continue
                    if r.get("Test Issue", "").upper() == "Y":
                        continue
                    if r.get("Financial Status", "").strip() == "D":
                        continue

                    rows.append({
                        'symbol': sym,
                        'security_name': name,
                        'exchange': r.get("Listing Exchange", "NASDAQ").upper(),
                        'etf': 'N',
                    })

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
            from utils.database_context import DatabaseContext
            with DatabaseContext('write') as cur:
                # Truncate to clear stale ETF entries (e.g., from delistings)
                cur.execute("TRUNCATE TABLE etf_symbols")
                logger.debug("Truncated etf_symbols table")

                # Bulk insert fresh ETF data
                for row in etf_rows:
                    cur.execute("""
                        INSERT INTO etf_symbols (symbol, security_name)
                        VALUES (%s, %s)
                    """, (row['symbol'], row['security_name']))
            logger.info(f"Refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except Exception as e:
            logger.warning(f"Failed to refresh etf_symbols: {e}")

def main():
    loader = StockSymbolsLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} symbols loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No symbols loaded")
        return 0

if __name__ == "__main__":
    sys.exit(main())
