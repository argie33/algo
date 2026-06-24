#!/usr/bin/env python3

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Analyst Sentiment Loader - Analyst Recommendation Sentiment

ROLE IN SENTIMENT PIPELINE:
  1. [SEPARATE SENTIMENT SOURCE] Fetches analyst recommendations (Buy/Hold/Sell)
     - Reads from: yfinance API
     - Writes to: analyst_sentiment_analysis table (per-symbol analyst sentiment)
     - Does NOT conflict with AAII sentiment (different data source)

PRIORITY HIERARCHY:
  - Independent source: Does NOT depend on load_aaii_sentiment.py
  - Used by: Separate analyst sentiment scoring system
  - Data separation: analyst_sentiment_analysis ≠ sentiment (AAII)
  - Conflicts: None (dedicated analyst data source)

DATA SOURCE:
  - yfinance API: Analyst recommendations (buy/hold/sell counts)
  - Per-symbol: Analyst consensus and recommendations

TABLES:
  - analyst_sentiment_analysis: Per-symbol analyst sentiment and recommendations

DISTINCTIONS FROM AAII SENTIMENT:
  - AAII: Market-wide investor sentiment (bullish/neutral/bearish %)
  - Analyst: Per-stock analyst recommendations (buy/hold/sell ratings)
  - Usage: Different signal sources, no conflicts

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadanalystsentiment.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date
from typing import Any

import requests

from loaders.runner import run_loader
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch analyst recommendations from yfinance and aggregate into sentiment."""
        try:
            from utils.external.yfinance import get_ticker
        except ImportError as e:
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] Failed to import yfinance module: {e}. "
                "Cannot fetch analyst sentiment without yfinance API."
            ) from e

        ticker = get_ticker(symbol)
        if not ticker:
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] Failed to fetch ticker for {symbol}. "
                "Cannot retrieve analyst sentiment without valid ticker."
            )

        try:
            recs = ticker.recommendations

            if recs is None or recs.empty:
                raise RuntimeError(
                    f"[ANALYST_SENTIMENT] No analyst recommendations available for {symbol}. "
                    "Cannot assess analyst sentiment without recommendation data."
                )

            # Group by date and aggregate sentiment counts
            sentiment_by_date: dict[Any, dict[str, int]] = {}
            for idx, row in recs.iterrows():
                rec_date = idx.date() if hasattr(idx, "date") else idx
                rating = row.get("To Grade", "").lower()

                if rec_date not in sentiment_by_date:
                    sentiment_by_date[rec_date] = {
                        "bullish": 0,
                        "bearish": 0,
                        "neutral": 0,
                        "total": 0,
                    }

                # Categorize rating
                if rating in ["buy", "overweight", "outperform", "strong buy"]:
                    sentiment_by_date[rec_date]["bullish"] += 1
                elif rating in ["sell", "underweight", "underperform", "strong sell"]:
                    sentiment_by_date[rec_date]["bearish"] += 1
                elif rating in ["hold", "equal weight", "neutral"]:
                    sentiment_by_date[rec_date]["neutral"] += 1

                sentiment_by_date[rec_date]["total"] += 1

            # Convert to result format
            results: list[dict[str, Any]] = []
            for rec_date, counts in sentiment_by_date.items():
                results.append(
                    {
                        "symbol": symbol,
                        "date": rec_date,
                        "analyst_count": counts["total"],
                        "bullish_count": counts["bullish"],
                        "bearish_count": counts["bearish"],
                        "neutral_count": counts["neutral"],
                        "target_price": None,
                        "current_price": None,
                        "upside_downside_percent": None,
                    }
                )

            if not results:
                raise RuntimeError(
                    f"[ANALYST_SENTIMENT] No analyst sentiment data found for {symbol}. "
                    "Cannot load analyst sentiment without recommendations."
                )
            return results
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] HTTP error fetching sentiment for {symbol}: {e}. "
                "Cannot generate signals without sentiment data."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] Failed to fetch sentiment for {symbol}: {e}. "
                "Cannot generate signals without sentiment data."
            ) from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystSentimentLoader))
