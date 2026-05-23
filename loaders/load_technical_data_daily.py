#!/usr/bin/env python3
"""Technical Data Daily Loader — RSI, MACD, SMA, EMA, ATR, Bollinger Bands.

Computes all technical indicators from daily price data and populates technical_data_daily.
Required by Phase 1 data freshness check.

Run: python3 load_technical_data_daily.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from loaders.technical_indicators import (
    compute_rsi, compute_macd, compute_moving_averages,
    compute_atr, compute_bollinger_bands, compute_volume_ma
)

logger = get_logger(__name__)


class TechnicalDataDailyLoader(OptimalLoader):
    table_name = "technical_data_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=300)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            return []

        indicators = self._compute_all_indicators(symbol, rows)
        if not indicators:
            return []

        if since is not None:
            since_str = since.isoformat()
            indicators = [ind for ind in indicators if ind["date"] > since_str]

        return indicators

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, open, high, low, close, volume FROM price_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start, end),
            )
            rows = []
            for r in cur.fetchall():
                # Validate: reject zero-price or zero-volume rows (data errors or halted stocks)
                close = float(r[4]) if r[4] is not None else None
                volume = int(r[5]) if r[5] is not None else None

                if close is None or close <= 0:
                    # Zero/negative close price = data error
                    continue
                if volume is not None and volume == 0:
                    # Zero volume = halted/no trading
                    continue

                rows.append({
                    "date": r[0].isoformat() if r[0] else None,
                    "open": float(r[1]) if r[1] is not None else None,
                    "high": float(r[2]) if r[2] is not None else None,
                    "low": float(r[3]) if r[3] is not None else None,
                    "close": close,
                    "volume": volume,
                })
            return rows
        finally:
            cur.close()

    def _compute_all_indicators(self, symbol: str, rows: List[dict]) -> List[dict]:
        if not rows or len(rows) < 50:
            return []

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Filter out identical OHLC rows (API-limit fallback/stale data)
        # These rows have open == high == low == close and indicate no real trading
        initial_len = len(df)
        df = df[~((df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"]))]
        if len(df) < initial_len:
            filtered_count = initial_len - len(df)
            logger.debug(f"[{symbol}] Filtered out {filtered_count} rows with identical OHLC (API-limit fallback data)")

        df["rsi_14"] = compute_rsi(df["close"], 14)
        df["macd"], df["macd_signal"] = compute_macd(df["close"])
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        mas = compute_moving_averages(df["close"])
        for name, values in mas.items():
            df[name] = values

        df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], 14)
        bbs = compute_bollinger_bands(df["close"], 20, 2.0)
        for name, values in bbs.items():
            df[name] = values

        df["volume_ma_50"] = compute_volume_ma(df["volume"], 50)

        results = []
        for _, row in df.iterrows():
            results.append({
                "symbol": symbol,
                "date": row["date"].date().isoformat(),
                "rsi": float(row["rsi_14"]) if pd.notna(row["rsi_14"]) else None,
                "macd": float(row["macd"]) if pd.notna(row["macd"]) else None,
                "macd_signal": float(row["macd_signal"]) if pd.notna(row["macd_signal"]) else None,
                "macd_histogram": float(row["macd_histogram"]) if pd.notna(row["macd_histogram"]) else None,
                "sma_20": float(row["sma_20"]) if pd.notna(row["sma_20"]) else None,
                "sma_50": float(row["sma_50"]) if pd.notna(row["sma_50"]) else None,
                "sma_150": float(row["sma_150"]) if pd.notna(row["sma_150"]) else None,
                "sma_200": float(row["sma_200"]) if pd.notna(row["sma_200"]) else None,
                "ema_12": float(row["ema_12"]) if pd.notna(row["ema_12"]) else None,
                "ema_21": float(row["ema_21"]) if pd.notna(row["ema_21"]) else None,
                "ema_26": float(row["ema_26"]) if pd.notna(row["ema_26"]) else None,
                "atr": float(row["atr_14"]) if pd.notna(row["atr_14"]) else None,
                "bb_upper": float(row["bb_upper"]) if pd.notna(row["bb_upper"]) else None,
                "bb_middle": float(row["bb_middle"]) if pd.notna(row["bb_middle"]) else None,
                "bb_lower": float(row["bb_lower"]) if pd.notna(row["bb_lower"]) else None,
                "volume_ma_50": float(row["volume_ma_50"]) if pd.notna(row["volume_ma_50"]) else None,
            })
        return results


if __name__ == "__main__":
    load_env()
    parser = argparse.ArgumentParser(description="Load technical indicators")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    symbols = (args.symbols.split(",") if args.symbols else get_active_symbols())
    loader = TechnicalDataDailyLoader()
    loader.run(symbols, parallelism=args.parallelism)
