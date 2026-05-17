#!/usr/bin/env python3
"""
import sys
from utils.logging_setup import get_logger
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

ETF Buy/Sell Signal Aggregate Loader — weekly and monthly signals from ETF prices.

Timeframe determined by LOADER_TYPE env var (signals_etf_weekly / signals_etf_monthly)
or --timeframe CLI flag for manual runs.
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
logger = get_logger(__name__)
import os
import sys
from datetime import date, timedelta
from typing import List, Optional
from config.credential_helper import get_db_password, get_db_config
from config.env_loader import load_env
from utils.loader_helpers import _resolve_timeframe
from utils.loader_helpers import get_active_symbols

from utils.optimal_loader import OptimalLoader



_TIMEFRAME_CONFIG = {
    "weekly": {
        "table_name": "buy_sell_weekly_etf",
        "primary_key": ("symbol", "date"),
        "watermark_field": "date",
        "resample_rule": "W",
        "min_rows": 20,
        "min_bars": 10,
        "pk_date_fn": lambda d: (d - timedelta(days=d.weekday())).isoformat(),
    },
    "monthly": {
        "table_name": "buy_sell_monthly_etf",
        "primary_key": ("symbol", "date"),
        "watermark_field": "date",
        "resample_rule": "MS",
        "min_rows": 20,
        "min_bars": 12,
        "pk_date_fn": lambda d: d.replace(day=1).isoformat(),
    },
}



class BuySellEtfAggregateLoader(OptimalLoader):

    def __init__(self, timeframe: str):
        assert timeframe in ("weekly", "monthly")
        cfg = _TIMEFRAME_CONFIG[timeframe]
        self.timeframe = timeframe
        self.table_name = cfg["table_name"]
        self.primary_key = cfg["primary_key"]
        self.watermark_field = cfg["watermark_field"]
        self._resample_rule = cfg["resample_rule"]
        self._min_rows = cfg["min_rows"]
        self._min_bars = cfg["min_bars"]
        self._pk_date_fn = cfg["pk_date_fn"]
        super().__init__()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        start = (end - timedelta(days=5 * 365)) if since is None else (since + timedelta(days=1))
        if start >= end:
            return None
        rows = self.router.fetch_ohlcv(symbol, start, end)
        if not rows:
            return None
        return self._compute_signals(symbol, rows)

    def _compute_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        if len(price_rows) < self._min_rows:
            return None
        try:
            import pandas as pd
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ("close", "high", "low", "date")):
            return None
        for col in ("close", "high", "low", "open"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"])

        bars = df.set_index("date").resample(self._resample_rule).agg({
            "close": "last", "high": "max", "low": "min", "open": "first",
        }).dropna()

        if len(bars) < self._min_bars:
            return None

        bars["rsi"] = self._compute_rsi(bars["close"], 14)
        bars["macd"], bars["signal_line"] = self._compute_macd(bars["close"])

        signals = []
        for idx, row in bars.iterrows():
            if pd.isna(row.get("rsi")) or pd.isna(row.get("macd")):
                continue
            sig = self._generate_signal(row, symbol, idx.date(), pd)
            if sig:
                signals.append(sig)
        return signals or None

    @staticmethod
    def _compute_rsi(closes, period=14):
        deltas = closes.diff()
        gains = deltas.where(deltas > 0, 0).rolling(window=period).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        return 100 - (100 / (1 + gains / losses))

    @staticmethod
    def _compute_macd(closes, fast=12, slow=26, signal=9):
        macd = closes.ewm(span=fast).mean() - closes.ewm(span=slow).mean()
        return macd, macd.ewm(span=signal).mean()

    def _generate_signal(self, row, symbol: str, idx_date, pd):
        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal_line):
            return None
        if rsi < 30 and macd > signal_line:
            signal_type = "BUY"
        elif rsi > 70 and macd < signal_line:
            signal_type = "SELL"
        else:
            return None
        bucket_date = self._pk_date_fn(idx_date)
        return {
            "symbol": symbol,
            "date": bucket_date,
            "signal": signal_type,
            "strength": float(rsi) / 100 if not pd.isna(rsi) else None,
        }

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")



def main():
    parser = argparse.ArgumentParser(description="ETF buy/sell aggregate loader (weekly/monthly)")
    parser.add_argument("--timeframe", choices=["weekly", "monthly"],
                        help="Signal timeframe (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs.")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    timeframe = _resolve_timeframe(args.timeframe)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = BuySellEtfAggregateLoader(timeframe)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

