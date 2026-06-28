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
import socket
import sys
from datetime import date
from typing import Any

import requests

from loaders.runner import run_loader
from utils.loaders.transient_errors import TransientAPIError
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Fetch analyst recommendations from yfinance and aggregate into sentiment.

        Returns None if analyst coverage is legitimately unavailable (common for smaller caps, international stocks).

        Raises:
            TransientAPIError: On timeouts/connection errors (orchestrator will retry with backoff)
            Exception: On unexpected errors (will be logged and handled by orchestrator)

        Analyst sentiment is optional enrichment; its absence does not prevent trading.
        """
        # Set short timeout to fail fast if yfinance is slow
        socket.setdefaulttimeout(10.0)

        try:
            from utils.external.yfinance import get_ticker
        except ImportError as e:
            logger.debug(f"[ANALYST_SENTIMENT] Failed to import yfinance for {symbol}: {e}")
            raise

        try:
            ticker = get_ticker(symbol)
        except (requests.Timeout, socket.timeout) as e:
            logger.warning(f"[ANALYST_SENTIMENT] Timeout fetching ticker for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching ticker for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST_SENTIMENT] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching ticker for {symbol}") from e

        if not ticker:
            logger.debug(f"[ANALYST_SENTIMENT] No ticker available for {symbol} — likely no analyst coverage")
            return {
                "data_unavailable": True,
                "reason": "no_ticker_found",
                "symbol": symbol
            }

        try:
            recs = ticker.recommendations
        except (requests.Timeout, socket.timeout) as e:
            logger.warning(f"[ANALYST_SENTIMENT] Timeout fetching recommendations for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching recommendations for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST_SENTIMENT] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching recommendations for {symbol}") from e

        if recs is None or recs.empty:
            logger.debug(f"[ANALYST_SENTIMENT] No analyst recommendations for {symbol} — no coverage available")
            return {
                "data_unavailable": True,
                "reason": "no_recommendations_available",
                "symbol": symbol
            }

        # Group by date and aggregate sentiment counts
        sentiment_by_date: dict[Any, dict[str, int]] = {}
        for idx, row in recs.iterrows():
            rec_date = idx.date() if hasattr(idx, "date") else idx

            # Explicit validation: To Grade must exist
            if "To Grade" not in row:
                raise ValueError(
                    f"[ANALYST_SENTIMENT] Missing 'To Grade' field for {symbol} on {rec_date}. "
                    "yfinance API response format may have changed. Cannot parse analyst sentiment without ratings."
                )

            rating = str(row["To Grade"]).lower().strip()
            if not rating:
                raise ValueError(
                    f"[ANALYST_SENTIMENT] Empty 'To Grade' rating for {symbol} on {rec_date}. "
                    "Cannot compute sentiment with missing rating data."
                )

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
            else:
                logger.warning(
                    f"[ANALYST_SENTIMENT] Unknown rating '{rating}' for {symbol} on {rec_date}. "
                    "Skipping unrecognized sentiment category."
                )

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
            logger.debug(f"[ANALYST_SENTIMENT] No sentiment data aggregated for {symbol}")
            return {
                "data_unavailable": True,
                "reason": "no_aggregated_sentiment_data",
                "symbol": symbol
            }

        return results

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystSentimentLoader))
