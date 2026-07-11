#!/usr/bin/env python3
"""Backfill technical_data_daily for missing dates 2026-06-10 to 2026-07-09.

Session 65: Fix technical_data_daily upstream failure from 2026-06-18.
Currently only 2026-07-10 has full coverage (10190 symbols).
All other dates have partial data (< 150 symbols).
buy_sell_daily needs 30 days of full history to generate swing pivot signals.

Strategy:
1. Delete existing partial data for 2026-06-10 to 2026-07-09
2. Re-compute technical indicators for these dates using price_daily
3. Re-insert with full symbol coverage
"""

import logging
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2

from loaders.technical_indicators import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    compute_volume_ma,
)
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class BackfillTechnicalData:
    """Backfill technical_data_daily for historical dates."""

    def __init__(self):
        self.table_name = "technical_data_daily"

    def run(self):
        """Execute backfill for 2026-06-10 to 2026-07-09."""
        start_time = time.time()

        # Calculate date range
        end_date = date(2026, 7, 10)  # Latest date
        backfill_start = date(2026, 6, 10)  # 30 days before

        logger.info(f"Backfilling technical_data_daily from {backfill_start} to {end_date}")

        try:
            # Step 1: Delete partial data for backfill range
            self._delete_partial_data(backfill_start, end_date)

            # Step 2: Get active symbols
            symbols = get_active_symbols()
            logger.info(f"Will backfill {len(symbols)} active symbols")

            # Step 3: Fetch all prices for the full range (300 days for indicator computation)
            fetch_start = end_date - timedelta(days=300)
            all_prices = self._fetch_all_prices(symbols, fetch_start, end_date)
            if not all_prices:
                raise RuntimeError("No price data found for backfill range")

            logger.info(f"Fetched {len(all_prices)} price rows")

            # Step 4: Compute indicators
            indicators_df = self._compute_all_indicators_vectorized(all_prices)
            if indicators_df.empty:
                raise RuntimeError("Computed indicators dataframe is empty")

            logger.info(f"Computed {len(indicators_df)} indicator rows")

            # Step 5: Filter to backfill date range
            mask = (indicators_df["date"] >= backfill_start) & (indicators_df["date"] <= end_date)
            backfill_df = indicators_df[mask].copy()
            logger.info(f"Filtered to {len(backfill_df)} rows for {backfill_start} to {end_date}")

            # Step 6: Insert backfilled data
            inserted = self._bulk_insert(backfill_df)

            duration = time.time() - start_time
            logger.info(f"Backfill completed: {inserted} rows inserted in {duration:.1f}s")

            return {
                "status": "success",
                "rows_inserted": inserted,
                "date_range": f"{backfill_start} to {end_date}",
                "duration_sec": round(duration, 2)
            }

        except Exception as e:
            logger.error(f"Backfill failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "duration_sec": round(time.time() - start_time, 2)
            }

    def _delete_partial_data(self, start_date: date, end_date: date) -> None:
        """Delete existing partial data in the backfill range."""
        logger.info(f"Deleting partial data for {start_date} to {end_date}")
        with DatabaseContext("write") as cur:
            cur.execute(
                "DELETE FROM technical_data_daily WHERE date >= %s AND date <= %s",
                (start_date, end_date)
            )
            logger.info(f"Deleted {cur.rowcount} existing rows")

    def _fetch_all_prices(self, symbols: list[str], start_date: date, end_date: date) -> list[dict]:
        """Fetch all price data in one query."""
        with DatabaseContext("read") as cur:
            sql_param_markers = ",".join(["%s"] * len(symbols))
            query = f"""
                SELECT symbol, date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol IN ({sql_param_markers})
                AND date >= %s AND date <= %s
                ORDER BY symbol, date ASC
            """
            cur.execute(query, [*symbols, start_date, end_date])
            rows = cur.fetchall()

            result = []
            for r in rows:
                close = float(r[5]) if r[5] is not None else None
                volume = int(r[6]) if r[6] is not None else None

                if close is None or close <= 0:
                    continue
                if volume is not None and volume == 0:
                    continue

                result.append({
                    "symbol": r[0],
                    "date": r[1],
                    "open": float(r[2]) if r[2] is not None else None,
                    "high": float(r[3]) if r[3] is not None else None,
                    "low": float(r[4]) if r[4] is not None else None,
                    "close": close,
                    "volume": volume,
                })

            return result

    def _compute_all_indicators_vectorized(self, prices: list[dict]) -> pd.DataFrame:
        """Compute technical indicators for all symbols at once."""
        df = pd.DataFrame(prices)
        df["date"] = pd.to_datetime(df["date"])

        # Fetch SPY prices once
        all_dates = df["date"]
        spy_prices_cached = self._fetch_spy_prices(all_dates.min().date(), all_dates.max().date())

        results = []

        for symbol in df["symbol"].unique():
            symbol_df = df[df["symbol"] == symbol].sort_values("date").reset_index(drop=True)

            try:
                # Compute basic indicators
                symbol_df["rsi"] = compute_rsi(symbol_df["close"])
                symbol_df["rsi_14"] = symbol_df["rsi"]

                macd_line, signal_line = compute_macd(symbol_df["close"])
                symbol_df["macd"] = macd_line
                symbol_df["macd_signal"] = signal_line
                symbol_df["macd_hist"] = macd_line - signal_line
                symbol_df["macd_histogram"] = symbol_df["macd_hist"]

                # Momentum
                symbol_df["mom"] = symbol_df["close"].diff()
                symbol_df["roc"] = symbol_df["close"].pct_change() * 100
                symbol_df["roc_10d"] = symbol_df["close"].pct_change(10) * 100
                symbol_df["roc_20d"] = symbol_df["close"].pct_change(20) * 100
                symbol_df["roc_60d"] = symbol_df["close"].pct_change(60) * 100
                symbol_df["roc_120d"] = symbol_df["close"].pct_change(120) * 100
                symbol_df["roc_252d"] = symbol_df["close"].pct_change(252) * 100

                # Clamp ROC
                decimal84_max = 9999.9999
                for col in ["roc", "roc_10d", "roc_20d", "roc_60d", "roc_120d", "roc_252d"]:
                    symbol_df[col] = symbol_df[col].clip(-decimal84_max, decimal84_max)

                # Moving averages
                mas = compute_moving_averages(symbol_df["close"])
                for name, values in mas.items():
                    symbol_df[name] = values

                # Bollinger Bands
                bb = compute_bollinger_bands(symbol_df["close"])
                for name, values in bb.items():
                    symbol_df[name] = values

                # ATR/ADX
                symbol_df["atr_14"] = compute_atr(symbol_df["high"], symbol_df["low"], symbol_df["close"], 14)
                symbol_df["atr_50"] = compute_atr(symbol_df["high"], symbol_df["low"], symbol_df["close"], 50)
                symbol_df["adx"] = compute_adx(symbol_df["high"], symbol_df["low"], symbol_df["close"])

                # Volume indicators
                symbol_df["volume_sma_20"] = compute_volume_ma(symbol_df["volume"], 20)
                symbol_df["volume_ratio"] = symbol_df["volume"] / symbol_df["volume_sma_20"]

                results.append(symbol_df)

            except Exception as e:
                logger.warning(f"Failed to compute indicators for {symbol}: {e}")
                continue

        if not results:
            return pd.DataFrame()

        full_df = pd.concat(results, ignore_index=True)
        return full_df

    def _fetch_spy_prices(self, start_date: date, end_date: date) -> dict:
        """Cache SPY prices for mansfield_rs calculation."""
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT date, close FROM price_daily "
                "WHERE symbol = 'SPY' AND date >= %s AND date <= %s "
                "ORDER BY date",
                (start_date, end_date)
            )
            return {row[0]: float(row[1]) for row in cur.fetchall()}

    def _bulk_insert(self, df: pd.DataFrame) -> int:
        """Insert indicators using COPY."""
        if df.empty:
            return 0

        # Prepare columns
        columns = [
            "symbol", "date", "rsi", "rsi_14", "macd", "macd_signal",
            "macd_hist", "macd_histogram", "mom", "roc", "roc_10d",
            "roc_20d", "roc_60d", "roc_120d", "roc_252d", "sma_10",
            "sma_20", "sma_50", "sma_200", "bb_upper", "bb_middle",
            "bb_lower", "atr_14", "atr_50", "adx", "volume_sma_20",
            "volume_ratio"
        ]

        # Ensure columns exist
        for col in columns:
            if col not in df.columns:
                df[col] = None

        insert_df = df[columns].copy()
        insert_df["date"] = pd.to_datetime(insert_df["date"]).dt.date.astype(str)

        with DatabaseContext("write") as cur:
            cur.execute(f"LOCK TABLE {self.table_name} IN EXCLUSIVE MODE")

            import io
            import csv

            buffer = io.StringIO()
            insert_df.to_csv(buffer, index=False, header=False, quoting=csv.QUOTE_MINIMAL)
            buffer.seek(0)

            cur.copy_from(buffer, self.table_name, columns=columns, null="")
            logger.info(f"Inserted {len(insert_df)} rows via COPY")

            return len(insert_df)


if __name__ == "__main__":
    backfiller = BackfillTechnicalData()
    result = backfiller.run()

    if result["status"] == "success":
        print(f"✓ Backfilled {result['rows_inserted']} rows")
        sys.exit(0)
    else:
        print(f"✗ Backfill failed: {result.get('error')}")
        sys.exit(1)
