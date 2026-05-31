#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
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

import argparse
import logging
logger = logging.getLogger(__name__)
from utils.loader_helpers import get_active_symbols
import os
from datetime import date, timedelta
from typing import List, Optional

from utils.optimal_loader import OptimalLoader

class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch analyst recommendations from yfinance and aggregate into sentiment."""
        try:
            from utils.yfinance_wrapper import get_ticker
        except ImportError:
            return None

        ticker = get_ticker(symbol)
        if not ticker:
            return None

        try:
            recs = ticker.recommendations

            if recs is None or recs.empty:
                return None

            # Group by date and aggregate sentiment counts
            sentiment_by_date = {}
            for idx, row in recs.iterrows():
                rec_date = idx.date() if hasattr(idx, 'date') else idx
                rating = row.get('To Grade', '').lower()

                if rec_date not in sentiment_by_date:
                    sentiment_by_date[rec_date] = {
                        'bullish': 0, 'bearish': 0, 'neutral': 0, 'total': 0
                    }

                # Categorize rating
                if rating in ['buy', 'overweight', 'outperform', 'strong buy']:
                    sentiment_by_date[rec_date]['bullish'] += 1
                elif rating in ['sell', 'underweight', 'underperform', 'strong sell']:
                    sentiment_by_date[rec_date]['bearish'] += 1
                elif rating in ['hold', 'equal weight', 'neutral']:
                    sentiment_by_date[rec_date]['neutral'] += 1

                sentiment_by_date[rec_date]['total'] += 1

            # Convert to result format
            results = []
            for rec_date, counts in sentiment_by_date.items():
                results.append({
                    'symbol': symbol,
                    'date': rec_date,
                    'analyst_count': counts['total'],
                    'bullish_count': counts['bullish'],
                    'bearish_count': counts['bearish'],
                    'neutral_count': counts['neutral'],
                    'target_price': None,
                    'current_price': None,
                    'upside_downside_percent': None
                })

            return results if results else None
        except Exception as e:
            logger.warning(f"Exception: {e}")
            # Any error - skip this symbol gracefully
            return None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row)

def main():
    parser = argparse.ArgumentParser(description="Optimal analyst_sentiment loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols(timeout_secs=60)

    loader = AnalystSentimentLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

