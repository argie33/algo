#!/usr/bin/env python3
"""Technical Data Daily Loader â€" RSI, MACD, SMA, EMA, ATR, Bollinger Bands.

Computes all technical indicators from daily price data and populates technical_data_daily.
Required by Phase 1 data freshness check.

Run: python3 load_technical_data_daily.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import psycopg2
import psycopg2.sql
from pandas.tseries.offsets import CustomBusinessDay

from loaders.runner import run_loader
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
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.safe_data_conversion import safe_float


logger = logging.getLogger(__name__)


class TechnicalDataDailyLoader(OptimalLoader):
    table_name = "technical_data_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: date | None):
        from datetime import datetime

        from algo.infrastructure import MarketCalendar

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()

        # If today is not a trading day, use yesterday instead
        # (prevents computing indicators for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Read the actual DB max date to avoid re-fetching 5 years of history.
        if since is None:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM technical_data_daily WHERE symbol = %s",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        since = (
                            row[0]
                            if isinstance(row[0], date)
                            else date.fromisoformat(str(row[0]))
                        )
            except (psycopg2.Error, ValueError) as e:
                raise RuntimeError(
                    f"[WATERMARK] Failed to read watermark for {symbol}: {e}. "
                    "Cannot determine incremental load point—cannot proceed."
                ) from e

        if since is None:
            # On ECS restart, load last 60 days only (not 5 years)
            # SMA-200 needs ~230 days; we keep buffer for safety
            # This prevents massive data fetch when watermark is empty
            start = end - timedelta(days=60)
        else:
            # Keep 300-day lookback so long moving averages (SMA 200) stay warm.
            start = since - timedelta(days=300)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows:
            raise RuntimeError(
                f"[TECHNICAL_DATA] No price data available for {symbol} from {start} to {end}. "
                "Cannot compute technical indicators without price history."
            )

        spy_rows = self._fetch_price_daily("SPY", start, end) if symbol != "SPY" else []
        indicators = self._compute_all_indicators(symbol, rows, spy_rows)
        if not indicators:
            raise RuntimeError(
                f"[TECHNICAL_DATA] Failed to compute technical indicators for {symbol}. "
                "Indicator computation returned empty result despite valid input data. "
                "Check indicator calculation functions for errors."
            )

        if since is not None:
            since_str = since.isoformat()
            indicators = [ind for ind in indicators if ind["date"] > since_str]

        return indicators

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> list[dict]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, open, high, low, close, volume FROM price_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                rows = []
                skipped_count = 0
                for r in cur.fetchall():
                    # Validate: reject zero-price or zero-volume rows (data errors or halted stocks)
                    close = safe_float(r[4], default=0.0) if r[4] is not None else None
                    volume = int(r[5]) if r[5] is not None else None

                    if close is None or close <= 0:
                        skipped_count += 1
                        logger.debug(
                            f"{symbol} [{r[0]}]: Row skipped — invalid close price "
                            f"(close={close} — expected > 0)"
                        )
                        continue
                    if volume is not None and volume == 0:
                        skipped_count += 1
                        logger.debug(
                            f"{symbol} [{r[0]}]: Row skipped — zero volume "
                            "(stock halted/no trading)"
                        )
                        continue

                    rows.append(
                        {
                            "date": r[0].isoformat() if r[0] else None,
                            "open": safe_float(r[1], default=0.0) if r[1] is not None else None,
                            "high": safe_float(r[2], default=0.0) if r[2] is not None else None,
                            "low": safe_float(r[3], default=0.0) if r[3] is not None else None,
                            "close": close,
                            "volume": volume,
                        }
                    )
                if skipped_count > 0:
                    logger.warning(
                        f"{symbol}: Skipped {skipped_count} row(s) due to invalid/missing "
                        f"price or volume data — {len(rows)} valid row(s) returned"
                    )
                return rows
        except psycopg2.Error as e:
            raise RuntimeError(
                f"[PRICE_DATA] Failed to fetch price data for {symbol} [{start} to {end}]: {e}. "
                "Cannot compute technical indicators without price history."
            ) from e
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[PRICE_DATA] Invalid data format for {symbol}: {e}. "
                "Price data may be corrupted."
            ) from e

    def _calculate_data_source_age_days(self, symbol: str, source_table: str) -> int:
        """Calculate age of most recent data in source table (in trading days).

        Returns:
            Trading days since most recent row in source table. Returns -1 if no data found or error.
        """
        try:
            with DatabaseContext("read") as cur:
                table_safe = assert_safe_table(source_table)
                cur.execute(
                    psycopg2.sql.SQL(
                        "SELECT MAX(date) FROM {} WHERE symbol = %s"
                    ).format(psycopg2.sql.Identifier(table_safe)),
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    max_date = (
                        row[0]
                        if isinstance(row[0], date)
                        else date.fromisoformat(str(row[0]))
                    )
                    from algo.infrastructure import MarketCalendar

                    # Count trading days from max_date to today
                    # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
                    trading_days = 0
                    check_date = datetime.now(EASTERN_TZ).date() - timedelta(days=1)
                    while check_date > max_date and trading_days < 999:
                        if MarketCalendar.is_trading_day(check_date):
                            trading_days += 1
                        check_date -= timedelta(days=1)

                    return trading_days
                return -1
        except psycopg2.Error as e:
            logger.warning(f"Database error calculating {source_table} age for {symbol}: {e}")
            return -1
        except (ValueError, TypeError) as e:
            logger.warning(f"Data format error calculating {source_table} age for {symbol}: {e}")
            return -1

    def _compute_all_indicators(
        self, symbol: str, rows: list[dict], spy_rows: list[dict] | None = None
    ) -> list[dict]:
        if not rows:
            raise RuntimeError(
                f"[TECHNICAL_DATA] Empty price data passed to indicator computation for {symbol}. "
                "Cannot compute technical indicators without price history."
            )
        if len(rows) < 50:
            raise RuntimeError(
                f"[TECHNICAL_DATA] Insufficient price history for {symbol}: {len(rows)} rows available, "
                "need >=50 days to compute meaningful technical indicators (SMA-200, RSI, MACD require lookback). "
                "Cannot proceed without adequate historical data."
            )

        # Precalculate source data age once per symbol (not per indicator row)
        price_data_age = self._calculate_data_source_age_days(symbol, "price_daily")

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Filter out identical OHLC rows (API-limit fallback/stale data)
        # These rows have open == high == low == close and indicate no real trading
        initial_len = len(df)
        df = df[
            ~(
                (df["open"] == df["high"])
                & (df["high"] == df["low"])
                & (df["low"] == df["close"])
            )
        ]
        if len(df) < initial_len:
            filtered_count = initial_len - len(df)
            logger.debug(
                f"[{symbol}] Filtered out {filtered_count} rows with identical OHLC (API-limit fallback data)"
            )

        # Compute all technical indicators required by schema
        df["rsi_14"] = compute_rsi(df["close"], 14)
        df["rsi"] = df["rsi_14"]  # Schema has both rsi and rsi_14

        df["macd"], df["macd_signal"] = compute_macd(df["close"])
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        df["macd_histogram"] = df["macd_hist"]  # Schema has both names

        # Momentum and rate of change (clamped to DECIMAL(8,4) range: Â±9999.9999)
        df["mom"] = df["close"].diff()
        df["roc"] = df["close"].pct_change() * 100
        df["roc_10d"] = df["close"].pct_change(10) * 100
        df["roc_20d"] = df["close"].pct_change(20) * 100
        df["roc_60d"] = df["close"].pct_change(60) * 100
        df["roc_120d"] = df["close"].pct_change(120) * 100
        df["roc_252d"] = df["close"].pct_change(252) * 100

        # Clamp ROC values to database field limits to prevent overflow
        _decimal84_max = 9999.9999
        roc_cols = ["roc", "roc_10d", "roc_20d", "roc_60d", "roc_120d", "roc_252d"]
        for col in roc_cols:
            before = df[col].copy()
            df[col] = df[col].clip(-_decimal84_max, _decimal84_max)
            capped_count = ((before.abs() > _decimal84_max) & (df[col].notna())).sum()
            if capped_count > 0:
                logger.warning(
                    f"{symbol}: {capped_count} {col} values capped to ±{_decimal84_max} (extreme market conditions)"
                )

        mas = compute_moving_averages(df["close"])
        for name, values in mas.items():
            df[name] = values

        df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], 14)
        df["atr"] = df["atr_14"]  # Schema has both atr and atr_14

        df["plus_di"], df["minus_di"], df["adx"] = compute_adx(
            df["high"], df["low"], df["close"], 14
        )

        # Mansfield Relative Strength: (rs_line / 52wk_ma_of_rs_line - 1) * 100
        # rs_line = close / spy_close; requires SPY prices aligned to same dates
        if spy_rows:
            import numpy as np

            from algo.infrastructure.market_calendar import US_HOLIDAYS

            spy_df = pd.DataFrame(spy_rows)
            spy_df["date"] = pd.to_datetime(spy_df["date"])
            spy_closes = spy_df.set_index("date")["close"]

            holidays = list(US_HOLIDAYS.keys())
            cbd = CustomBusinessDay(holidays=holidays)
            target_index = pd.DatetimeIndex(df["date"].values, freq=cbd)
            spy_aligned = spy_closes.reindex(target_index)

            # Defensive check: zero or NaN SPY prices would cause division by zero
            if (spy_aligned == 0).any() or spy_aligned.isna().all():
                logger.warning(
                    f"[{symbol}] SPY alignment invalid (zeros or all NaN) — cannot compute Mansfield RS"
                )
                df["mansfield_rs"] = None
            else:
                # Forward-fill NaN values from missing SPY dates to avoid division by zero
                spy_filled = spy_aligned.fillna(method='pad')
                rs_line = df["close"].values / spy_filled.values
                rs_line_s = pd.Series(rs_line, index=df.index)
                # Replace infinities with NaN
                rs_line_s = rs_line_s.replace([np.inf, -np.inf], np.nan)

                rs_line_52w_ma = rs_line_s.rolling(window=252, min_periods=126).mean()

                # Defensive check: if rolling mean is all NaN, can't compute ratio
                if rs_line_52w_ma.isna().all():
                    logger.debug(
                        f"[{symbol}] Insufficient RS history for 52-week MA (need 126+ days)"
                    )
                    df["mansfield_rs"] = None
                else:
                    # Only compute where both rs_line and its MA are valid (avoid NaN division)
                    mansfield_result = (rs_line_s / rs_line_52w_ma - 1) * 100
                    # Replace infinities with NaN (safeguard against edge cases)
                    mansfield_result = mansfield_result.replace([np.inf, -np.inf], np.nan)
                    df["mansfield_rs"] = mansfield_result
        else:
            df["mansfield_rs"] = None

        bbs = compute_bollinger_bands(df["close"], 20, 2.0)
        for name, values in bbs.items():
            df[name] = values

        df["volume_ma_50"] = compute_volume_ma(df["volume"], 50)
        df["symbol"] = symbol
        df["price_data_age_days"] = price_data_age

        columns = [
            "symbol",
            "date",
            "rsi",
            "rsi_14",
            "macd",
            "macd_signal",
            "macd_hist",
            "macd_histogram",
            "mom",
            "roc",
            "roc_10d",
            "roc_20d",
            "roc_60d",
            "roc_120d",
            "roc_252d",
            "sma_20",
            "sma_50",
            "sma_150",
            "sma_200",
            "ema_12",
            "ema_21",
            "ema_26",
            "atr",
            "atr_14",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "volume_ma_50",
            "adx",
            "plus_di",
            "minus_di",
            "mansfield_rs",
            "price_data_age_days",
            "close",
        ]

        df["date"] = df["date"].dt.date.astype(str)

        def safe_float(v):
            return safe_float(v, default=0.0) if pd.notna(v) else None

        for col in columns[2:]:
            if col not in ("price_data_age_days",):
                df[col] = df[col].apply(safe_float)

        records = df[columns].to_dict("records")

        # pandas converts int+None Series to float64 (e.g. 6887014 → 6887014.0).
        # volume_ma_50 and price_data_age_days are integers in the schema — fix after to_dict.
        import math

        for r in records:
            vma = r.get("volume_ma_50")
            if isinstance(vma, float):
                r["volume_ma_50"] = round(vma) if not math.isnan(vma) else None

            # price_data_age_days is already an integer (set once per symbol)
            age = r.get("price_data_age_days")
            if age is not None and not isinstance(age, int):
                r["price_data_age_days"] = int(age) if isinstance(age, float) else age

        return records



if __name__ == "__main__":
    sys.exit(run_loader(TechnicalDataDailyLoader))
