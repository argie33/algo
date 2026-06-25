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
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AnalystRatingsLoader(OptimalLoader):
    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch analyst upgrades/downgrades from yfinance."""
        try:
            from utils.external.yfinance import get_ticker
        except ImportError as e:
            raise RuntimeError(
                f"[ANALYST] Failed to import yfinance module: {e}. Cannot fetch analyst rating data without yfinance."
            ) from e

        ticker = get_ticker(symbol)
        if not ticker:
            raise RuntimeError(
                f"[ANALYST] Failed to fetch ticker data for {symbol}. "
                "Cannot fetch analyst ratings without valid ticker."
            )

        try:
            upgrades_downgrades = ticker.upgrades_downgrades

            if upgrades_downgrades is None or upgrades_downgrades.empty:
                raise RuntimeError(
                    f"[ANALYST_RATINGS] No analyst upgrade/downgrade data available for {symbol}. "
                    "Cannot assess analyst actions without rating changes."
                )

            results = []
            for idx, row in upgrades_downgrades.iterrows():
                ud_date = idx.date() if hasattr(idx, "date") else idx
                # Fail-fast if critical analyst rating fields missing
                for field in ["Firm", "To Grade", "Action"]:
                    if field not in row or (isinstance(row[field], float) and pd.isna(row[field])):
                        raise ValueError(
                            f"Analyst upgrade/downgrade record for {symbol} missing required field '{field}' - "
                            f"cannot proceed without complete analyst data"
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
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(
                f"[ANALYST_RATINGS] HTTP error fetching ratings for {symbol}: {e}. "
                "Cannot generate signals without analyst data."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[ANALYST_RATINGS] Failed to fetch ratings for {symbol}: {e}. "
                "Cannot generate signals without analyst data."
            ) from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystRatingsLoader))
