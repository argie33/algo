#!/usr/bin/env python3
"""Trend Criteria Data Loader -â€ Minervini 8-point, Weinstein stage, consolidation.

Computes trend confirmation metrics from price and technical data.
Required by Phase 1 data freshness check.

Run: python3 load_trend_criteria_data.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import os
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

import logging
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext
from utils.loader_config import get_parallelism, get_default_parallelism
from loaders.technical_indicators import compute_moving_averages

logger = logging.getLogger(__name__)

class TrendCriteriaLoader(OptimalLoader):
    table_name = "trend_template_data"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date] = None):
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td
        from zoneinfo import ZoneInfo

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        # FIXED: Use ZoneInfo instead of hardcoded -5 offset to handle EDT properly.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        end = now_et.date()

        # If today is not a trading day, use yesterday instead
        # (prevents computing criteria for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # When since is None (e.g. first call after an ECS task restart), read the actual
        # DB max date to skip recomputing years of already-loaded history. Without this,
        # every ECS run would re-fetch 2 years x all symbols - matching the fix applied to
        # MarketHealthDailyLoader in commit 97230793b.
        if since is None:
            try:
                with DatabaseContext('read') as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM trend_template_data WHERE symbol = %s",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except Exception as e:
                logger.warning(f"Could not read trend_template_data watermark for {symbol}: {e}")

        if since is None:
            start = end - timedelta(days=2 * 365)
        else:
            # Keep 300-day lookback so moving averages (50d, 150d, 200d) are warm before
            # the incremental window starts â€" avoids NaN MAs at the boundary.
            start = since - timedelta(days=300)

        rows = self._fetch_price_daily(symbol, start, end)
        if not rows or len(rows) < 50:
            return []

        results = self._compute_trend_criteria(symbol, rows)
        if since is not None:
            since_str = since.isoformat()
            results = [r for r in results if r["date"] > since_str]

        return results

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT date, close, volume FROM price_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat() if r[0] else None,
                        "close": float(r[1]) if r[1] is not None else None,
                        "volume": int(r[2]) if r[2] is not None else None,
                    }
                    for r in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to fetch price data for {symbol}: {e}")
            return []

    def _compute_trend_criteria(self, symbol: str, rows: List[dict]) -> List[dict]:
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        close = df["close"]
        # Use shared moving average computation
        mas = compute_moving_averages(close)
        df["sma_50"] = mas['sma_50']
        df["sma_150"] = mas['sma_150']
        df["sma_200"] = mas['sma_200']

        # Compute slopes (not in shared function)
        df["sma_50_slope"] = df["sma_50"].diff(5) / df["sma_50"].shift(5)
        df["sma_200_slope"] = df["sma_200"].diff(5) / df["sma_200"].shift(5)

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
                recent = df["close"].iloc[idx-10:idx+1]
                mean_price = recent.mean()
                rng = (recent.max() - recent.min()) / mean_price if mean_price > 0 else 999.0
                consolidation = bool(rng < 0.10)
            else:
                consolidation = False

            trend_dir = "uptrend" if score >= 6 else ("downtrend" if score <= 2 else "sideways")

            results.append({
                "symbol": symbol,
                "date": row["date"].date().isoformat(),
                "price_52w_high": round(float(high52), 4) if high52 else None,
                "price_52w_low": round(float(low52), 4) if low52 else None,
                "percent_from_52w_low": round(float(pct_from_low), 2) if pct_from_low is not None else None,
                "percent_from_52w_high": round(float(pct_from_high), 2) if pct_from_high is not None else None,
                "sma_50_slope": round(float(row["sma_50_slope"]), 4) if pd.notna(row.get("sma_50_slope", float("nan"))) else None,
                "sma_200_slope": round(float(row["sma_200_slope"]), 4) if pd.notna(row.get("sma_200_slope", float("nan"))) else None,
                "price_above_sma50": bool(c > sma50) if sma50 else None,
                "price_above_sma200": bool(c > sma200) if sma200 else None,
                "sma50_above_sma200": bool(sma50 > sma200) if (sma50 and sma200) else None,
                "ma_spread_percent": round(float((sma50 - sma200) / sma200 * 100), 4) if (sma50 and sma200) else None,
                "minervini_trend_score": score,
                "weinstein_stage": weinstein_stage,
                "trend_direction": trend_dir,
                "consolidation_flag": consolidation,
            })

        return results

def main():
    parser = argparse.ArgumentParser(description="Load trend criteria data")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=get_default_parallelism("trend_criteria_data"), help="Parallel workers")
    args = parser.parse_args()

    try:
        symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)
        loader = TrendCriteriaLoader()
        loader.run(symbols, parallelism=args.parallelism)
        logger.info("Trend criteria data load completed")
        return 0
    except Exception as e:
        logger.error(f"Trend criteria data load failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

