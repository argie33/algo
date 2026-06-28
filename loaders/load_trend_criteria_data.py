#!/usr/bin/env python3
"""Trend Criteria Data Loader -â€ Minervini 8-point, Weinstein stage, consolidation.

Computes trend confirmation metrics from price and technical data.
Required by Phase 1 data freshness check.

Run: python3 load_trend_criteria_data.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date, timedelta
from typing import Any

import pandas as pd
import psycopg2

from loaders.runner import run_loader
from loaders.technical_indicators import compute_moving_averages
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class TrendCriteriaLoader(OptimalLoader):
    table_name = "trend_template_data"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def _prepare_batch_context(self) -> None:
        """Cache max price date once per run (avoids one SELECT per symbol)."""
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()

        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                    (end,),
                )
                row = cur.fetchone()
                max_price_date = row[0] if row and row[0] is not None else None
                if max_price_date and max_price_date < end:
                    logger.info(
                        f"[TrendCriteria] Price data only available to {max_price_date}, using that as end date"
                    )
                    end = max_price_date
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[TrendCriteria] Failed to query max price date from database: {e}. "
                "Cannot determine batch context without authoritative price data availability."
            ) from e

        self._batch_context = {"end_date": end}

    def fetch_incremental(self, symbol: str, since: date | None = None) -> list[dict[str, Any]]:
        # CRITICAL: Batch context MUST exist — fail fast if missing
        # Never fall back to per-symbol recomputation; all symbols in batch must use same end_date
        if not self._batch_context:
            raise RuntimeError(
                f"[TrendCriteria] Batch context not initialized for {symbol}. "
                "Batch context must be populated in _prepare_batch_context() before fetch_incremental(). "
                "Cannot compute trend criteria with missing batch context — indicates loader initialization failure."
            )
        if "end_date" not in self._batch_context:
            raise RuntimeError(
                f"[TrendCriteria] Batch context missing 'end_date' key for {symbol}. "
                f"Available keys: {list(self._batch_context.keys())}. "
                "All symbols must use the same batch end_date. "
                "Check _prepare_batch_context() implementation."
            )

        end = self._batch_context["end_date"]

        # When since is None (e.g. first call after an ECS task restart), read the actual
        # DB max date to skip recomputing years of already-loaded history. Without this,
        # every ECS run would re-fetch 2 years x all symbols - matching the fix applied to
        # MarketHealthDailyLoader in commit 97230793b.
        if since is None:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM trend_template_data WHERE symbol = %s",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"[TrendCriteria] Failed to read watermark for {symbol}: {e}. "
                    "Cannot determine incremental load point without authoritative database state."
                ) from e

        if since is None:
            start = end - timedelta(days=2 * 365)
        else:
            # Keep 300-day lookback so moving averages (50d, 150d, 200d) are warm before
            # the incremental window starts â€" avoids NaN MAs at the boundary.
            start = since - timedelta(days=300)

        rows = self._fetch_price_daily(symbol, start, end)
        # Allow symbols with at least 20 days of data (early in trading history)
        # Very new stocks with < 20 days return empty results (optional data)
        if not rows or len(rows) < 20:
            logger.debug(f"[TrendCriteria] Skipping {symbol}: insufficient price data ({len(rows) if rows else 0} rows, need >= 20)")
            return []

        results = self._compute_trend_criteria(symbol, rows)
        if since is not None:
            since_str = since.isoformat()
            results = [r for r in results if r["date"] > since_str]

        return results

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT date, close, volume FROM price_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start, end),
            )
            rows = cur.fetchall()
            if not rows:
                # Return empty list for symbols with no price data (delisted, invalid tickers, etc.)
                return []
            return [
                {
                    "date": r[0].isoformat() if r[0] else None,
                    "close": float(r[1]) if r[1] is not None else None,
                    "volume": int(r[2]) if r[2] is not None else None,
                }
                for r in rows
            ]

    def _compute_trend_criteria(self, symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:  # noqa: C901
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        close = df["close"]
        # Use shared moving average computation
        mas = compute_moving_averages(close)
        df["sma_50"] = mas["sma_50"]
        df["sma_150"] = mas["sma_150"]
        df["sma_200"] = mas["sma_200"]

        # Compute slopes (not in shared function)
        # CRITICAL: Avoid division by zero - replace zero shift values with NaN before dividing
        # This prevents inf/NaN from silently corrupting slope calculations
        sma_50_shifted = df["sma_50"].shift(5).replace(0, None)
        sma_200_shifted = df["sma_200"].shift(5).replace(0, None)
        df["sma_50_slope"] = df["sma_50"].diff(5) / sma_50_shifted
        df["sma_200_slope"] = df["sma_200"].diff(5) / sma_200_shifted

        # 52-week highs/lows (custom, not in shared function)
        df["high_52w"] = close.rolling(252).max()
        df["low_52w"] = close.rolling(252).min()

        results = []
        for idx in range(len(df)):
            row = df.iloc[idx]
            c = row["close"]
            if c is None or pd.isna(c):
                continue

            sma50 = row["sma_50"] if pd.notna(row["sma_50"]) else None
            sma150 = row["sma_150"] if pd.notna(row["sma_150"]) else None
            sma200 = row["sma_200"] if pd.notna(row["sma_200"]) else None
            high52 = row["high_52w"] if pd.notna(row["high_52w"]) else None
            low52 = row["low_52w"] if pd.notna(row["low_52w"]) else None

            # Minervini 8-point trend score
            score = 0
            if sma50 and c > sma50:
                score += 1
            if sma150 and c > sma150:
                score += 1
            if sma200 and c > sma200:
                score += 1
            if sma50 and sma150 and sma50 > sma150:
                score += 1
            if sma150 and sma200 and sma150 > sma200:
                score += 1
            sma200_slope = row["sma_200_slope"]
            if sma200_slope and pd.notna(sma200_slope) and sma200_slope > 0:
                score += 1
            if high52 and c >= high52 * 0.75:
                score += 1
            if low52 and c >= low52 * 1.30:
                score += 1

            # Weinstein stage (1=base, 2=advancing, 3=top, 4=declining)
            sma200_slope_val = row["sma_200_slope"]
            if sma200 and c > sma200:
                if pd.notna(sma200_slope_val) and sma200_slope_val > 0:
                    weinstein_stage = 2  # advancing: above rising 200 MA
                else:
                    weinstein_stage = 3  # topping: above flat/falling 200 MA
            else:
                if pd.notna(sma200_slope_val) and sma200_slope_val < 0:
                    weinstein_stage = 4  # declining: below falling 200 MA
                else:
                    weinstein_stage = 1  # basing: below flat/rising 200 MA

            pct_from_low = ((c - low52) / low52 * 100) if low52 else None
            pct_from_high = ((c - high52) / high52 * 100) if high52 else None

            # Consolidation: price within 10% range over 10 days
            if idx >= 10:
                recent = df["close"].iloc[idx - 10 : idx + 1]
                if recent.isna().any():
                    consolidation = None
                else:
                    mean_price = recent.mean()
                    if mean_price > 0:
                        rng = (recent.max() - recent.min()) / mean_price
                        consolidation = bool(rng < 0.10)
                    else:
                        consolidation = None
            else:
                consolidation = None

            trend_dir = "uptrend" if score >= 6 else ("downtrend" if score <= 2 else "sideways")

            # Skip rows where SMAs aren't available yet (early in symbol's trading history)
            # This is common for newly listed stocks that don't have 200 days of price data yet
            if sma50 is None or sma200 is None:
                continue
            if sma50 <= 0 or sma200 <= 0:
                raise RuntimeError(
                    f"[TREND_CRITERIA] {symbol} [{row['date'].date().isoformat()}]: "
                    f"Invalid SMA values (must be positive). sma_50={sma50}, sma_200={sma200}. "
                    f"Prices cannot be zero or negative. Check price_daily for invalid entries."
                )

            # CRITICAL: Validate SMA slope values exist before using in result
            # NaN values corrupt technical indicators; must be explicit None instead
            sma50_slope_val = row["sma_50_slope"]
            if pd.isna(sma50_slope_val):
                sma50_slope = None
            else:
                sma50_slope = round(float(sma50_slope_val), 4)

            sma200_slope_val = row["sma_200_slope"]
            if pd.isna(sma200_slope_val):
                sma200_slope = None
            else:
                sma200_slope = round(float(sma200_slope_val), 4)

            results.append(
                {
                    "symbol": symbol,
                    "date": row["date"].date().isoformat(),
                    "price_52w_high": round(float(high52), 4) if high52 else None,
                    "price_52w_low": round(float(low52), 4) if low52 else None,
                    "percent_from_52w_low": (round(float(pct_from_low), 2) if pct_from_low is not None else None),
                    "percent_from_52w_high": (round(float(pct_from_high), 2) if pct_from_high is not None else None),
                    "sma_50_slope": sma50_slope,
                    "sma_200_slope": sma200_slope,
                    "price_above_sma50": bool(c > sma50),
                    "price_above_sma200": bool(c > sma200),
                    "sma50_above_sma200": bool(sma50 > sma200),
                    "ma_spread_percent": round(float((sma50 - sma200) / sma200 * 100), 4),
                    "minervini_trend_score": score,
                    "weinstein_stage": weinstein_stage,
                    "trend_direction": trend_dir,
                    "consolidation_flag": consolidation,
                }
            )

        return results


if __name__ == "__main__":
    sys.exit(run_loader(TrendCriteriaLoader))
