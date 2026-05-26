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
    compute_atr, compute_bollinger_bands, compute_volume_ma, compute_adx
)

logger = get_logger(__name__)


class TechnicalDataDailyLoader(OptimalLoader):
    table_name = "technical_data_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, use yesterday instead
        # (prevents computing indicators for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Read the actual DB max date to avoid re-fetching 5 years of history.
        if since is None:
            try:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute(
                    "SELECT MAX(date) FROM technical_data_daily WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                cur.close()
                if row and row[0]:
                    since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except Exception as e:
                logger.warning(f"Could not read technical_data_daily watermark for {symbol}: {e}")

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            # Keep 300-day lookback so long moving averages (SMA 200) stay warm.
            start = since - timedelta(days=300)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            return []

        spy_rows = self._fetch_price_daily("SPY", start, end) if symbol != "SPY" else []
        indicators = self._compute_all_indicators(symbol, rows, spy_rows)
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

    def _compute_all_indicators(self, symbol: str, rows: List[dict], spy_rows: List[dict] = None) -> List[dict]:
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

        # Compute all technical indicators required by schema
        df["rsi_14"] = compute_rsi(df["close"], 14)
        df["rsi"] = df["rsi_14"]  # Schema has both rsi and rsi_14

        df["macd"], df["macd_signal"] = compute_macd(df["close"])
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        df["macd_histogram"] = df["macd_hist"]  # Schema has both names

        # Momentum and rate of change (clamped to DECIMAL(8,4) range: ±9999.9999)
        df["mom"] = df["close"].diff()
        df["roc"] = df["close"].pct_change() * 100
        df["roc_10d"] = df["close"].pct_change(10) * 100
        df["roc_20d"] = df["close"].pct_change(20) * 100
        df["roc_60d"] = df["close"].pct_change(60) * 100
        df["roc_120d"] = df["close"].pct_change(120) * 100
        df["roc_252d"] = df["close"].pct_change(252) * 100

        # Clamp ROC values to database field limits to prevent overflow
        roc_cols = ["roc", "roc_10d", "roc_20d", "roc_60d", "roc_120d", "roc_252d"]
        for col in roc_cols:
            df[col] = df[col].clip(-9999.9999, 9999.9999)

        mas = compute_moving_averages(df["close"])
        for name, values in mas.items():
            df[name] = values

        df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], 14)
        df["atr"] = df["atr_14"]  # Schema has both atr and atr_14

        df["plus_di"], df["minus_di"], df["adx"] = compute_adx(df["high"], df["low"], df["close"], 14)

        # Mansfield Relative Strength: (rs_line / 52wk_ma_of_rs_line - 1) * 100
        # rs_line = close / spy_close; requires SPY prices aligned to same dates
        if spy_rows:
            spy_df = pd.DataFrame(spy_rows)
            spy_df["date"] = pd.to_datetime(spy_df["date"])
            spy_closes = spy_df.set_index("date")["close"]
            spy_aligned = spy_closes.reindex(df["date"].values)
            rs_line = df["close"].values / spy_aligned.values
            rs_line_s = pd.Series(rs_line, index=df.index)
            rs_line_52w_ma = rs_line_s.rolling(window=252, min_periods=126).mean()
            df["mansfield_rs"] = (rs_line_s / rs_line_52w_ma - 1) * 100
        else:
            df["mansfield_rs"] = None

        bbs = compute_bollinger_bands(df["close"], 20, 2.0)
        for name, values in bbs.items():
            df[name] = values

        df["volume_ma_50"] = compute_volume_ma(df["volume"], 50)

        results = []
        for _, row in df.iterrows():
            results.append({
                "symbol": symbol,
                "date": row["date"].date().isoformat(),
                "rsi": float(row["rsi"]) if pd.notna(row["rsi"]) else None,
                "rsi_14": float(row["rsi_14"]) if pd.notna(row["rsi_14"]) else None,
                "macd": float(row["macd"]) if pd.notna(row["macd"]) else None,
                "macd_signal": float(row["macd_signal"]) if pd.notna(row["macd_signal"]) else None,
                "macd_hist": float(row["macd_hist"]) if pd.notna(row["macd_hist"]) else None,
                "macd_histogram": float(row["macd_histogram"]) if pd.notna(row["macd_histogram"]) else None,
                "mom": float(row["mom"]) if pd.notna(row["mom"]) else None,
                "roc": float(row["roc"]) if pd.notna(row["roc"]) else None,
                "roc_10d": float(row["roc_10d"]) if pd.notna(row["roc_10d"]) else None,
                "roc_20d": float(row["roc_20d"]) if pd.notna(row["roc_20d"]) else None,
                "roc_60d": float(row["roc_60d"]) if pd.notna(row["roc_60d"]) else None,
                "roc_120d": float(row["roc_120d"]) if pd.notna(row["roc_120d"]) else None,
                "roc_252d": float(row["roc_252d"]) if pd.notna(row["roc_252d"]) else None,
                "sma_20": float(row["sma_20"]) if pd.notna(row["sma_20"]) else None,
                "sma_50": float(row["sma_50"]) if pd.notna(row["sma_50"]) else None,
                "sma_150": float(row["sma_150"]) if pd.notna(row["sma_150"]) else None,
                "sma_200": float(row["sma_200"]) if pd.notna(row["sma_200"]) else None,
                "ema_12": float(row["ema_12"]) if pd.notna(row["ema_12"]) else None,
                "ema_21": float(row["ema_21"]) if pd.notna(row["ema_21"]) else None,
                "ema_26": float(row["ema_26"]) if pd.notna(row["ema_26"]) else None,
                "atr": float(row["atr"]) if pd.notna(row["atr"]) else None,
                "atr_14": float(row["atr_14"]) if pd.notna(row["atr_14"]) else None,
                "bb_upper": float(row["bb_upper"]) if pd.notna(row["bb_upper"]) else None,
                "bb_middle": float(row["bb_middle"]) if pd.notna(row["bb_middle"]) else None,
                "bb_lower": float(row["bb_lower"]) if pd.notna(row["bb_lower"]) else None,
                "volume_ma_50": float(row["volume_ma_50"]) if pd.notna(row["volume_ma_50"]) else None,
                "adx": float(row["adx"]) if pd.notna(row["adx"]) else None,
                "plus_di": float(row["plus_di"]) if pd.notna(row["plus_di"]) else None,
                "minus_di": float(row["minus_di"]) if pd.notna(row["minus_di"]) else None,
                "mansfield_rs": float(row["mansfield_rs"]) if pd.notna(row["mansfield_rs"]) else None,
            })
        return results


def main():
    try:
        load_env()
    except Exception as e:
        logger.error(f"Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Load technical indicators")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = args.symbols.split(",")
            logger.info(f"Using {len(symbols)} symbols from command line")
        else:
            logger.info("Fetching active symbols from database...")
            symbols = get_active_symbols(timeout_secs=300)
            if not symbols:
                logger.warning("No symbols found in stock_symbols table - exiting")
                return 1
            logger.info(f"Loaded {len(symbols)} active symbols")
    except Exception as e:
        logger.error(f"Failed to get symbols: {e}", exc_info=True)
        return 1

    logger.info(f"Starting technical data loader with {len(symbols)} symbols, parallelism={args.parallelism}")
    loader = TechnicalDataDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info(f"Technical data daily load completed: {result}")
        return 0
    except Exception as e:
        logger.error(f"Technical data daily load failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
