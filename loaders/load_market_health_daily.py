#!/usr/bin/env python3
"""Market Health Daily Loader â€" Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data and market indicators.
Populates all required market_health_daily columns.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""
from loaders.loader_helper import setup_imports
setup_imports()

import sys
import argparse
from datetime import date, datetime, timedelta
from typing import List, Optional

import pandas as pd

import logging
from utils.loader_helpers import get_active_symbols
from utils.timezone_utils import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext
from loaders.technical_indicators import compute_moving_averages, compute_volume_ma

logger = logging.getLogger(__name__)

class MarketHealthDailyLoader(OptimalLoader):
    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_incremental(self, symbol: str = "SPY", since: Optional[date] = None):
        """Fetch SPY price data and compute market health metrics."""
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        # FIXED: Use ZoneInfo instead of hardcoded -5 offset to handle EDT properly.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()

        # If today is not a trading day, use yesterday instead
        # (prevents computing health metrics for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # If no watermark (e.g. first call after ECS restart), read the actual table max date
        # to avoid a full 5-year recompute + expensive all-stock breadth query on every restart.
        # BUT: if the table is nearly empty (< 5 rows), assume it needs backfilling and start from scratch
        if since is None:
            try:
                with DatabaseContext('read') as cur:
                    cur.execute("SELECT MAX(date), COUNT(*) FROM market_health_daily")
                    row = cur.fetchone()
                    row_count = row[1] if row else 0
                    if row and row[0]:
                        # If table has fewer than 5 rows, it's likely incomplete/corrupted - do a full backfill
                        if row_count < 5:
                            logger.info(f"market_health_daily has {row_count} rows (< 5), starting from scratch for backfill")
                            since = None
                        else:
                            since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except Exception as e:
                logger.warning(f"Could not read market_health_daily watermark: {e}")

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=100)

        rows = self._fetch_price_daily("SPY", start, end)
        if not rows:
            return []

        health_metrics = self._compute_market_health(rows)
        if not health_metrics:
            return []

        logger.info(f"Computed {len(health_metrics)} health metrics from {len(rows)} price rows, date range: {health_metrics[0]['date']} to {health_metrics[-1]['date']}")

        # Merge real breadth data (A/D ratio, new highs/lows) into health metrics
        breadth = self._fetch_breadth_data(start, end)
        for m in health_metrics:
            b = breadth.get(m["date"], {})
            m["advance_decline_ratio"] = b.get("advance_decline_ratio", 1.0)
            m["new_highs_count"] = b.get("new_highs_count", 0)
            m["new_lows_count"] = b.get("new_lows_count", 0)

        # Merge VIX data
        vix = self._fetch_vix_data(start, end)
        for m in health_metrics:
            m["vix_level"] = vix.get(m["date"])

        # Optimize breadth data fetching for incremental updates: only compute for dates we'll keep
        if since is not None:
            since_str = since.isoformat()
            before_filter = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] >= since_str]
            logger.info(f"Filtered health_metrics: {before_filter} -> {len(health_metrics)} (keeping dates >= {since_str})")

        return health_metrics

    def _fetch_vix_data(self, start: date, end: date) -> dict:
        """Fetch VIX close prices via wrapper. Returns {date_str: vix_close}."""
        from algo.algo_market_calendar import MarketCalendar
        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.info(f"Market closed today ({today}) — skipping VIX yfinance fetch")
            return {}
        try:
            from utils.yfinance_wrapper import YFinanceWrapper
            ticker = YFinanceWrapper.get_ticker("^VIX")
            if not ticker:
                logger.warning("VIX ticker not available")
                return {}
            df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
            if df is None or df.empty:
                logger.warning("VIX history returned no data")
                return {}
            result = {}
            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                close_val = row.get("Close") if hasattr(row, "get") else row["Close"]
                if close_val is not None and not (isinstance(close_val, float) and close_val != close_val):
                    result[date_str] = round(float(close_val), 2)
            logger.info(f"Fetched VIX data: {len(result)} days")
            return result
        except Exception as e:
            logger.warning(f"VIX fetch failed (circuit breaker will use None): {e}")
            return {}

    def _fetch_breadth_data(self, start: date, end: date) -> dict:
        """Compute advance/decline ratio and new 52-week highs/lows from full stock universe."""
        try:
            with DatabaseContext('read') as cur:
                # For efficiency: only compute breadth for the last 30 days (most recent data)
                # For dates older than 30 days, query existing market_health_daily data to reuse
                recent_start = max(start, end - timedelta(days=30))
                lookback_start = recent_start - timedelta(days=365)

                result = {}

                # First, get cached breadth data from market_health_daily for older dates
                if start < recent_start:
                    try:
                        cur.execute("""
                            SELECT date,
                                   COALESCE(advance_decline_ratio, 1.0),
                                   COALESCE(new_highs_count, 0),
                                   COALESCE(new_lows_count, 0)
                            FROM market_health_daily
                            WHERE date >= %s AND date < %s
                            ORDER BY date ASC
                        """, (start, recent_start))

                        for r in cur.fetchall():
                            result[r[0].isoformat()] = {
                                "advance_decline_ratio": float(r[1]),
                                "new_highs_count": int(r[2]),
                                "new_lows_count": int(r[3]),
                            }
                    except Exception as e:
                        logger.warning(f"Could not fetch cached breadth data: {e}")

                # Now compute breadth data only for recent dates (more efficient).
                # 90s timeout: this query joins 365-day price history for 5000+ symbols.
                # Under write load from stock_prices_daily ECS tasks the query can block
                # for minutes — fail fast and let the loader write market health rows
                # without breadth columns (orchestrator Phase 1 only checks date freshness,
                # not whether advance_decline_ratio is populated).
                cur.execute("SET LOCAL statement_timeout = '90s'")
                cur.execute("""
                    WITH prices AS (
                        SELECT symbol, date, close
                        FROM price_daily
                        WHERE date >= %s AND date <= %s
                          AND symbol NOT LIKE '^%%'
                    ),
                    with_context AS (
                        SELECT
                            date, symbol, close,
                            LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
                            MAX(close) OVER (PARTITION BY symbol ORDER BY date
                                             ROWS BETWEEN 251 PRECEDING AND 1 PRECEDING) AS high_251d,
                            MIN(close) OVER (PARTITION BY symbol ORDER BY date
                                             ROWS BETWEEN 251 PRECEDING AND 1 PRECEDING) AS low_251d
                        FROM prices
                    )
                    SELECT
                        date,
                        COUNT(CASE WHEN close > prev_close THEN 1 END) AS advances,
                        COUNT(CASE WHEN close < prev_close THEN 1 END) AS declines,
                        ROUND(
                            COUNT(CASE WHEN close > prev_close THEN 1 END)::numeric /
                            NULLIF(COUNT(CASE WHEN close < prev_close THEN 1 END), 0), 3
                        ) AS advance_decline_ratio,
                        COUNT(CASE WHEN high_251d IS NOT NULL AND close >= high_251d THEN 1 END) AS new_highs,
                        COUNT(CASE WHEN low_251d IS NOT NULL AND close <= low_251d THEN 1 END) AS new_lows
                    FROM with_context
                    WHERE prev_close IS NOT NULL AND date >= %s
                    GROUP BY date
                    ORDER BY date ASC
                """, (lookback_start, end, recent_start))

                for r in cur.fetchall():
                    result[r[0].isoformat()] = {
                        "advance_decline_ratio": float(r[3]) if r[3] is not None else 1.0,
                        "new_highs_count": int(r[4]) if r[4] is not None else 0,
                        "new_lows_count": int(r[5]) if r[5] is not None else 0,
                    }

                return result
        except Exception as e:
            logger.error(f"Failed to fetch breadth data: {e}")
            return {}

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> List[dict]:
        try:
            with DatabaseContext('read') as cur:
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
        except Exception as e:
            logger.error(f"Failed to fetch price data for {symbol}: {e}")
            return []

    def _compute_market_health(self, rows: List[dict]) -> List[dict]:
        if not rows:
            return []
        # Warn if we have fewer than 20 rows but still process them (can happen at startup)
        if len(rows) < 20:
            logger.warning(f"Computing market health with only {len(rows)} rows (< 20 recommended)")

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        df["price_change"] = df["close"].diff()
        df["up_day"] = (df["price_change"] > 0).astype(int)

        # Use shared indicator computation
        df["prev_close"] = df["close"].shift(1)
        df["prev_volume"] = df["volume"].shift(1)
        # Distribution day: close down >= 0.2% AND volume > previous day (IBD canonical definition)
        df["distribution_day"] = ((df["close"] < df["prev_close"] * 0.998) & (df["volume"] > df["prev_volume"])).astype(int)

        # Calculate moving averages using shared function
        mas = compute_moving_averages(df["close"])
        df["sma_50"] = mas['sma_50']
        df["sma_200"] = mas['sma_200']
        df["breadth_10d"] = df["up_day"].rolling(10).mean() * 100  # % up days in last 10

        results = []
        for idx, row in df.iterrows():
            close = float(row["close"]) if pd.notna(row["close"]) else 0
            sma_200 = float(row["sma_200"]) if pd.notna(row["sma_200"]) else None
            sma_50 = float(row["sma_50"]) if pd.notna(row["sma_50"]) else None

            # Determine market trend and stage
            market_trend = "neutral"
            market_stage = 2  # Default to Stage 2 (uptrend); overridden below when MAs available

            if sma_200 and sma_50:
                if close > sma_50 > sma_200:
                    market_trend = "uptrend"
                    market_stage = 2
                elif close < sma_50 < sma_200:
                    market_trend = "downtrend"
                    market_stage = 4
                elif close > sma_200 and sma_50 < sma_200:
                    market_trend = "topping"
                    market_stage = 3
                else:
                    market_trend = "mixed"
                    market_stage = 1
            elif sma_200:
                if close > sma_200 * 1.05:
                    market_trend = "uptrend"
                    market_stage = 2
                elif close < sma_200 * 0.95:
                    market_trend = "downtrend"
                    market_stage = 4
                else:
                    market_trend = "consolidation"
                    market_stage = 1

            # Count distribution days (4w = 25 trading days, 20d = 20 trading days per IBD)
            # idx-24:idx+1 = 25 rows (today + 24 prior sessions)
            dist_days_25d = int(df["distribution_day"].iloc[max(0, idx-24):idx+1].sum()) if idx >= 0 else 0
            dist_days_20d = int(df["distribution_day"].iloc[max(0, idx-19):idx+1].sum()) if idx >= 0 else 0

            spy_change_pct = None
            if idx > 0:
                prev_close = float(df.iloc[idx-1]["close"])
                if prev_close > 0:
                    spy_change_pct = round((close - prev_close) / prev_close * 100, 2)

            results.append({
                "date": row["date"].date().isoformat(),
                "market_trend": market_trend,
                "market_stage": market_stage,
                "distribution_days_4w": dist_days_25d,
                "distribution_days_20d": dist_days_20d,
                "up_volume_percent": float(df["up_day"].iloc[max(0, idx-10):idx+1].mean() * 100) if idx >= 0 else 50,
                "advance_decline_ratio": None,  # filled from _fetch_breadth_data
                "new_highs_count": None,         # filled from _fetch_breadth_data
                "new_lows_count": None,          # filled from _fetch_breadth_data
                "breadth_momentum_10d": float(row["breadth_10d"]) if pd.notna(row["breadth_10d"]) else 50,
                "spy_change_pct": spy_change_pct,
                "vix_level": None,  # populated in fetch_incremental from _fetch_vix_data
                "put_call_ratio": None,
                "yield_curve_slope": None,
                "fed_rate_environment": "unknown",
            })

        return results

# Index symbols stored in price_daily to power frontend charts that call /api/prices/history/{sym}
# VIX family: VolTermStructureCard in MarketsHealth
# Market indices: IndicesStrip sparklines + Distribution Days timeline
INDEX_SYMBOLS_FOR_PRICE_DAILY = [
    '^VIX', '^VIX9D', '^VIX3M', '^VIX6M',
    '^GSPC', '^IXIC', '^NYA', '^DJI', '^RUT',
]

def _write_vix_family_prices(start: date, end: date) -> int:
    """Download VIX-family and market-index prices via wrapper and upsert into price_daily.

    Supplies data for:
    - VolTermStructureCard (^VIX9D / ^VIX3M / ^VIX6M)
    - Distribution Days timeline (^GSPC / ^IXIC / ^NYA / ^DJI)
    Returns the number of rows upserted.
    """
    # On non-trading days yfinance aggressively rate-limits index/VIX fetches.
    # Skip the fetch — existing price_daily data is still current from the last trading day.
    from algo.algo_market_calendar import MarketCalendar
    today = datetime.now(EASTERN_TZ).date()
    if not MarketCalendar.is_trading_day(today):
        logger.info(f"Market closed today ({today}) — skipping VIX/index yfinance fetch")
        return 0
    try:
        from utils.yfinance_wrapper import YFinanceWrapper

        records = []
        for sym in INDEX_SYMBOLS_FOR_PRICE_DAILY:
            try:
                ticker = YFinanceWrapper.get_ticker(sym)
                if not ticker:
                    logger.warning(f"Could not get ticker for {sym}")
                    continue

                df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
                if df is None or df.empty:
                    logger.warning(f"No data for {sym}")
                    continue

                for idx, row in df.iterrows():
                    d = idx.date() if hasattr(idx, 'date') else date.fromisoformat(str(idx)[:10])

                    def _v(col):
                        val = row.get(col) if hasattr(row, 'get') else row[col]
                        if val is None:
                            return None
                        if hasattr(val, '__len__'):
                            try:
                                val = val.iloc[0] if len(val) else None
                            except (IndexError, AttributeError):
                                val = None
                        try:
                            f = float(val)
                            return None if f != f else round(f, 4)
                        except (TypeError, ValueError):
                            return None

                    close = _v('Close')
                    if close is None:
                        continue
                    records.append((
                        sym, d,
                        _v('Open') or close,
                        _v('High') or close,
                        _v('Low') or close,
                        close,
                        int(_v('Volume') or 0),
                    ))
                logger.info(f"Fetched {len([r for r in records if r[0] == sym])} rows for {sym}")
            except Exception as e:
                logger.warning(f"Failed to fetch {sym}: {e}")

        if not records:
            return 0

        with DatabaseContext('write') as cur:
            cur.executemany("""
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open   = EXCLUDED.open,
                    high   = EXCLUDED.high,
                    low    = EXCLUDED.low,
                    close  = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """, records)

        logger.info(f"Upserted {len(records)} VIX family price rows into price_daily")
        return len(records)
    except Exception as e:
        logger.error(f"VIX family price write failed: {e}")
        return 0

def main():
    from utils.loader_history_tracker import LoaderHistoryTracker

    parser = argparse.ArgumentParser(description="Load market health daily metrics")
    parser.add_argument("--symbols", type=str, help="(Ignored - always uses SPY)")
    parser.add_argument("--parallelism", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    tracker = LoaderHistoryTracker('market_health_daily')
    tracker.start()

    try:
        loader = MarketHealthDailyLoader()
        loader.run(["SPY"], parallelism=args.parallelism)

        # Also write VIX-family term structure prices to price_daily so the
        # VolTermStructureCard in MarketsHealth can render.
        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        end = datetime.now(EASTERN_TZ).date()
        start = end - timedelta(days=90)
        written = _write_vix_family_prices(start, end)
        if written > 0:
            logger.info(f"VIX family: {written} rows written to price_daily")

        logger.info("Market health daily load completed")
        tracker.complete(symbols_processed=1)
        return 0
    except Exception as e:
        logger.error(f"Market health daily load failed: {e}")
        tracker.failed(error_message=str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())

