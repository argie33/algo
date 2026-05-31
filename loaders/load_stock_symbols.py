#!/usr/bin/env python3
"""Stock Symbols Loader - Load all tradable symbols from NASDAQ/NYSE."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
]


def should_exclude(name: str) -> bool:
    return any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS)


class StockSymbolsLoader(OptimalLoader):
    """Load stock symbols from NASDAQ and NYSE."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch all stock symbols from NASDAQ/NYSE."""
        try:
            logger.info("Downloading NASDAQ list")
            nas_text = requests.get(NASDAQ_URL, timeout=15).text
            logger.info("Downloading OTHER list")
            oth_text = requests.get(OTHER_URL, timeout=15).text

            rows = []
            for text in [nas_text, oth_text]:
                reader = csv.DictReader(text.splitlines(), delimiter="|")
                for r in reader:
                    sym = r.get("Symbol", "").strip()
                    if not sym or sym.startswith("File Creation Time"):
                        continue
                    name = r.get("Security Name", "").strip()

                    # Skip ETFs and excluded securities
                    if r.get("ETF", "").upper() == "Y" or should_exclude(name):
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

            return rows if rows else None

        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return None


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
