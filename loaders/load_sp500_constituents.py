#!/usr/bin/env python3
"""S&P 500 Constituents Loader - Mark S&P 500 membership (Market-wide)."""

import json
import logging
import socket
import sys
from datetime import date
from io import StringIO
from typing import List, Optional

import pandas as pd
import requests

from loaders.runner import run_loader
from utils.infrastructure.timeout import ExecutionTimeout
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class SP500ConstituentsLoader(OptimalLoader):
    """Load and mark S&P 500 constituent symbols."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch S&P 500 symbols from Wikipedia with timeout protection."""
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(15.0)

        # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
        is_valid, error_msg = validate_url(SP500_URL, allowed_domains=["wikipedia.org"])
        if not is_valid:
            raise RuntimeError(f"SSRF prevention: Invalid S&P 500 URL: {error_msg}")

        try:
            logger.info("Fetching S&P 500 constituents from Wikipedia")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            try:
                response = requests.get(SP500_URL, headers=headers, timeout=15)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                raise RuntimeError(
                    "S&P 500 fetch timeout. Wikipedia API is unreachable or slow. "
                    "Cannot load S&P 500 constituent list."
                )
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    "S&P 500 connection error. Cannot reach Wikipedia. "
                    "Cannot load S&P 500 constituent list."
                )

            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError(
                    "Could not find S&P 500 table in Wikipedia response. "
                    "Wikipedia page format may have changed."
                )

            df = tables[0]
            col = "Symbol" if "Symbol" in df.columns else "Ticker"
            symbols = df[col].str.strip().tolist()

            logger.info(f"Fetched {len(symbols)} S&P 500 constituents")

            # Return rows with is_sp500 flag set to true
            return [
                {
                    "symbol": sym,
                    "is_sp500": True,
                }
                for sym in symbols
            ]

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e



if __name__ == "__main__":
    sys.exit(run_loader(SP500ConstituentsLoader, global_mode=True))
