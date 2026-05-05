#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Monthly Buy/Sell Signals Loader - Optimal Pattern.

Computes buy/sell signals from monthly aggregated price_daily data.
Inherits watermarks, dedup, parallelism, and bulk COPY from OptimalLoader.

Run:
    python3 loadbuysellmonthly.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


class BuySellMonthlyLoader(OptimalLoader):
    table_name = "buy_sell_monthly"
    primary_key = ("symbol", "timeframe", "date")
    watermark_field = "date"
    timeframe_value = "Monthly"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        if since is None:
            start = end - timedelta(days=10 * 365)
        else:
            start = since - timedelta(days=800)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            return None

        signals = self._compute_monthly_signals(symbol, rows)
        if not signals:
            return None

        if since is not None:
            since_str = since.isoformat()
            signals = [s for s in signals if s["date"] > since_str]

        return signals or None

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s AND date >= %s AND date <= %s
                ORDER BY date ASC
                """,
                (symbol, start, end),
            )
            rows = cur.fetchall()
            return [
                {
                    "date": r[0].isoformat() if r[0] else None,
                    "open": float(r[1]) if r[1] is not None else None,
                    "high": float(r[2]) if r[2] is not None else None,
                    "low": float(r[3]) if r[3] is not None else None,
                    "close": float(r[4]) if r[4] is not None else None,
                    "volume": int(r[5]) if r[5] is not None else None,
                }
                for r in rows
            ]
        finally:
            cur.close()

    def _compute_monthly_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        if len(price_rows) < 100:
            return None

        try:
            import pandas as pd
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low", "date"]):
            return None

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"])

        monthly = df.set_index("date").resample("MS").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["close"])

        if len(monthly) < 12:
            return None

        monthly["rsi"] = self._compute_rsi(monthly["close"], 14)
        macd, signal_line = self._compute_macd(monthly["close"])
        monthly["macd"] = macd
        monthly["signal_line"] = signal_line

        signals = []
        for idx, row in monthly.iterrows():
            sig = self._generate_signal_row(row, symbol, idx.date(), pd)
            if sig:
                signals.append(sig)

        return signals if signals else None

    @staticmethod
    def _compute_rsi(closes, period=14):
        deltas = closes.diff()
        gains = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        rs = gains / losses
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _compute_macd(closes, fast=12, slow=26, signal=9):
        ema_fast = closes.ewm(span=fast).mean()
        ema_slow = closes.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line

    def _generate_signal_row(self, row, symbol: str, idx_date, pd):
        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal_line):
            return None

        signal_str = None
        if rsi < 30 and macd > signal_line:
            signal_str = "BUY"
        elif rsi > 70 and macd < signal_line:
            signal_str = "SELL"
        if not signal_str:
            return None

        def _f(v):
            return float(v) if v is not None and not pd.isna(v) else None

        return {
            "symbol": symbol,
            "timeframe": self.timeframe_value,
            "date": idx_date.isoformat(),
            "open": _f(row.get("open")),
            "high": _f(row.get("high")),
            "low": _f(row.get("low")),
            "close": _f(row.get("close")),
            "volume": int(row["volume"]) if row.get("volume") is not None and not pd.isna(row.get("volume")) else None,
            "signal": signal_str,
            "signal_type": signal_str.capitalize(),
            "rsi": _f(rsi),
        }

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")


def get_active_symbols() -> List[str]:
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
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal buy_sell_monthly loader")
    parser.add_argument("--symbols", help="Comma-separated symbols.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = BuySellMonthlyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
