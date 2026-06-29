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

        Returns list of analyst upgrade/downgrade records. If no data is available or all records
        are invalid, returns a list containing one dict with data_unavailable marker.
        All returned valid records must have complete analyst rating data (Firm, To Grade, Action).

        Raises:
            TransientAPIError: On timeouts/connection errors (orchestrator will retry with backoff)
            RuntimeError: If yfinance returns unexpected data structure (API format change, corrupted data)

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
            logger.warning(
                f"[ANALYST_RATINGS] Timeout fetching upgrades/downgrades for {symbol} (transient, will retry): {e}"
            )
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
            logger.info(f"[ANALYST_RATINGS] No upgrade/downgrade history for {symbol} — data unavailable")
            # Return explicit marker instead of empty list (which looks like "no ratings found")
            return [
                {"symbol": symbol, "data_unavailable": True, "reason": "No analyst upgrade/downgrade history available"}
            ]

        results = []

        # Handle yfinance column naming variations (old: "To Grade", new: "ToGrade")
        to_grade_col = None
        from_grade_col = None
        for col in upgrades_downgrades.columns:
            if col.lower() == "tograde" or col == "To Grade":
                to_grade_col = col
            if col.lower() == "fromgrade" or col == "From Grade":
                from_grade_col = col

        if not to_grade_col:
            raise ValueError(
                f"[ANALYST_RATINGS] Could not find 'ToGrade'/'To Grade' column for {symbol}. "
                f"Available columns: {list(upgrades_downgrades.columns)}. "
                "yfinance API response format may have changed."
            )

        for idx, row in upgrades_downgrades.iterrows():
            ud_date = idx.date() if hasattr(idx, "date") else idx
            # Validate required fields (use actual column names from API)
            # .get() is safe here: yfinance column names vary, None means field doesn't exist in this record
            firm = row.get("Firm")
            to_grade = row.get(to_grade_col)
            action = row.get("Action")

            if not firm or (isinstance(firm, float) and pd.isna(firm)):
                logger.warning(f"[ANALYST_RATINGS] Missing Firm for {symbol} on {ud_date}, skipping record")
                continue
            if not to_grade or (isinstance(to_grade, float) and pd.isna(to_grade)):
                logger.warning(f"[ANALYST_RATINGS] Missing {to_grade_col} for {symbol} on {ud_date}, skipping record")
                continue
            if not action or (isinstance(action, float) and pd.isna(action)):
                logger.warning(f"[ANALYST_RATINGS] Missing Action for {symbol} on {ud_date}, skipping record")
                continue

            # old_rating is optional (older records may not have FromGrade), safe to use .get()
            old_rating_raw = row.get(from_grade_col) if from_grade_col else None
            old_rating_str = str(old_rating_raw).strip() if old_rating_raw else None
            results.append(
                {
                    "symbol": symbol,
                    "action_date": ud_date,
                    "firm": str(firm).strip(),
                    "new_rating": str(to_grade).strip(),
                    "old_rating": old_rating_str,
                    "action": str(action).strip(),
                }
            )

        # If all records were skipped due to validation failures, return explicit marker
        if not results:
            logger.warning(f"[ANALYST_RATINGS] All records skipped for {symbol} (all records missing required fields)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "All analyst upgrade/downgrade records missing required fields (Firm, Rating, Action)",
                }
            ]

        return results

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystRatingsLoader))
