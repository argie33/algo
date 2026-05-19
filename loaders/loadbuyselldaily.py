#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Buy/Sell Signals Loader - Multi-timeframe (daily/weekly/monthly) with stock/ETF support.

Consolidated: Previously split across loadbuyselldaily.py, loadbuysell_etf_daily.py,
load_buysell_aggregate.py, and load_buysell_etf_aggregate.py. Now one parametrized loader.

Computes buy/sell trading signals from price_daily (or etf_price_daily) using technical indicators.
Reads local price tables (populated by loadpricedaily.py) to avoid re-fetching from APIs.

Run:
    python3 loadbuyselldaily.py --timeframe daily [--symbols AAPL,MSFT] [--asset-class stock]
    python3 loadbuyselldaily.py --timeframe weekly [--symbols AAPL,MSFT]
    python3 loadbuyselldaily.py --timeframe daily --symbols SPY,QQQ --asset-class etf
"""
import argparse
import logging
import os
from datetime import date, timedelta
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from loaders.technical_indicators import compute_rsi, compute_macd

logger = get_logger(__name__)
log = logging.getLogger(__name__)


# Config for different timeframes
_TIMEFRAME_CONFIG = {
    "daily": {
        "resample_rule": None,  # No resampling for daily
        "min_daily_rows": 50,
        "min_bars": 50,
        "lookback_days": 300,
        "has_atr": True,
    },
    "weekly": {
        "resample_rule": "W",
        "min_daily_rows": 50,
        "min_bars": 15,
        "lookback_days": 400,
        "has_atr": True,
    },
    "monthly": {
        "resample_rule": "MS",
        "min_daily_rows": 100,
        "min_bars": 12,
        "lookback_days": 800,
        "has_atr": False,
    },
}


class BuySellSignalsLoader(OptimalLoader):
    """Multi-timeframe buy/sell signals loader. Consolidates 4 separate loaders."""

    def __init__(self, timeframe: str = "daily", asset_class: str = "stock", *args, **kwargs):
        """Initialize with timeframe (daily/weekly/monthly) and asset_class (stock/etf)."""
        assert timeframe in ("daily", "weekly", "monthly"), f"Invalid timeframe: {timeframe}"
        assert asset_class in ("stock", "etf"), f"Invalid asset_class: {asset_class}"

        self.timeframe = timeframe
        self.asset_class = asset_class
        self.cfg = _TIMEFRAME_CONFIG[timeframe]

        # Map timeframe + asset_class to table names
        if asset_class == "etf":
            self.price_table = "etf_price_daily"
            if timeframe == "daily":
                self.table_name = "buy_sell_daily_etf"
            elif timeframe == "weekly":
                self.table_name = "buy_sell_weekly_etf"
            else:  # monthly
                self.table_name = "buy_sell_monthly_etf"
        else:  # stock
            self.price_table = "price_daily"
            if timeframe == "daily":
                self.table_name = "buy_sell_daily"
            elif timeframe == "weekly":
                self.table_name = "buy_sell_weekly"
            else:  # monthly
                self.table_name = "buy_sell_monthly"

        self.primary_key = ("symbol", "timeframe", "date")
        self.watermark_field = "date"
        super().__init__(*args, **kwargs)

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Pull price rows from the local `price_daily` table.

        We need a lookback large enough that the longest indicator (50/200 SMA,
        MACD slow=26) has warmed up at the watermark date — fetch 300 trading
        days before the watermark.
        """
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            # Re-fetch enough history to warm up indicators, then filter
            # signals after the watermark in _compute_signals.
            start = since - timedelta(days=400)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            return []

        # Fetch trend template data for stage/trend info
        trend_data = self._fetch_trend_data(symbol, start, end)

        signals = self._compute_signals(symbol, rows, trend_data)
        if not signals:
            return []

        # Only emit signals strictly newer than the watermark
        if since is not None:
            since_str = since.isoformat()
            signals = [s for s in signals if s["date"] > since_str]

        return signals

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        """Read OHLCV from local price_daily table."""
        from utils.db_connection import get_db_connection
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

    def _fetch_trend_data(self, symbol: str, start: date, end: date) -> dict:
        """Fetch trend template data (stage, trend direction) for date range."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT date, weinstein_stage, trend_direction, minervini_trend_score
                    FROM trend_template_data
                    WHERE symbol = %s AND date >= %s AND date <= %s
                    ORDER BY date ASC
                    """,
                    (symbol, start, end),
                )
                rows = cur.fetchall()
                return {
                    r[0].isoformat(): {
                        "stage_number": int(r[1]) if r[1] else None,
                        "trend_direction": r[2],
                        "trend_score": float(r[3]) if r[3] else None,
                    }
                    for r in rows
                }
            finally:
                cur.close()
        except Exception:
            return {}

    def _compute_signals(self, symbol: str, price_rows: List[dict], trend_data: dict = None) -> Optional[List[dict]]:
        """Compute Minervini breakout buy/sell signals from price data."""
        if len(price_rows) < 50:
            return []

        if trend_data is None:
            trend_data = {}

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low"]):
            return []

        for col in ["close", "high", "low", "open"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce")
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        if len(df) < 50:
            return []

        df["rsi"] = compute_rsi(df["close"], 14)
        macd, signal_line = compute_macd(df["close"])
        df["macd"] = macd
        df["signal_line"] = signal_line
        df["sma_50"] = df["close"].rolling(50).mean()
        df["sma_200"] = df["close"].rolling(200).mean()
        df["ema_21"] = df["close"].ewm(span=21).mean()
        df["avg_volume_50d"] = df["volume"].rolling(50).mean()

        signals = []
        for i in range(len(df)):
            sig = self._generate_signal_row(df, i, symbol, trend_data)
            if sig:
                signals.append(sig)

        return signals

    def _generate_signal_row(self, df, row_idx: int, symbol: str, trend_data: dict) -> Optional[dict]:
        """Generate Minervini-style breakout buy/sell signal for one price row.

        BUY: price breaks above the prior 25-bar consolidation high on elevated volume,
             with healthy RSI momentum and MACD bullish — aligns with the breakout
             methodology used throughout the filter pipeline and swing scorer.

        SELL: price closes below 21-EMA or 50-SMA on elevated volume with MACD bearish.

        This replaces the prior mean-reversion (RSI<30 oversold) approach that produced
        near-zero signals in Stage 2 uptrending stocks — a philosophical mismatch with
        the Minervini breakout strategy used by the rest of the algo.
        """
        row = df.iloc[row_idx]

        def _f(col):
            v = row.get(col) if hasattr(row, 'get') else row[col] if col in row.index else None
            try:
                import math
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return None
                return float(v)
            except (TypeError, ValueError):
                return None

        close = _f("close")
        high = _f("high")
        low = _f("low")
        volume = _f("volume")
        date_val = row["date"] if "date" in row.index else None
        date_str = date_val if isinstance(date_val, str) else str(date_val) if date_val is not None else None

        if close is None or close <= 0 or date_str is None:
            return None

        rsi = _f("rsi")
        macd = _f("macd")
        signal_line = _f("signal_line")
        sma_50 = _f("sma_50")
        ema_21 = _f("ema_21")
        avg_volume_50d = _f("avg_volume_50d")

        if any(v is None for v in [rsi, macd, signal_line, sma_50, ema_21, avg_volume_50d]):
            return None

        # Suppress definitive Stage 4 downtrend; filter pipeline gates Stage 2
        trend_info = trend_data.get(date_str, {})
        if trend_info.get("stage_number") == 4:
            return None

        # Volume ratio vs 50-day average
        vol_ratio = (volume / avg_volume_50d) if (avg_volume_50d > 0 and volume is not None) else 0.0

        # Pivot: highest high of the prior 25 bars (consolidation base ceiling)
        # Look back without lookahead bias using row_idx
        pivot = None
        if row_idx >= 10:
            lookback = df.iloc[max(0, row_idx - 25):row_idx]
            if len(lookback) >= 10:
                pivot = float(lookback["high"].max())

        # Close quality: fraction of day's range above the low
        day_range = (high - low) if (high is not None and low is not None) else 0
        close_quality = ((close - low) / day_range) if day_range > 0 else 0.5

        signal_str = None
        reason_parts = []

        # BUY: Minervini breakout above base high on volume with healthy momentum
        if (
            pivot is not None and
            close > pivot and           # breakout above consolidation high
            vol_ratio >= 1.5 and        # institutional volume surge
            45 <= rsi <= 75 and         # healthy momentum zone
            macd > signal_line and      # MACD bullish
            close > sma_50 and          # above medium-term trend
            close > ema_21 and          # above short-term trend
            close_quality >= 0.60       # strong close in upper 40% of range
        ):
            signal_str = "BUY"
            breakout_pct = ((close - pivot) / pivot * 100) if pivot > 0 else 0
            reason_parts.append(f"Breakout +{breakout_pct:.1f}% above base")
            reason_parts.append(f"Vol {vol_ratio:.1f}x avg")
            if close_quality >= 0.85:
                reason_parts.append("Strong close")

        # SELL: Trend breakdown below key MAs on volume with weakening momentum
        elif (
            (close < ema_21 or close < sma_50) and
            vol_ratio >= 1.25 and
            rsi < 50 and
            macd < signal_line
        ):
            signal_str = "SELL"
            reason_parts.append("Below EMA21" if close < ema_21 else "Below SMA50")
            reason_parts.append(f"Vol {vol_ratio:.1f}x on breakdown")

        if not signal_str:
            return None

        # Strength: volume surge + momentum quality (0-100 scale)
        if signal_str == "BUY":
            strength = min(100.0, (vol_ratio - 1.0) * 30.0 + max(0.0, rsi - 45) * 0.5)
        else:
            strength = min(100.0, (vol_ratio - 1.0) * 30.0 + max(0.0, 50 - rsi) * 0.5)
        strength = max(0.0, strength)

        return {
            "symbol": symbol,
            "date": date_str,
            "timeframe": self.timeframe,
            "signal": signal_str,
            "strength": round(strength, 4),
            "reason": "; ".join(reason_parts)[:255] if reason_parts else f"{signal_str} signal",
        }

    def transform(self, rows):
        """Signals are already clean from compute stage."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate signal row."""
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")



def main():
    load_env()
    parser = argparse.ArgumentParser(description="Buy/Sell signals loader - Multi-timeframe (daily/weekly/monthly)")
    parser.add_argument("--timeframe", choices=["daily", "weekly", "monthly"], default="daily",
                        help="Timeframe: daily, weekly, or monthly")
    parser.add_argument("--asset-class", choices=["stock", "etf"], default="stock",
                        help="Asset class: stock or etf")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stock_symbols table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers (compute-intensive)")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = BuySellSignalsLoader(timeframe=args.timeframe, asset_class=args.asset_class)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
