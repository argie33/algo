#!/usr/bin/env python3
"""
ETF Weekly Buy/Sell Signals Loader - Optimal Pattern.

Computes buy/sell signals from weekly ETF price data.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadbuysell_etf_weekly.py [--symbols SPY,QQQ] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class BuySellETFWeeklyLoader(OptimalLoader):
    table_name = "buy_sell_etf_weekly"
    primary_key = ("symbol", "week_start")
    watermark_field = "week_start"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price data and compute weekly signals."""
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

        return self._compute_weekly_signals(symbol, rows)

    def _compute_weekly_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        """Aggregate to weekly and compute signals."""
        if len(price_rows) < 20:
            return None

        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low", "date"]):
            return None

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"])

        weekly = df.set_index("date").resample("W").agg({
            "close": "last",
            "high": "max",
            "low": "min",
            "open": "first",
        }).dropna()

        if len(weekly) < 10:
            return None

        weekly["rsi"] = self._compute_rsi(weekly["close"], 14)
        weekly["macd"], weekly["signal_line"] = self._compute_macd(weekly["close"])

        signals = []
        for idx, row in weekly.iterrows():
            if pd.isna(row.get("rsi")) or pd.isna(row.get("macd")):
                continue

            signal = self._generate_signal(row, symbol, idx.date())
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
    def _generate_signal(row, symbol: str, idx_date):
        """Generate buy/sell signal from weekly indicators."""
        import pandas as pd
        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")

        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal_line):
            return None

        signal_type = None
        if rsi < 30 and macd > signal_line:
            signal_type = "BUY"
        elif rsi > 70 and macd < signal_line:
            signal_type = "SELL"

        if signal_type:
            week_start = idx_date - timedelta(days=idx_date.weekday())
            return {
                "symbol": symbol,
                "week_start": week_start.isoformat(),
                "signal_type": signal_type,
                "rsi": float(rsi) if not pd.isna(rsi) else None,
                "macd": float(macd) if not pd.isna(macd) else None,
                "confidence": 0.5,
            }
        return None

    def transform(self, rows):
        """Signals are already clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate signal row."""
        if not super()._validate_row(row):
            return False
        return row.get("signal_type") in ("BUY", "SELL")


def get_active_etf_symbols() -> List[str]:
    """Pull active ETF symbols from database or use defaults."""
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "stocks"),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    except:
        return ["SPY", "QQQ", "IWM", "EEM", "EFA"]
    finally:
        try:
            conn.close()
        except:
            pass


def main():
    parser = argparse.ArgumentParser(description="Optimal buy_sell_etf_weekly loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs from database.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_etf_symbols()

    loader = BuySellETFWeeklyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
