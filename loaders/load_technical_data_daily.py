#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Daily Technical Indicators Loader.

Computes RSI, MACD, moving averages, ATR, ADX, ROC, momentum from price_daily.
Populates technical_data_daily table.

Run:
    python3 load_technical_data_daily.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import argparse
import logging
import os
from datetime import date, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.loader_helpers import get_active_symbols
from utils.structured_logger import get_logger
from utils.monitoring_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class TechnicalDataDailyLoader(OptimalLoader):
    table_name = "technical_data_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price_daily data for technical calculations."""
        db_conn = get_db_connection()
        end = date.today()

        # Always fetch 252 days lookback for accurate moving averages
        start = end - timedelta(days=252)

        query = """
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s
            ORDER BY date ASC
        """

        try:
            cursor = db_conn.cursor()
            cursor.execute(query, (symbol, start, end))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return None

            # Convert to list of dicts
            return [
                {
                    'symbol': row[0],
                    'date': row[1],
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': float(row[6]),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch price_daily: {e}")
            return None
        finally:
            db_conn.close()

    def transform(self, rows):
        """Compute all technical indicators from price data."""
        if not rows or len(rows) < 20:
            return []

        try:
            df = pd.DataFrame(rows)
            df = df.sort_values('date').reset_index(drop=True)

            # Compute all indicators
            df = self._compute_all_indicators(df)

            # Extract only rows needed for database (drop intermediate calculation rows)
            # Keep only the last 100 rows to avoid storing too much historical data
            df = df.tail(100)

            # Convert back to list of dicts
            result = []
            for _, row in df.iterrows():
                result.append({
                    'symbol': row['symbol'],
                    'date': row['date'],
                    'rsi': float(row.get('rsi', np.nan)),
                    'macd': float(row.get('macd', np.nan)),
                    'macd_signal': float(row.get('macd_signal', np.nan)),
                    'macd_hist': float(row.get('macd_hist', np.nan)),
                    'mom': float(row.get('mom', np.nan)),
                    'roc': float(row.get('roc', np.nan)),
                    'roc_10d': float(row.get('roc_10d', np.nan)),
                    'roc_20d': float(row.get('roc_20d', np.nan)),
                    'roc_60d': float(row.get('roc_60d', np.nan)),
                    'roc_120d': float(row.get('roc_120d', np.nan)),
                    'roc_252d': float(row.get('roc_252d', np.nan)),
                    'sma_20': float(row.get('sma_20', np.nan)),
                    'sma_50': float(row.get('sma_50', np.nan)),
                    'sma_200': float(row.get('sma_200', np.nan)),
                    'ema_12': float(row.get('ema_12', np.nan)),
                    'ema_26': float(row.get('ema_26', np.nan)),
                    'atr': float(row.get('atr', np.nan)),
                    'adx': float(row.get('adx', np.nan)),
                    'plus_di': float(row.get('plus_di', np.nan)),
                    'minus_di': float(row.get('minus_di', np.nan)),
                    'mansfield_rs': float(row.get('mansfield_rs', np.nan)),
                })

            return result
        except Exception as e:
            logger.error(f"Transform failed: {e}")
            return []

    def _compute_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all technical indicators."""
        df = df.copy()

        # RSI (14 period)
        df['rsi'] = self._compute_rsi(df['close'], 14)

        # MACD (12, 26, 9)
        df['macd'], df['macd_signal'], df['macd_hist'] = self._compute_macd(df['close'])

        # Momentum
        df['mom'] = df['close'].diff(1)
        df['roc'] = (df['close'].pct_change(1) * 100)
        df['roc_10d'] = (df['close'].pct_change(10) * 100)
        df['roc_20d'] = (df['close'].pct_change(20) * 100)
        df['roc_60d'] = (df['close'].pct_change(60) * 100)
        df['roc_120d'] = (df['close'].pct_change(120) * 100)
        df['roc_252d'] = (df['close'].pct_change(252) * 100)

        # Moving Averages
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()

        # ATR (14 period)
        df['atr'] = self._compute_atr(df['high'], df['low'], df['close'], 14)

        # ADX (Average Directional Index)
        df['adx'], df['plus_di'], df['minus_di'] = self._compute_adx(
            df['high'], df['low'], df['close'], 14
        )

        # Mansfield RS (Relative Strength vs SPY)
        df['mansfield_rs'] = 0.0  # Will be populated by separate calculation if needed

        return df

    def _compute_rsi(self, closes: pd.Series, period: int = 14) -> pd.Series:
        """Compute Relative Strength Index."""
        deltas = closes.diff()
        gains = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        rs = gains / losses.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _compute_macd(self, closes: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9):
        """Compute MACD line, signal line, and histogram."""
        ema_fast = closes.ewm(span=fast).mean()
        ema_slow = closes.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _compute_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Compute Average True Range."""
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr

    def _compute_adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
        """Compute ADX, +DI, -DI (Average Directional Index)."""
        # Calculate directional movements
        plus_dm = high.diff()
        minus_dm = -low.diff()

        # Set to 0 when no directional movement
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
        minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate DI+ and DI-
        atr = tr.rolling(period).mean()
        plus_di = (plus_dm.rolling(period).mean() / atr) * 100
        minus_di = (minus_dm.rolling(period).mean() / atr) * 100

        # Calculate ADX
        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di
        di_ratio = di_diff / di_sum.replace(0, np.nan)

        adx = di_ratio.rolling(period).mean() * 100

        return adx, plus_di, minus_di


def main():
    try:
        load_env()
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Technical Data Daily Loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    default_parallelism = int(os.getenv("PARALLELISM", os.getenv("LOADER_PARALLELISM", "4")))
    parser.add_argument("--parallelism", type=int, default=default_parallelism, help="Concurrent workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from CLI")
        else:
            symbols = get_active_symbols()
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database")
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        return 1

    loader = TechnicalDataDailyLoader()
    try:
        logger.info(f"[MAIN] Starting technical data loader (parallelism={args.parallelism})")
        with TimeBlock("load_technical_data_daily"):
            stats = loader.run(symbols, parallelism=args.parallelism)

        logger.info(f"[MAIN] Loader completed: {stats}")
        return 0 if stats["symbols_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"[MAIN] Loader failed with error: {e}", exc_info=True)
        return 1
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
