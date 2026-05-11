#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Daily Buy/Sell Signals Loader - Optimal Pattern.

Computes buy/sell trading signals from price_daily using technical indicators.
Inherits watermarks, dedup, parallelism, and bulk COPY from OptimalLoader.

Data source:
    Reads price history from the local `price_daily` table (already populated
    by `loadpricedaily.py`). This avoids hammering Yahoo Finance / Alpaca for
    data we already have. If price_daily lacks coverage, run loadpricedaily.py
    first.

Run:
    python3 loadbuyselldaily.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

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


def _detect_base_type(df, pd):
    """Detect base type: flat base, VCP (volatility contraction), or pullback.

    Returns dict with type, length_days, quality, pivot_price, zone_start, zone_end.
    """
    try:
        if len(df) < 20:
            return {'type': 'Unknown', 'quality': 'B'}

        # Look at last 30 days of data
        recent = df.tail(30)
        if len(recent) < 10:
            return {'type': 'Unknown', 'quality': 'B'}

        high_max = recent['high'].max()
        low_min = recent['low'].min()
        close_curr = recent['close'].iloc[-1]

        # Consolidation range as percentage
        if high_max > 0:
            consol_pct = ((high_max - low_min) / low_min) * 100.0
        else:
            return {'type': 'Unknown', 'quality': 'B'}

        # Detect base type
        if consol_pct < 3.0:
            # Tight base = Flat base (good setup)
            return {
                'type': 'Flat Base',
                'length_days': len(recent),
                'quality': 'A',  # Tight consolidation is higher quality
                'pivot_price': low_min,
                'zone_start': low_min,
                'zone_end': high_max,
            }
        elif 3.0 <= consol_pct < 8.0:
            # Moderate consolidation - could be VCP or normal consolidation
            # Check if ranges have been contracting (VCP signature)
            widths = [(recent['high'].iloc[i] - recent['low'].iloc[i]) for i in range(len(recent))]
            if len(widths) > 10:
                avg_early = sum(widths[-20:-10]) / 10.0
                avg_recent = sum(widths[-10:]) / 10.0
                if avg_recent < avg_early * 0.8:  # Ranges contracting
                    return {
                        'type': 'VCP',
                        'length_days': len(recent),
                        'quality': 'A',
                        'pivot_price': low_min,
                        'zone_start': low_min,
                        'zone_end': high_max,
                    }
            return {
                'type': 'Consolidation',
                'length_days': len(recent),
                'quality': 'B',
                'pivot_price': low_min,
                'zone_start': low_min,
                'zone_end': high_max,
            }
        else:
            # Wide consolidation - likely pullback/retest setup
            return {
                'type': 'Pullback',
                'length_days': len(recent),
                'quality': 'B',
                'pivot_price': low_min,
                'zone_start': low_min,
                'zone_end': high_max,
            }
    except Exception as e:
        log.debug(f"Base detection failed: {e}")
        return {'type': 'Unknown', 'quality': 'B'}


class BuySellDailyLoader(OptimalLoader):
    table_name = "buy_sell_daily"
    primary_key = ("symbol", "timeframe", "date")
    watermark_field = "date"
    timeframe_value = "Daily"

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
            return None

        # Fetch SPY data for Mansfield RS calculation
        spy_rows = self._fetch_price_daily('SPY', start, end)

        # Fetch trend template data for stage/trend info
        trend_data = self._fetch_trend_data(symbol, start, end)

        signals = self._compute_signals(symbol, rows, trend_data, spy_rows)
        if not signals:
            # No signals computed at all (e.g., insufficient data)
            return None

        # Only emit signals strictly newer than the watermark
        if since is not None:
            since_str = since.isoformat()
            signals = [s for s in signals if s["date"] > since_str]

        # NOTE: If no signals pass the watermark filter, we return None here.
        # This can cause watermark stagnation if no new signals occur.
        # Mitigation: Run with BACKFILL_DAYS env var to force full reload periodically,
        # or delete watermarks from loader_watermarks table to reset.
        return signals or None

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        """Read OHLCV from local price_daily table."""
        import psycopg2
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

    def _compute_signals(self, symbol: str, price_rows: List[dict], trend_data: dict = None, spy_rows: List[dict] = None) -> Optional[List[dict]]:
        """Compute buy/sell signals from price data using technical indicators."""
        if len(price_rows) < 50:
            return None

        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            log.error("pandas/numpy not available")
            return None

        if trend_data is None:
            trend_data = {}

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low"]):
            return None

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        if len(df) < 50:
            return None

        # Prepare SPY data for Mansfield RS calculation
        spy_df = None
        if spy_rows:
            spy_df = pd.DataFrame(spy_rows)
            spy_df["close"] = pd.to_numeric(spy_df["close"], errors="coerce")
            spy_df["date"] = pd.to_datetime(spy_df["date"])
            spy_df = spy_df.dropna(subset=["close"]).set_index("date")

        df["rsi"] = self._compute_rsi(df["close"], 14)
        macd, signal_line = self._compute_macd(df["close"])
        df["macd"] = macd
        df["signal_line"] = signal_line
        df["atr"] = self._compute_atr(df["high"], df["low"], df["close"], 14)
        df["adx"] = self._compute_adx(df["high"], df["low"], df["close"], 14)
        df["sma_50"] = df["close"].rolling(50).mean()
        df["sma_200"] = df["close"].rolling(200).mean()
        df["ema_21"] = df["close"].ewm(span=21).mean()
        df["avg_volume_50d"] = df["volume"].rolling(50).mean()

        signals = []
        for _, row in df.iterrows():
            sig = self._generate_signal_row(row, symbol, pd, trend_data, spy_df, df)
            if sig:
                signals.append(sig)

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
        import pandas as pd
        tr1 = highs - lows
        tr2 = (highs - closes.shift()).abs()
        tr3 = (lows - closes.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    @staticmethod
    def _compute_adx(highs, lows, closes, period=14):
        """Compute Average Directional Index (simplified)."""
        import pandas as pd
        plus_dm = highs.diff()
        minus_dm = lows.diff().abs()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        tr1 = highs - lows
        tr2 = (highs - closes.shift()).abs()
        tr3 = (lows - closes.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        return adx

    def _generate_signal_row(self, row, symbol: str, pd, trend_data: dict = None, spy_df=None, df=None):
        """Generate buy/sell signal from indicators for one row."""
        if trend_data is None:
            trend_data = {}

        rsi = row.get("rsi")
        macd = row.get("macd")
        signal_line = row.get("signal_line")
        date_val = row.get("date")

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

        # Compute entry price, stop level, and buy level
        close_price = _f(row.get("close"))
        high_price = _f(row.get("high"))
        low_price = _f(row.get("low"))
        atr = _f(row.get("atr"))

        # Entry price is the close (for BUY signals, this is the signal trigger price)
        entry_price = close_price

        # CRITICAL FIX: Validate entry_price exists (239 signals currently NULL)
        if entry_price is None or entry_price <= 0:
            return None  # Skip signals with invalid entry prices

        # Stop level: 2x ATR below the low of the signal day (for BUY signals)
        # This provides a reasonable stop loss
        if atr and low_price and signal_str == "BUY":
            stop_level = low_price - (atr * 2.0)
        elif atr and high_price and signal_str == "SELL":
            stop_level = high_price + (atr * 2.0)
        else:
            stop_level = None

        # Buy level is the same as entry price (we're trading the close)
        buy_level = entry_price

        # Fetch trend data for this date if available
        date_str = date_val if isinstance(date_val, str) else str(date_val)
        trend_info = trend_data.get(date_str, {})
        stage_number = trend_info.get("stage_number")
        trend_direction = trend_info.get("trend_direction")

        # Derive market_stage from trend_direction (real data only)
        market_stage = trend_direction if trend_direction else None

        # Compute Mansfield RS (relative strength vs SPY) if SPY data available
        mansfield_rs = None
        if spy_df is not None:
            try:
                # Get 60-day returns for both stock and SPY
                date_pd = pd.to_datetime(date_val)
                stock_60d_ago = date_pd - pd.Timedelta(days=60)

                # Find closes around date and 60d ago
                stock_recent = row.get("close")
                if stock_recent and date_pd in spy_df.index:
                    spy_recent = spy_df.loc[date_pd, "close"]
                    stock_old = None
                    spy_old = None

                    # Search for closes ~60 days prior
                    for i in range(50, 80):
                        check_date = date_pd - pd.Timedelta(days=i)
                        if check_date in spy_df.index:
                            spy_old = spy_df.loc[check_date, "close"]
                            break

                    if spy_old and spy_recent and spy_old > 0:
                        stock_return = (stock_recent - stock_old) / stock_old if stock_old > 0 else 0
                        spy_return = (spy_recent - spy_old) / spy_old
                        # Relative strength: 100 = tied, >100 = stock outperforming, <100 = underperforming
                        if spy_return != -1:
                            mansfield_rs = 100 * (1 + stock_return) / (1 + spy_return)
            except Exception as e:
                log.debug(f"Mansfield RS calc failed for {symbol} on {date_val}: {e}")

        # RS rating: Mansfield RS if available, else RSI (0-100)
        rs_rating = None
        if mansfield_rs is not None:
            rs_rating = int(round(mansfield_rs))
        else:
            rsi_val = _f(rsi)
            rs_rating = int(round(rsi_val)) if rsi_val is not None else None

        # Base type detection: flat base vs VCP vs pullback
        base_info = _detect_base_type(df, pd)
        base_type = base_info.get('type', 'Unknown')
        base_length_days = base_info.get('length_days')
        breakout_quality = base_info.get('quality', 'B')
        pivot_price = base_info.get('pivot_price', close_price)
        buy_zone_start = base_info.get('zone_start', entry_price)
        buy_zone_end = base_info.get('zone_end', entry_price)

        return {
            "symbol": symbol,
            "timeframe": self.timeframe_value,
            "date": date_str,
            "open": _f(row.get("open")),
            "high": _f(row.get("high")),
            "low": _f(row.get("low")),
            "close": _f(row.get("close")),
            "volume": int(row["volume"]) if row.get("volume") is not None and not pd.isna(row.get("volume")) else None,
            "signal": signal_str,
            "signal_type": signal_str.capitalize(),
            "entry_price": entry_price,
            "buylevel": buy_level,
            "stoplevel": stop_level,
            "rsi": _f(rsi),
            "adx": _f(row.get("adx")),
            "atr": _f(row.get("atr")),
            "sma_50": _f(row.get("sma_50")),
            "sma_200": _f(row.get("sma_200")),
            "ema_21": _f(row.get("ema_21")),
            "stage_number": stage_number,
            "market_stage": market_stage,
            "rs_rating": rs_rating,
            "base_type": base_type,
            "base_length_days": base_length_days,
            "breakout_quality": breakout_quality,
            "pivot_price": pivot_price,
            "buy_zone_start": buy_zone_start,
            "buy_zone_end": buy_zone_end,
            "avg_volume_50d": int(row.get("avg_volume_50d")) if row.get("avg_volume_50d") is not None and not pd.isna(row.get("avg_volume_50d")) else None,
        }

    def transform(self, rows):
        """Signals are already clean from compute stage."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate signal row."""
        if not super()._validate_row(row):
            return False
        return row.get("signal") in ("BUY", "SELL")


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stock_symbols table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=credential_manager.get_db_credentials()["password"],
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal buy_sell_daily loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stock_symbols table.")
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
