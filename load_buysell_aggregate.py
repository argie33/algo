#!/usr/bin/env python3
"""
Buy/Sell Signal Aggregate Loader — weekly and monthly signals from daily prices.

Timeframe determined by LOADER_TYPE env var (signals_weekly / signals_monthly)
or --timeframe CLI flag for manual runs.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from credential_helper import get_db_password, get_db_config
from typing import List, Optional

try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

_TIMEFRAME_CONFIG = {
    "weekly": {
        "table_name": "buy_sell_weekly",
        "timeframe_value": "Weekly",
        "resample_rule": "W",
        "min_daily_rows": 50,
        "min_bars": 15,
        "lookback_days": 400,
        "has_atr": True,
    },
    "monthly": {
        "table_name": "buy_sell_monthly",
        "timeframe_value": "Monthly",
        "resample_rule": "MS",
        "min_daily_rows": 100,
        "min_bars": 12,
        "lookback_days": 800,
        "has_atr": False,
    },
}


def _resolve_timeframe(cli_arg: Optional[str]) -> str:
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "monthly" if "monthly" in loader_type else "weekly"


class BuySellAggregateLoader(OptimalLoader):
    primary_key = ("symbol", "timeframe", "date")
    watermark_field = "date"

    def __init__(self, timeframe: str):
        assert timeframe in ("weekly", "monthly")
        cfg = _TIMEFRAME_CONFIG[timeframe]
        self.timeframe = timeframe
        self.table_name = cfg["table_name"]
        self.timeframe_value = cfg["timeframe_value"]
        self._resample_rule = cfg["resample_rule"]
        self._min_daily_rows = cfg["min_daily_rows"]
        self._min_bars = cfg["min_bars"]
        self._lookback_days = cfg["lookback_days"]
        self._has_atr = cfg["has_atr"]
        super().__init__()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        start = (end - timedelta(days=5 * 365)) if since is None else (since - timedelta(days=self._lookback_days))
        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            return None
        signals = self._compute_signals(symbol, rows)
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

    def _compute_signals(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        if len(price_rows) < self._min_daily_rows:
            return None
        try:
            import pandas as pd
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        for col in ("close", "high", "low", "open", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"])

        bars = df.set_index("date").resample(self._resample_rule).agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
        }).dropna(subset=["close"])

        if len(bars) < self._min_bars:
            return None

        bars["rsi"] = self._compute_rsi(bars["close"], 14)
        macd, signal_line = self._compute_macd(bars["close"])
        bars["macd"] = macd
        bars["signal_line"] = signal_line
        if self._has_atr:
            bars["atr"] = self._compute_atr(bars["high"], bars["low"], bars["close"], 14)

        signals = []
        for idx, row in bars.iterrows():
            sig = self._generate_signal_row(row, symbol, idx.date(), pd)
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

    @staticmethod
    def _compute_atr(highs, lows, closes, period=14):
        import pandas as pd
        tr = pd.concat([
            highs - lows,
            (highs - closes.shift()).abs(),
            (lows - closes.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def _generate_signal_row(self, row, symbol: str, idx_date, pd):
        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal_line):
            return None
        if rsi < 30 and macd > signal_line:
            signal_str = "BUY"
        elif rsi > 70 and macd < signal_line:
            signal_str = "SELL"
        else:
            return None

        def _f(v):
            return float(v) if v is not None and not pd.isna(v) else None

        result = {
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
        if self._has_atr:
            result["atr"] = _f(row.get("atr"))
        return result

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
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Buy/sell aggregate loader (weekly/monthly)")
    parser.add_argument("--timeframe", choices=["weekly", "monthly"],
                        help="Signal timeframe (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    timeframe = _resolve_timeframe(args.timeframe)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = BuySellAggregateLoader(timeframe)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

