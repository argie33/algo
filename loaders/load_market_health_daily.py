#!/usr/bin/env python3
"""Market Health Daily Loader — Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data.
Required by Phase 1 data freshness check.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class MarketHealthDailyLoader(OptimalLoader):
    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_incremental(self, symbol: str = "SPY", since: Optional[date] = None):
        """Fetch SPY price data and compute market health metrics."""
        end = date.today()
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
        df["distribution_day"] = ((df["up_day"] == 0) & (df["volume"] > df["volume"].rolling(50).mean())).astype(int)

        results = []
        for idx, row in df.iterrows():
            close = float(row["close"]) if pd.notna(row["close"]) else 0
            sma_200 = float(df["close"].iloc[:idx+1].rolling(200).mean().iloc[-1]) if idx >= 199 else None

            market_stage = "unknown"
            if sma_200 and close > sma_200 * 1.05:
                market_stage = "uptrend"
            elif sma_200 and close < sma_200 * 0.95:
                market_stage = "downtrend"
            else:
                market_stage = "consolidation"

            results.append({
                "date": row["date"].date().isoformat(),
                "market_stage": market_stage,
                "distribution_days": int(df["distribution_day"].iloc[:idx+1].sum()),
                "close": float(row["close"]) if pd.notna(row["close"]) else None,
                "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
            })

        return results


if __name__ == "__main__":
    load_env()
    loader = MarketHealthDailyLoader()
    loader.run(["SPY"], parallelism=1)
