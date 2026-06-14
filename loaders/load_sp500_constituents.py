#!/usr/bin/env python3
"""S&P 500 Constituents Loader - Mark S&P 500 membership (Market-wide)."""
import sys
import logging
from datetime import date
from typing import Optional, List
import pandas as pd
import requests
from io import StringIO

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

class SP500ConstituentsLoader(OptimalLoader):
    """Load and mark S&P 500 constituent symbols."""
    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch S&P 500 symbols from Wikipedia with timeout protection."""
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        try:
            logger.info("Fetching S&P 500 constituents from Wikipedia")

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            try:
                response = requests.get(SP500_URL, headers=headers, timeout=15)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                logger.error("S&P 500 fetch timeout")
                return None
            except requests.exceptions.ConnectionError:
                logger.error("S&P 500 connection error")
                return None

            tables = pd.read_html(StringIO(response.text))
            if not tables:
                logger.error("Could not find S&P 500 table")
                return None

            df = tables[0]
            col = "Symbol" if "Symbol" in df.columns else "Ticker"
            symbols = df[col].str.strip().tolist()

            logger.info(f"Fetched {len(symbols)} S&P 500 constituents")

            # Return rows with is_sp500 flag set to true
            return [{
                'symbol': sym,
                'is_sp500': True,
            } for sym in symbols]

        except Exception as e:
            logger.error(f"Failed to fetch S&P 500 list: {e}")
            return None

def main():
    try:
        # Execution timeout: Fetch + parse typically takes 10-20s
        # Set limit to 2 min (120s) to catch hanging requests early
        with ExecutionTimeout(max_seconds=120, label="load_sp500_constituents"):
            loader = SP500ConstituentsLoader()
            result = loader.load_global()

            if result > 0:
                logger.info(f"SUCCESS: {result} S&P 500 symbols marked")
                return 0
            else:
                logger.warning(f"COMPLETED: No symbols marked")
                return 0
    except Exception as e:
        logger.error(f"S&P 500 constituents load failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
