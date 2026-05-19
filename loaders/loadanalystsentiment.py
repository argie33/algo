#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Analyst Sentiment Loader.

Aggregates recent analyst recommendations from yfinance into sentiment counts
(bullish/neutral/bearish) and stores in analyst_sentiment_analysis table.

Complements loadanalystupgradedowngrade.py (which stores individual actions).
This loader computes aggregate sentiment scores for the algo filter pipeline.

Run:
    python3 loadanalystsentiment.py [--parallelism 8]
"""

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

# Grade → sentiment bucket
_BULLISH_GRADES = {
    "strong buy", "buy", "outperform", "overweight", "accumulate",
    "positive", "add", "market outperform", "sector outperform",
    "top pick", "conviction buy",
}
_BEARISH_GRADES = {
    "sell", "strong sell", "underperform", "underweight", "reduce",
    "negative", "market underperform", "sector underperform",
}
# Everything else = neutral (hold, neutral, market perform, in-line, etc.)


def _classify_grade(grade: str) -> str:
    g = str(grade or "").lower().strip()
    if g in _BULLISH_GRADES:
        return "bullish"
    if g in _BEARISH_GRADES:
        return "bearish"
    return "neutral"


class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Aggregate analyst recommendations into sentiment buckets."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            recs = ticker.recommendations
        except Exception as e:
            log.debug("recommendations failed for %s: %s", symbol, e)
            return None

        if recs is None or (hasattr(recs, 'empty') and recs.empty):
            return None

        today = date.today()
        lookback_start = today - timedelta(days=365)

        # Filter to recent recommendations
        counts = {"bullish": 0, "neutral": 0, "bearish": 0}
        try:
            for idx, row in recs.iterrows():
                try:
                    rec_date = idx.date() if hasattr(idx, 'date') else date.fromisoformat(str(idx)[:10])
                    if rec_date < lookback_start:
                        continue
                    grade = row.get("To Grade") or row.get("toGrade") or ""
                    bucket = _classify_grade(grade)
                    counts[bucket] += 1
                except Exception:
                    continue
        except Exception as e:
            log.debug("recommendations iteration error for %s: %s", symbol, e)
            return None

        total = sum(counts.values())
        if total == 0:
            return None

        # Get current price for upside calculation
        try:
            info = ticker.fast_info
            current_price = float(info.last_price) if info.last_price else None
            target_price = float(ticker.analyst_price_targets.mean) if hasattr(ticker, 'analyst_price_targets') else None
        except Exception:
            current_price = None
            target_price = None

        upside = None
        if target_price and current_price and current_price > 0:
            upside = round((target_price - current_price) / current_price * 100, 2)

        return [{
            "symbol": symbol,
            "date": str(today),
            "analyst_count": total,
            "bullish_count": counts["bullish"],
            "bearish_count": counts["bearish"],
            "neutral_count": counts["neutral"],
            "target_price": target_price,
            "current_price": current_price,
            "upside_downside_percent": upside,
        }]


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = get_active_symbols()
    loader = AnalystSentimentLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    log.info("Analyst sentiment load complete: %s", stats)
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
