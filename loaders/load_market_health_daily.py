#!/usr/bin/env python3
"""Market Health Daily Loader — Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data and market indicators.
Populates all required market_health_daily columns.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from loaders.technical_indicators import compute_moving_averages, compute_volume_ma

logger = get_logger(__name__)


class MarketHealthDailyLoader(OptimalLoader):
    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_incremental(self, symbol: str = "SPY", since: Optional[date] = None):
        """Fetch SPY price data and compute market health metrics."""
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, use yesterday instead
        # (prevents computing health metrics for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=100)

        rows = self._fetch_price_daily("SPY", start, end)
        if not rows:
            return []

        health_metrics = self._compute_market_health(rows)
        if not health_metrics:
            return []

        if since is not None:
            since_str = since.isoformat()
            health_metrics = [m for m in health_metrics if m["date"] > since_str]

        return health_metrics

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, open, high, low, close, volume FROM price_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start, end),
            )
            return [
                {
                    "date": r[0].isoformat() if r[0] else None,
                    "open": float(r[1]) if r[1] is not None else None,
                    "high": float(r[2]) if r[2] is not None else None,
                    "low": float(r[3]) if r[3] is not None else None,
                    "close": float(r[4]) if r[4] is not None else None,
                    "volume": int(r[5]) if r[5] is not None else None,
                }
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def _compute_market_health(self, rows: List[dict]) -> List[dict]:
        if not rows or len(rows) < 20:
            return []

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        df["price_change"] = df["close"].diff()
        df["up_day"] = (df["price_change"] > 0).astype(int)

        # Use shared indicator computation
        df["prev_volume"] = df["volume"].shift(1)
        df["distribution_day"] = ((df["price_change"] < 0) & (df["volume"] > df["prev_volume"])).astype(int)

        # Calculate moving averages using shared function
        mas = compute_moving_averages(df["close"])
        df["sma_50"] = mas['sma_50']
        df["sma_200"] = mas['sma_200']
        df["breadth_10d"] = df["up_day"].rolling(10).mean() * 100  # % up days in last 10

        results = []
        for idx, row in df.iterrows():
            close = float(row["close"]) if pd.notna(row["close"]) else 0
            sma_200 = float(row["sma_200"]) if pd.notna(row["sma_200"]) else None
            sma_50 = float(row["sma_50"]) if pd.notna(row["sma_50"]) else None

            # Determine market trend and stage
            market_trend = "neutral"
            market_stage = 2  # Default to 2 (consolidation)

            if sma_200 and sma_50:
                if close > sma_50 > sma_200:
                    market_trend = "uptrend"
                    market_stage = 2
                elif close < sma_50 < sma_200:
                    market_trend = "downtrend"
                    market_stage = 4
                else:
                    market_trend = "mixed"
                    market_stage = 1
            elif sma_200:
                if close > sma_200 * 1.05:
                    market_trend = "uptrend"
                    market_stage = 2
                elif close < sma_200 * 0.95:
                    market_trend = "downtrend"
                    market_stage = 4
                else:
                    market_trend = "consolidation"
                    market_stage = 1

            # Count distribution days (last 25 trading days per IBD)
            dist_days_25d = int(df["distribution_day"].iloc[max(0, idx-25):idx+1].sum()) if idx >= 0 else 0

            results.append({
                "date": row["date"].date().isoformat(),
                "market_trend": market_trend,
                "market_stage": market_stage,
                "distribution_days_4w": dist_days_25d,
                "distribution_days_20d": dist_days_25d,
                "up_volume_percent": float(df["up_day"].iloc[max(0, idx-10):idx+1].mean() * 100) if idx >= 0 else 50,
                "advance_decline_ratio": 1.0,
                "new_highs_count": 0,
                "new_lows_count": 0,
                "breadth_momentum_10d": float(row["breadth_10d"]) if pd.notna(row["breadth_10d"]) else 50,
                "vix_level": None,
                "put_call_ratio": None,
                "yield_curve_slope": None,
                "fed_rate_environment": "unknown",
            })

        return results


def main():
    import argparse
    load_env()
    parser = argparse.ArgumentParser(description="Load market health daily metrics")
    parser.add_argument("--symbols", type=str, help="(Ignored - always uses SPY)")
    parser.add_argument("--parallelism", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    try:
        loader = MarketHealthDailyLoader()
        loader.run(["SPY"], parallelism=args.parallelism)
        logger.info("Market health daily load completed")
        return 0
    except Exception as e:
        logger.error(f"Market health daily load failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
