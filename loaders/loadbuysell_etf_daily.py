#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
ETF Daily Buy/Sell Signals Loader - Optimal Pattern.


Computes buy/sell signals from ETF price data.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadbuysell_etf_daily.py [--symbols SPY,QQQ] [--parallelism 8]
"""
from utils.structured_logger import get_logger


try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
logger = get_logger(__name__)
import os
import psycopg2
from config.env_loader import load_env
from datetime import date, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from utils.optimal_loader import OptimalLoader




class BuySellETFDailyLoader(OptimalLoader):
    table_name = "buy_sell_daily_etf"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price data and compute signals."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return []

        rows = self.router.fetch_ohlcv(symbol, start, end)
        if not rows:
            return []

        return self._compute_signals(symbol, rows)

    def _compute_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        """Compute buy/sell signals from price data using technical indicators."""
        if len(price_rows) < 20:
            return []

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low"]):
            return []

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df = df.dropna(subset=["close"])

        if len(df) < 20:
            return None

        df["rsi"] = self._compute_rsi(df["close"], 14)
        df["macd"], df["signal_line"] = self._compute_macd(df["close"])

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
            return {
                "symbol": symbol,
                "date": date_val if isinstance(date_val, str) else str(date_val),
                "signal": signal_type,
                "strength": float(rsi) / 100 if not pd.isna(rsi) else None,
            }
        return None

    def transform(self, rows):
        """Signals are already clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate signal row."""
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")


def get_active_etf_symbols() -> List[str]:
    """Pull active ETF symbols from database or use defaults."""
    from utils.db_connection import get_db_connection
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    except (psycopg2.Error, OSError) as e:

        logging.warning(f"Failed to fetch ETF symbols: {e}")
        return ["SPY", "QQQ", "IWM", "EEM", "EFA"]
    finally:
        try:
            conn.close()
        except psycopg2.Error:
                pass


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal buy_sell_etf_daily loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs from database.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_etf_symbols()

    loader = BuySellETFDailyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

