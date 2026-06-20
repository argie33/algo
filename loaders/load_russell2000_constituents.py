#!/usr/bin/env python3
"""Russell 2000 Constituents Loader - Mark Russell 2000 membership (Market-wide)."""

import json
import logging
import socket
import sys
from datetime import date

import requests

from loaders.runner import run_loader
from utils.infrastructure.timeout import ExecutionTimeout
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class Russell2000ConstituentsLoader(OptimalLoader):
    """Load and mark Russell 2000 constituent symbols."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch Russell 2000 symbols from data source with timeout protection."""
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        try:
            logger.info("Fetching Russell 2000 constituents")

            # Try to fetch from a reliable source
            headers = {"User-Agent": "Mozilla/5.0"}
            urls = [
                "https://www.multpl.com/russell-2000/table/by-date",
                "https://en.wikipedia.org/wiki/Russell_2000",
            ]

            for url in urls:
                # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
                is_valid, error_msg = validate_url(url, allowed_domains=["multpl.com", "wikipedia.org"])
                if not is_valid:
                    logger.debug(f"SSRF prevention: Invalid Russell 2000 URL: {error_msg}")
                    continue

                try:
                    from io import StringIO

                    import pandas as pd

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
                            logger.info(
                                f"Fetched {len(symbols)} Russell 2000 constituents"
                            )
                            return [
                                {
                                    "symbol": sym,
                                    "is_russell2000": True,
                                }
                                for sym in symbols
                            ]
                except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
                    logger.debug(f"URL {url} failed: {e}")
                    continue

            logger.error("Could not fetch Russell 2000 constituents from any source")
            raise RuntimeError("Failed to fetch Russell 2000 constituents: all data sources exhausted")

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e



if __name__ == "__main__":
    sys.exit(run_loader(Russell2000ConstituentsLoader, global_mode=True))
