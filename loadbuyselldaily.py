#!/usr/bin/env python3
"""
Daily Buy/Sell Signals Loader - Optimal Pattern.

Computes buy/sell trading signals from price data using technical indicators.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Performance: Parallel execution with 4-8 workers provides 4-8x speedup.

Run:
    python3 loadbuyselldaily.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd
import numpy as np

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class BuySellDailyLoader(OptimalLoader):
    table_name = "buy_sell_daily"
    primary_key = ("symbol", "timeframe", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price data and compute signals."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return None

        rows = self.router.fetch_ohlcv(symbol, start, end)
        if not rows:
            return None

        return self._compute_signals(symbol, rows)

    def _compute_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        """Compute buy/sell signals from price data using technical indicators."""
        if len(price_rows) < 20:
            return None

        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low"]):
            return None

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df = df.dropna(subset=["close"])

        if len(df) < 20:
            return None

        df["rsi"] = self._compute_rsi(df["close"], 14)
        df["macd"], df["signal_line"] = self._compute_macd(df["close"])
        df["atr"] = self._compute_atr(df["high"], df["low"], df["close"], 14)

        signals = []
        for idx, row in df.iterrows():
            if pd.isna(row.get("rsi")) or pd.isna(row.get("macd")):
                continue

            signal = self._generate_signal(row, symbol)
            if signal:
                signals.append(signal)

        return signals if signals else None

    @staticmethod
    def _compute_rsi(closes, period=14):
        """Compute Relative Strength Index."""
        deltas = closes.diff()
        gains = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def _compute_macd(closes, fast=12, slow=26, signal=9):
        """Compute MACD."""
        ema_fast = closes.ewm(span=fast).mean()
        ema_slow = closes.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line

    @staticmethod
    def _compute_atr(highs, lows, closes, period=14):
        """Compute Average True Range."""
        tr1 = highs - lows
        tr2 = (highs - closes.shift()).abs()
        tr3 = (lows - closes.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    @staticmethod
    def _generate_signal(row, symbol: str):
        """Generate buy/sell signal from indicators."""
        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")
        date_val = row.get("date")

        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal_line):
            return None

        signal_type = None
        if rsi < 30 and macd > signal_line:
            signal_type = "BUY"
        elif rsi > 70 and macd < signal_line:
            signal_type = "SELL"

        if signal_type:
            # Map to actual buy_sell_daily schema. The table uses 'signal' (BUY/SELL)
            # in addition to 'signal_type'. We don't have 'macd'/'signal_line' columns
            # — those are intermediate computations. Persist what the table accepts.
            close = row.get("close")
            return {
                "symbol": symbol,
                "date": date_val if isinstance(date_val, str) else str(date_val),
                "signal": signal_type,
                "signal_type": "buy_signal" if signal_type == "BUY" else "sell_signal",
                "timeframe": "daily",
                "close": float(close) if close is not None and not pd.isna(close) else None,
                "open": float(row.get("open")) if row.get("open") is not None and not pd.isna(row.get("open")) else None,
                "high": float(row.get("high")) if row.get("high") is not None and not pd.isna(row.get("high")) else None,
                "low": float(row.get("low")) if row.get("low") is not None and not pd.isna(row.get("low")) else None,
                "volume": int(row.get("volume")) if row.get("volume") is not None and not pd.isna(row.get("volume")) else None,
                "rsi": float(rsi) if not pd.isna(rsi) else None,
                "atr": float(row.get("atr")) if row.get("atr") is not None and not pd.isna(row.get("atr")) else None,
            }
        return None

    def transform(self, rows):
        """Signals are already clean from compute stage."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate signal row."""
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stocks ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal buy_sell_daily loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers (compute-intensive)")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = BuySellDailyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
