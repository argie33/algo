#!/usr/bin/env python3

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Analyst Ratings Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadanalystupgradedowngrade.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date
from typing import Any

import pandas as pd
import requests

from loaders.runner import run_loader
from utils.loaders.transient_errors import TransientAPIError
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AnalystRatingsLoader(OptimalLoader):
    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch analyst upgrades/downgrades from yfinance.

        Returns empty list (not None) if analyst rating history is unavailable.
        All returned records must have complete analyst rating data (Firm, To Grade, Action).

        Raises:
            TransientAPIError: On timeouts/connection errors (orchestrator will retry with backoff)
            ValueError: If a record is missing required analyst rating field (indicates data format change)

        Analyst upgrades/downgrades are optional enrichment; their absence does not prevent trading.
        """
        try:
            from utils.external.yfinance import get_ticker
        except ImportError as e:
            logger.debug(f"[ANALYST] Failed to import yfinance for {symbol}: {e}")
            raise

        try:
            ticker = get_ticker(symbol)
        except requests.Timeout as e:
            logger.warning(f"[ANALYST] Timeout fetching ticker for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching ticker for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching ticker for {symbol}") from e

        if not ticker:
            raise RuntimeError(
                f"[ANALYST_RATINGS] Ticker not found for {symbol}. "
                "yfinance returned None for ticker symbol. Cannot fetch analyst upgrade/downgrade data. "
                "Check symbol validity and yfinance API connectivity."
            )

        try:
            upgrades_downgrades = ticker.upgrades_downgrades
        except requests.Timeout as e:
            logger.warning(f"[ANALYST_RATINGS] Timeout fetching upgrades/downgrades for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching upgrades/downgrades for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST_RATINGS] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching upgrades/downgrades for {symbol}") from e

        if upgrades_downgrades is None:
            raise RuntimeError(
                f"[ANALYST_RATINGS] yfinance returned None for upgrades_downgrades on {symbol}. "
                "API call succeeded but returned invalid data structure. "
                "API format may have changed or ticker data is corrupted."
            )
        if upgrades_downgrades.empty:
            logger.info(f"[ANALYST_RATINGS] No upgrade/downgrade history for {symbol} — optional enrichment unavailable")
            return []

        results = []
        for idx, row in upgrades_downgrades.iterrows():
            ud_date = idx.date() if hasattr(idx, "date") else idx
            # CRITICAL: Validate all required analyst rating fields
            for field in ["Firm", "To Grade", "Action"]:
                if field not in row or (isinstance(row[field], float) and pd.isna(row[field])):
                    raise ValueError(
                        f"[ANALYST_RATINGS] Missing or invalid '{field}' field for {symbol} on {ud_date}. "
                        "yfinance API response format may have changed. Cannot parse analyst upgrade/downgrade without all required fields."
                    )
            old_rating_raw = row.get("From Grade")
            old_rating_str = str(old_rating_raw).strip() if old_rating_raw else None
            results.append(
                {
                    "symbol": symbol,
                    "action_date": ud_date,
                    "firm": str(row["Firm"]).strip(),
                    "new_rating": str(row["To Grade"]).strip(),
                    "old_rating": old_rating_str,
                    "action": str(row["Action"]).strip(),
                }
            )

        return results

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystRatingsLoader))
