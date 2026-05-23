#!/usr/bin/env python3
"""Analyst Sentiment Loader — aggregates analyst ratings and target prices from yfinance.

Table: analyst_sentiment_analysis
Primary key: (symbol, date)

Run: python3 loaders/loadanalystsentiment.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from utils.yfinance_wrapper import get_ticker

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

# Rating strings → sentiment bucket
BULLISH_RATINGS = {"buy", "strong buy", "outperform", "overweight", "accumulate", "positive"}
BEARISH_RATINGS = {"sell", "strong sell", "underperform", "underweight", "reduce", "negative"}

def _classify(rating: str) -> str:
    r = str(rating).lower().strip()
    if any(b in r for b in BULLISH_RATINGS):
        return "bullish"
    if any(b in r for b in BEARISH_RATINGS):
        return "bearish"
    return "neutral"

class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        try:
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)

            # Get recent recommendations
            recs = ticker.recommendations
            if recs is None or (hasattr(recs, "empty") and recs.empty):
                return None

            # Get price targets
            target_price = None
            try:
                pt = ticker.analyst_price_targets
                if pt is not None and hasattr(pt, "mean"):
                    target_price = float(pt["mean"]) if "mean" in pt else None
                elif isinstance(pt, dict):
                    target_price = float(pt.get("mean", 0)) or None
            except Exception:
                pass

            # Current price
            current_price = None
            try:
                info = ticker.fast_info
                current_price = float(info.last_price) if hasattr(info, "last_price") else None
            except Exception:
                pass

            # Count recent ratings (last 90 days)
            cutoff = date.today() - timedelta(days=90)
            bullish = bearish = neutral = 0
            if hasattr(recs, "iterrows"):
                for idx, row in recs.iterrows():
                    try:
                        rec_date = idx.date() if hasattr(idx, "date") else None
                        if rec_date and rec_date < cutoff:
                            continue
                        grade = str(row.get("To Grade") or row.get("toGrade") or row.get(recs.columns[0]) or "")
                        sentiment = _classify(grade)
                        if sentiment == "bullish":
                            bullish += 1
                        elif sentiment == "bearish":
                            bearish += 1
                        else:
                            neutral += 1
                    except Exception:
                        continue

            total = bullish + bearish + neutral
            if total == 0:
                return None

            upside = None
            if target_price and current_price and current_price > 0:
                upside = round((target_price - current_price) / current_price * 100, 2)

            today = date.today().isoformat()
            if since and today <= since.isoformat():
                return None

            return [{
                "symbol": symbol,
                "date": today,
                "analyst_count": total,
                "bullish_count": bullish,
                "bearish_count": bearish,
                "neutral_count": neutral,
                "target_price": round(target_price, 2) if target_price else None,
                "current_price": round(current_price, 2) if current_price else None,
                "upside_downside_percent": upside,
            }]

        except Exception as e:
            log.debug("Analyst sentiment error for %s: %s", symbol, e)
            return None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return row.get("analyst_count", 0) > 0

def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = AnalystSentimentLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0

if __name__ == "__main__":
    sys.exit(main())
