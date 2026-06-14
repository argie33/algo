#!/usr/bin/env python3
"""Russell 2000 Constituents Loader - Mark Russell 2000 membership (Market-wide)."""
import sys
import logging
from datetime import date
from typing import Optional, List
import requests

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.timeout import ExecutionTimeout
from loaders.loader_helper import setup_imports
setup_imports()

logger = logging.getLogger(__name__)

class Russell2000ConstituentsLoader(OptimalLoader):
    """Load and mark Russell 2000 constituent symbols."""
    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch Russell 2000 symbols from data source with timeout protection."""
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        try:
            logger.info("Fetching Russell 2000 constituents")

            # Try to fetch from a reliable source
            headers = {'User-Agent': 'Mozilla/5.0'}
            urls = [
                "https://www.multpl.com/russell-2000/table/by-date",
                "https://en.wikipedia.org/wiki/Russell_2000",
            ]

            for url in urls:
                try:
                    import pandas as pd
                    from io import StringIO

                    try:
                        response = requests.get(url, headers=headers, timeout=15)
                        response.raise_for_status()
                    except requests.exceptions.Timeout:
                        logger.debug(f"Russell 2000 fetch timeout from {url}")
                        continue
                    except requests.exceptions.ConnectionError:
                        logger.debug(f"Russell 2000 connection error from {url}")
                        continue

                    tables = pd.read_html(StringIO(response.text))
                    if tables:
                        df = tables[0]
                        if "Symbol" in df.columns or "Ticker" in df.columns:
                            col = "Symbol" if "Symbol" in df.columns else "Ticker"
                            symbols = df[col].str.strip().tolist()
                            logger.info(f"Fetched {len(symbols)} Russell 2000 constituents")
                            return [{
                                'symbol': sym,
                                'is_russell2000': True,
                            } for sym in symbols]
                except Exception as e:
                    logger.debug(f"URL {url} failed: {e}")
                    continue

            logger.warning("Could not fetch Russell 2000 constituents from any source")
            return None

        except Exception as e:
            logger.error(f"Failed to fetch Russell 2000: {e}")
            return None

def main():
    try:
        # Execution timeout: Fetch + parse typically takes 10-20s
        # Set limit to 2 min (120s) to catch hanging requests early
        with ExecutionTimeout(max_seconds=120, label="load_russell2000_constituents"):
            loader = Russell2000ConstituentsLoader()
            result = loader.load_global()

            if result > 0:
                logger.info(f"SUCCESS: {result} Russell 2000 symbols marked")
                return 0
            else:
                logger.warning(f"COMPLETED: No symbols marked")
                return 0
    except Exception as e:
        logger.error(f"Russell 2000 constituents load failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
