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
from datetime import date, datetime
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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:  # noqa: C901
        """Fetch analyst recommendations from yfinance and aggregate into sentiment.

        DATA CONTRACT:
            - All records include: symbol, date, analyst_count, bullish_count, bearish_count, neutral_count
            - All records include: target_price, current_price, upside_downside_percent (may be None—yfinance doesn't provide)
            - All records include: data_unavailable (boolean, default False)
            - When data_unavailable=True, reason field explains why (e.g., "No coverage", "API error")
            - Target/current price fields intentionally NULL when no yfinance provider data available

        Returns list of records with data_unavailable flags set appropriately.
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
            logger.info(f"[ANALYST_SENTIMENT] Failed to import yfinance for {symbol}: {e}")
            raise

        try:
            ticker = get_ticker(symbol)
        except (TimeoutError, requests.Timeout) as e:
            logger.warning(f"[ANALYST_SENTIMENT] Timeout fetching ticker for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching ticker for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST_SENTIMENT] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching ticker for {symbol}") from e

        if not ticker:
            logger.info(f"[ANALYST_SENTIMENT] No ticker available for {symbol} — likely no analyst coverage")
            return [{
                "symbol": symbol,
                "date": date.today(),
                "analyst_count": None,
                "bullish_count": None,
                "bearish_count": None,
                "neutral_count": None,
                "target_price": None,
                "current_price": None,
                "upside_downside_percent": None,
                "data_unavailable": True,
                "reason": "No ticker available from yfinance (no analyst coverage or API issue)",
                "created_at": datetime.now().isoformat(),
            }]

        try:
            recs = ticker.recommendations
        except (TimeoutError, requests.Timeout) as e:
            logger.warning(f"[ANALYST_SENTIMENT] Timeout fetching recommendations for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching recommendations for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[ANALYST_SENTIMENT] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching recommendations for {symbol}") from e

        if recs is None or recs.empty:
            logger.info(f"[ANALYST_SENTIMENT] No analyst recommendations for {symbol} — no coverage available")
            return [{
                "symbol": symbol,
                "date": date.today(),
                "analyst_count": None,
                "bullish_count": None,
                "bearish_count": None,
                "neutral_count": None,
                "target_price": None,
                "current_price": None,
                "upside_downside_percent": None,
                "data_unavailable": True,
                "reason": "No analyst recommendations available (no coverage)",
                "created_at": datetime.now().isoformat(),
            }]

        # Handle two yfinance response formats:
        # 1. Old format: Individual recommendation rows with 'To Grade' field (indexed by date)
        # 2. New format: Aggregated counts (strongBuy, buy, hold, sell, strongSell columns)

        # Check for new format (aggregated counts)
        if all(col in recs.columns for col in ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']):
            # New yfinance API format: aggregated recommendation counts
            logger.debug(f"[ANALYST_SENTIMENT] Using new yfinance aggregated format for {symbol}")
            results: list[dict[str, Any]] = []

            for idx, row in recs.iterrows():
                # CRITICAL: Validate all required fields are present and numeric
                # Missing data indicates incomplete API response — skip rather than defaulting to 0
                required_fields = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                missing_fields = [f for f in required_fields if f not in row or row[f] is None]
                if missing_fields:
                    logger.warning(
                        f"[ANALYST_SENTIMENT] Skipping row for {symbol} (idx={idx}): "
                        f"missing required fields {missing_fields}. yfinance API returned incomplete data."
                    )
                    continue

                try:
                    strong_buy = int(row['strongBuy'])
                    buy = int(row['buy'])
                    hold = int(row['hold'])
                    sell = int(row['sell'])
                    strong_sell = int(row['strongSell'])
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"[ANALYST_SENTIMENT] Skipping row for {symbol} (idx={idx}): "
                        f"non-numeric values in recommendation counts: {e}. Data validation failed."
                    )
                    continue

                bullish_count = strong_buy + buy
                bearish_count = strong_sell + sell
                neutral_count = hold
                total = bullish_count + bearish_count + neutral_count

                if total == 0:
                    logger.info(f"[ANALYST_SENTIMENT] No analyst ratings found for {symbol}")
                    continue

                # Extract date from index or use the recommendation date if available
                row_date = idx if isinstance(idx, (datetime, date)) else date.today()
                if isinstance(row_date, datetime):
                    row_date = row_date.date()

                results.append({
                    "symbol": symbol,
                    "date": row_date,  # Use analyst data date (from yfinance index) not today's date
                    "analyst_count": total,
                    "bullish_count": bullish_count,
                    "bearish_count": bearish_count,
                    "neutral_count": neutral_count,
                    "target_price": None,  # yfinance aggregated format does not provide target price
                    "current_price": None,  # yfinance aggregated format does not provide current price
                    "upside_downside_percent": None,  # yfinance aggregated format does not provide upside/downside
                    "data_unavailable": False,
                })

            if results:
                logger.debug(f"[ANALYST_SENTIMENT] Parsed {len(results)} records for {symbol}")
                return results
            else:
                logger.info(f"[ANALYST_SENTIMENT] No sentiment data for {symbol}")
                return [{
                    "symbol": symbol,
                    "date": date.today(),
                    "analyst_count": None,
                    "bullish_count": None,
                    "bearish_count": None,
                    "neutral_count": None,
                    "target_price": None,
                    "current_price": None,
                    "upside_downside_percent": None,
                    "data_unavailable": True,
                    "reason": "No analyst sentiment records extracted from yfinance",
                    "created_at": datetime.now().isoformat(),
                }]

        elif "To Grade" in recs.columns:
            # Old yfinance API format: individual recommendation rows
            logger.debug(f"[ANALYST_SENTIMENT] Using old yfinance detailed format for {symbol}")
            sentiment_by_date: dict[Any, dict[str, int]] = {}
            for idx, row in recs.iterrows():
                rec_date = idx.date() if hasattr(idx, "date") else idx
                rating = str(row["To Grade"]).lower().strip()

                if not rating:
                    logger.warning(f"[ANALYST_SENTIMENT] Empty rating for {symbol} on {rec_date}, skipping")
                    continue

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

            results = [
                {
                    "symbol": symbol,
                    "date": rec_date,
                    "analyst_count": counts["total"],
                    "bullish_count": counts["bullish"],
                    "bearish_count": counts["bearish"],
                    "neutral_count": counts["neutral"],
                    "target_price": None,  # yfinance detailed format does not provide target price
                    "current_price": None,  # yfinance detailed format does not provide current price
                    "upside_downside_percent": None,  # yfinance detailed format does not provide upside/downside
                    "data_unavailable": False,
                }
                for rec_date, counts in sentiment_by_date.items()
            ]

            if results:
                return results
            else:
                logger.info(f"[ANALYST_SENTIMENT] No sentiment data aggregated for {symbol}")
                return [{
                    "symbol": symbol,
                    "date": date.today(),
                    "analyst_count": None,
                    "bullish_count": None,
                    "bearish_count": None,
                    "neutral_count": None,
                    "target_price": None,
                    "current_price": None,
                    "upside_downside_percent": None,
                    "data_unavailable": True,
                    "reason": "No analyst sentiment records aggregated from yfinance",
                    "created_at": datetime.now().isoformat(),
                }]
        else:
            # Unknown format
            logger.error(
                f"[ANALYST_SENTIMENT] yfinance response format unknown for {symbol}. "
                f"Expected 'To Grade' column (old format) or 'strongBuy'/'buy'/'hold'/'sell'/'strongSell' columns (new format). "
                f"Got columns: {list(recs.columns)}."
            )
            return [{
                "symbol": symbol,
                "date": date.today(),
                "analyst_count": None,
                "bullish_count": None,
                "bearish_count": None,
                "neutral_count": None,
                "target_price": None,
                "current_price": None,
                "upside_downside_percent": None,
                "data_unavailable": True,
                "reason": f"yfinance response format unknown. Got columns: {list(recs.columns)}",
                "created_at": datetime.now().isoformat(),
            }]

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(AnalystSentimentLoader))
