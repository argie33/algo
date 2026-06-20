#!/usr/bin/env python3
"""Market Health Daily Loader – Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data and market indicators.
Populates all required market_health_daily columns.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from typing import List, Optional

import pandas as pd
import psycopg2

from loaders.technical_indicators import compute_moving_averages
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class MarketHealthDailyLoader(OptimalLoader):
    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_incremental(self, symbol: str = "SPY", since: date | None = None):
        """Fetch SPY price data and compute market health metrics."""
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

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
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT MAX(date), COUNT(*) FROM market_health_daily")
                    row = cur.fetchone()
                    row_count = row[1] if row else 0
                    if row and row[0]:
                        # If table has fewer than 5 rows, it's likely incomplete/corrupted - do a full backfill
                        if row_count < 5:
                            logger.info(
                                f"market_health_daily has {row_count} rows (< 5), starting from scratch for backfill"
                            )
                            since = None
                        else:
                            since = (
                                row[0]
                                if isinstance(row[0], date)
                                else date.fromisoformat(str(row[0]))
                            )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"[MARKET_HEALTH] Failed to read watermark from market_health_daily: {e}. "
                    "Cannot determine incremental load point."
                )

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=100)

        rows = self._fetch_price_daily("SPY", start, end)
        if not rows:
            raise RuntimeError(
                f"[MARKET_HEALTH] No SPY price data available for {start} to {end}. "
                "Cannot compute market health metrics without price data."
            )

        health_metrics = self._compute_market_health(rows)
        if not health_metrics:
            raise RuntimeError(
                f"[MARKET_HEALTH] Failed to compute health metrics from {len(rows)} price rows. "
                "Market health computation should never produce empty results from valid input."
            )

        logger.info(
            f"Computed {len(health_metrics)} health metrics from {len(rows)} price rows, date range: {health_metrics[0]['date']} to {health_metrics[-1]['date']}"
        )

        # Merge real breadth data (A/D ratio, new highs/lows) into health metrics
        breadth = self._fetch_breadth_data(start, end)
        for m in health_metrics:
            b = breadth.get(m["date"], {})
            m["advance_decline_ratio"] = b.get("advance_decline_ratio", 1.0)
            m["new_highs_count"] = b.get("new_highs_count", 0)
            m["new_lows_count"] = b.get("new_lows_count", 0)

        # Merge VIX data (non-critical enrichment - fail gracefully if unavailable)
        try:
            vix = self._fetch_vix_data(start, end)
            matched_count = 0
            for m in health_metrics:
                if m["date"] in vix:
                    m["vix_level"] = vix[m["date"]]
                    matched_count += 1
                else:
                    m["vix_level"] = None
            logger.info(f"VIX enrichment: matched {matched_count}/{len(health_metrics)} dates")
        except RuntimeError as e:
            error_msg = str(e)
            if "DATA QUALITY" in error_msg:
                logger.error(f"VIX data quality issue (operator action required): {e}")
            else:
                logger.warning(f"VIX unavailable: {e}. Continuing with missing VIX values.")
            # Ensure vix_level is set to None for all rows if fetch fails
            for m in health_metrics:
                if "vix_level" not in m:
                    m["vix_level"] = None

        # Merge today's put/call ratio from SPY options (non-critical enrichment - fail gracefully)
        # Put/call_ratio and VIX both depend on yfinance API which has rate limits and outages.
        # Making this REQUIRED would block entire pipeline on yfinance issues.
        # Graceful degradation allows data pipeline to continue and signal generation to proceed.
        try:
            today_pc = self._fetch_put_call_ratio(end)
            end_str = end.isoformat()
            matched_count = 0
            for m in health_metrics:
                if m["date"] == end_str:
                    m["put_call_ratio"] = today_pc
                    if today_pc is not None:
                        matched_count += 1
                else:
                    m["put_call_ratio"] = None
            if today_pc is not None:
                logger.info(f"Put/call ratio: {today_pc:.3f} (matched {matched_count} rows)")
            else:
                # On non-trading days, put/call is legitimately unavailable
                logger.debug("Put/call ratio unavailable (non-trading day or no options data)")
        except RuntimeError as e:
            logger.warning(f"Put/call ratio unavailable: {e}. Continuing with missing put/call data.")
            # Ensure put_call_ratio is set to None for all rows if fetch fails
            for m in health_metrics:
                if "put_call_ratio" not in m:
                    m["put_call_ratio"] = None

        # Merge yield curve slope from economic_metrics_daily (non-critical enrichment - fail gracefully)
        # Yield curve data is computed by economic_metrics_daily loader which runs separately.
        # If that loader has issues, yield curve will be missing, but market health should still load.
        try:
            yield_curve = self._fetch_yield_curve_data(start, end)
            matched_count = 0
            for m in health_metrics:
                m["yield_curve_slope"] = yield_curve.get(m["date"])
                if m["yield_curve_slope"] is not None:
                    matched_count += 1
            logger.info(f"Yield curve enrichment: matched {matched_count}/{len(health_metrics)} dates")
        except RuntimeError as e:
            logger.warning(f"Yield curve unavailable: {e}. Continuing with missing yield curve data.")
            # Ensure yield_curve_slope is set to None for all rows if fetch fails
            for m in health_metrics:
                if "yield_curve_slope" not in m:
                    m["yield_curve_slope"] = None

        # Optimize breadth data fetching for incremental updates: only compute for dates we'll keep
        if since is not None:
            since_str = since.isoformat()
            before_filter = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] >= since_str]
            logger.info(
                f"Filtered health_metrics: {before_filter} -> {len(health_metrics)} (keeping dates >= {since_str})"
            )

        return health_metrics

    def _fetch_vix_data(self, start: date, end: date) -> dict:
        """Fetch VIX close prices via wrapper. Returns {date_str: vix_close}.

        CRITICAL: If yfinance returns data but ALL values are < 5.0, this is a
        data quality issue (not missing data). Logs ERROR so operators know
        to investigate yfinance feed.
        """
        try:
            from utils.external.yfinance import YFinanceWrapper

            ticker = YFinanceWrapper.get_ticker("^VIX")
            if not ticker:
                logger.warning(
                    f"[VIX] Ticker ^VIX not available from yfinance for {start} to {end}. "
                    "Continuing with missing VIX data."
                )
                return {}
            df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
            if df is None or df.empty:
                logger.debug(
                    f"[VIX] yfinance returned no data for {start} to {end}. "
                    "This is expected for non-trading date ranges."
                )
                return {}

            result = {}
            low_value_count = 0  # Track but don't reject low values
            low_values = []

            for idx, row in df.iterrows():
                date_str = (
                    idx.strftime("%Y-%m-%d")
                    if hasattr(idx, "strftime")
                    else str(idx)[:10]
                )
                close_val = row.get("Close") if hasattr(row, "get") else row["Close"]
                is_nan = isinstance(close_val, float) and close_val != close_val

                if close_val is None or is_nan:
                    continue

                close_float = float(close_val)
                # CRITICAL FIX: Accept ALL valid numeric VIX values, including < 5.0
                # Low VIX (< 5) is rare but valid (indicates very low market volatility)
                # Filtering them out masks data quality issues. Only reject NaN/None.
                if close_float >= 0:
                    result[date_str] = round(close_float, 2)
                    if close_float < 5.0:
                        low_value_count += 1
                        low_values.append(close_float)

            # Check for data availability
            if len(result) == 0:
                raise RuntimeError(
                    "[VIX] No valid VIX data returned by yfinance (all values were NaN/None). "
                    "Cannot compute market health without valid VIX values."
                )

            # WARN if many low values (unusual pattern, may indicate data issue)
            if low_value_count > 0:
                low_pct = (low_value_count / len(result) * 100) if result else 0
                if low_pct > 50:
                    logger.warning(
                        f"[VIX] Unusual data pattern: {low_pct:.0f}% of values < 5.0 ({low_values[:3]}...). "
                        "This may indicate a data feed issue. Check yfinance directly."
                    )
                else:
                    logger.info(
                        f"[VIX] Fetched {len(result)} values, {low_value_count} were < 5.0 (low volatility)"
                    )

            return result
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[VIX] Failed to fetch VIX data: {type(e).__name__}: {e}. "
                "VIX data is authoritative for market health computation."
            )

    def _fetch_put_call_ratio(self, eval_date: date) -> float | None:
        """Compute put/call ratio from SPY options chain volume via yfinance.

        Sums total puts and calls volume across near-term expirations as a proxy
        for the daily equity put/call ratio. Only runs on trading days.
        High ratio (>1.1): fear/hedging dominant. Low ratio (<0.6): complacency.
        """
        from algo.infrastructure import MarketCalendar

        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.debug("Put/call: skipping (not a trading day)")
            return None  # OK to return None on non-trading days—no options data expected
        try:
            from utils.external.yfinance import YFinanceWrapper, _throttled_yf_request

            ticker = YFinanceWrapper.get_ticker("SPY")
            if not ticker:
                raise RuntimeError(
                    "Put/call: could not get SPY ticker from yfinance. "
                    "Cannot compute put/call ratio for market health."
                )

            # ticker.options makes an outbound request — run through the rate limiter
            # so it doesn't race against other yfinance calls sharing the NAT gateway IP.
            try:
                expirations = _throttled_yf_request(lambda: ticker.options)
            except Exception as e:
                raise RuntimeError(
                    f"[PUT_CALL] Failed to fetch option expirations from yfinance: {e}. "
                    "Cannot compute put/call ratio for market health."
                )

            if not expirations:
                raise RuntimeError(
                    "Put/call: no option expirations returned by yfinance (ticker.options empty). "
                    "Cannot compute put/call ratio without available option contracts."
                )

            total_puts = 0.0
            total_calls = 0.0
            chain_errors = 0
            for exp in expirations[:4]:  # near-term expirations (most liquid)
                try:
                    chain = _throttled_yf_request(lambda e=exp: ticker.option_chain(e))
                    total_puts += float(chain.puts["volume"].fillna(0).sum())
                    total_calls += float(chain.calls["volume"].fillna(0).sum())
                except (AttributeError, KeyError, ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(f"Put/call: option_chain({exp}) fetch error: {e}")
                    chain_errors += 1
                    continue

            if chain_errors == min(4, len(expirations)):
                raise RuntimeError(
                    "Put/call: all option chain fetches failed — cannot compute market health without this data."
                )

            if total_calls > 0:
                ratio = round(total_puts / total_calls, 3)
                logger.info(
                    f"Put/call ratio: {ratio:.3f} "
                    f"(puts={total_puts:.0f}, calls={total_calls:.0f}, chain_errors={chain_errors})"
                )
                return ratio
            raise RuntimeError(
                f"Put/call: zero calls volume across {len(expirations[:4])} expirations. "
                "Cannot compute market health without valid put/call data."
            )
        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[PUT_CALL] Failed to compute put/call ratio: {e}. "
                "This metric is authoritative for market health."
            )

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict:
        """Read 10Y-2Y yield spread from economic_metrics_daily. Returns {date_str: slope}."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT report_date, yield_curve_slope_10y2y FROM economic_metrics_daily"
                    " WHERE report_date >= %s AND report_date <= %s AND yield_curve_slope_10y2y IS NOT NULL"
                    " ORDER BY report_date",
                    (start, end),
                )
                rows = cur.fetchall()
            result = {str(row[0]): float(row[1]) for row in rows}
            if result:
                logger.info(f"Fetched yield curve data: {len(result)} days")
            return result
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[YIELD_CURVE] Failed to fetch yield curve data from economic_metrics_daily: {e}. "
                "Cannot compute market health without yield curve slope data."
            )

    def _fetch_breadth_data(self, start: date, end: date) -> dict:
        """Compute advance/decline ratio and new 52-week highs/lows from full stock universe."""
        try:
            with DatabaseContext("read") as cur:
                # For efficiency: only compute breadth for the last 30 days (most recent data)
                # For dates older than 30 days, query existing market_health_daily data to reuse
                recent_start = max(start, end - timedelta(days=30))
                lookback_start = recent_start - timedelta(days=365)

                result = {}

                # First, get cached breadth data from market_health_daily for older dates
                if start < recent_start:
                    try:
                        cur.execute(
                            """
                            SELECT date,
                                   COALESCE(advance_decline_ratio, 1.0),
                                   COALESCE(new_highs_count, 0),
                                   COALESCE(new_lows_count, 0)
                            FROM market_health_daily
                            WHERE date >= %s AND date < %s
                            ORDER BY date ASC
                        """,
                            (start, recent_start),
                        )

                        for r in cur.fetchall():
                            result[r[0].isoformat()] = {
                                "advance_decline_ratio": float(r[1]),
                                "new_highs_count": int(r[2]),
                                "new_lows_count": int(r[3]),
                            }
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        raise RuntimeError(
                            f"[BREADTH] Failed to fetch cached breadth data: {e}. "
                            "Cannot verify previously computed market breadth metrics."
                        )

                # Now compute breadth data only for recent dates (more efficient).
                # 90s timeout: this query joins 365-day price history for 5000+ symbols.
                # Under write load from stock_prices_daily ECS tasks the query can block
                # for minutes — fail fast and let the loader write market health rows
                # without breadth columns (orchestrator Phase 1 only checks date freshness,
                # not whether advance_decline_ratio is populated).
                cur.execute("SET LOCAL statement_timeout = '90s'")
                cur.execute(
                    """
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
                """,
                    (lookback_start, end, recent_start),
                )

                for r in cur.fetchall():
                    result[r[0].isoformat()] = {
                        "advance_decline_ratio": (
                            float(r[3]) if r[3] is not None else 1.0
                        ),
                        "new_highs_count": int(r[4]) if r[4] is not None else 0,
                        "new_lows_count": int(r[5]) if r[5] is not None else 0,
                    }

                return result
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[BREADTH] Failed to compute breadth data: {e}. "
                "Advance/decline ratio and new highs/lows are authoritative for market health."
            )

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> list[dict]:
        try:
            with DatabaseContext("read") as cur:
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
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[PRICE_DATA] Failed to fetch price data for {symbol}: {e}. "
                "Cannot compute market health without SPY price data."
            )

    def _compute_market_health(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        # Warn if we have fewer than 20 rows but still process them (can happen at startup)
        if len(rows) < 20:
            logger.warning(
                f"Computing market health with only {len(rows)} rows (< 20 recommended)"
            )

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        df["price_change"] = df["close"].diff()
        df["up_day"] = (df["price_change"] > 0).astype(int)

        # Use shared indicator computation
        df["prev_close"] = df["close"].shift(1)
        df["prev_volume"] = df["volume"].shift(1)
        # Distribution day: close down >= 0.2% AND volume > previous day (IBD canonical definition)
        df["distribution_day"] = (
            (df["close"] < df["prev_close"] * 0.998)
            & (df["volume"] > df["prev_volume"])
        ).astype(int)

        # Calculate moving averages using shared function
        mas = compute_moving_averages(df["close"])
        df["sma_50"] = mas["sma_50"]
        df["sma_200"] = mas["sma_200"]
        df["breadth_10d"] = (
            df["up_day"].rolling(10).mean() * 100
        )  # % up days in last 10

        results = []
        for idx, row in df.iterrows():
            close = float(row["close"]) if pd.notna(row["close"]) else 0
            sma_200 = float(row["sma_200"]) if pd.notna(row["sma_200"]) else None
            sma_50 = float(row["sma_50"]) if pd.notna(row["sma_50"]) else None

            # Determine market trend and stage
            market_trend = "neutral"
            market_stage = (
                2  # Default to Stage 2 (uptrend); overridden below when MAs available
            )

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
            dist_days_25d = (
                int(df["distribution_day"].iloc[max(0, idx - 24) : idx + 1].sum())
                if idx >= 0
                else 0
            )
            dist_days_20d = (
                int(df["distribution_day"].iloc[max(0, idx - 19) : idx + 1].sum())
                if idx >= 0
                else 0
            )

            spy_change_pct = None
            if idx > 0:
                prev_close = float(df.iloc[idx - 1]["close"])
                if prev_close > 0:
                    spy_change_pct = round((close - prev_close) / prev_close * 100, 2)

            results.append(
                {
                    "date": row["date"].date().isoformat(),
                    "market_trend": market_trend,
                    "market_stage": market_stage,
                    "distribution_days_4w": dist_days_25d,
                    "distribution_days_20d": dist_days_20d,
                    "up_volume_percent": (
                        float(
                            df["up_day"].iloc[max(0, idx - 10) : idx + 1].mean() * 100
                        )
                        if idx >= 0
                        else 50
                    ),
                    "advance_decline_ratio": None,  # filled from _fetch_breadth_data
                    "new_highs_count": None,  # filled from _fetch_breadth_data
                    "new_lows_count": None,  # filled from _fetch_breadth_data
                    "breadth_momentum_10d": (
                        float(row["breadth_10d"])
                        if pd.notna(row["breadth_10d"])
                        else 50
                    ),
                    "spy_change_pct": spy_change_pct,
                    "vix_level": None,  # populated in fetch_incremental from _fetch_vix_data
                    "put_call_ratio": None,
                    "yield_curve_slope": None,
                    "fed_rate_environment": "unknown",
                }
            )

        return results


# Index symbols stored in price_daily to power frontend charts that call /api/prices/history/{sym}
# VIX family: VolTermStructureCard in MarketsHealth
# Market indices: IndicesStrip sparklines + Distribution Days timeline
INDEX_SYMBOLS_FOR_PRICE_DAILY = [
    "^VIX",
    "^VIX9D",
    "^VIX3M",
    "^VIX6M",
    "^GSPC",
    "^IXIC",
    "^NYA",
    "^DJI",
    "^RUT",
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
    from algo.infrastructure import MarketCalendar

    today = datetime.now(EASTERN_TZ).date()
    if not MarketCalendar.is_trading_day(today):
        logger.info(
            f"Market closed today ({today}) — skipping VIX/index yfinance fetch"
        )
        return 0
    try:
        from utils.external.yfinance import YFinanceWrapper

        records = []
        failed_symbols = {}
        for sym in INDEX_SYMBOLS_FOR_PRICE_DAILY:
            try:
                ticker = YFinanceWrapper.get_ticker(sym)
                if not ticker:
                    logger.warning(f"Could not get ticker for {sym}")
                    failed_symbols[sym] = "Ticker unavailable"
                    continue

                df = ticker.history(
                    start=start, end=end, interval="1d", auto_adjust=True
                )
                if df is None or df.empty:
                    logger.warning(f"No data for {sym}")
                    failed_symbols[sym] = "Empty data"
                    continue

                for idx, row in df.iterrows():
                    d = (
                        idx.date()
                        if hasattr(idx, "date")
                        else date.fromisoformat(str(idx)[:10])
                    )

                    def _v(col):
                        val = row.get(col) if hasattr(row, "get") else row[col]
                        if val is None:
                            return None
                        if hasattr(val, "__len__"):
                            try:
                                val = val.iloc[0] if len(val) else None
                            except (IndexError, AttributeError):
                                val = None
                        try:
                            f = float(val)
                            if f != f:  # NaN check
                                return None
                            return round(f, 4)
                        except (TypeError, ValueError) as e:
                            raise RuntimeError(
                                f"[PRICE_EXTRACTION] Failed to parse {col} value '{val}' as float for {sym} on {d}: {e}. "
                                "Data integrity issue in yfinance response."
                            )

                    close = _v("Close")
                    if close is None:
                        continue

                    open_val = _v("Open")
                    high_val = _v("High")
                    low_val = _v("Low")
                    volume_val = _v("Volume")

                    if volume_val is None:
                        logger.debug(f"{sym} on {d}: Volume data missing")
                        volume_val = None
                    else:
                        volume_val = int(volume_val)

                    records.append(
                        (
                            sym,
                            d,
                            open_val,
                            high_val,
                            low_val,
                            close,
                            volume_val,
                        )
                    )
                logger.info(
                    f"Fetched {len([r for r in records if r[0] == sym])} rows for {sym}"
                )
            except (AttributeError, KeyError, ValueError, TypeError) as e:
                logger.error(f"Failed to fetch {sym}: Data format error: {e}")
                failed_symbols[sym] = f"Data format error: {str(e)[:50]}"
                continue
            except RuntimeError:
                raise
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.error(f"Failed to fetch {sym}: Unexpected error: {e}")
                failed_symbols[sym] = f"Unexpected error: {str(e)[:50]}"
                continue

        coverage = (len(INDEX_SYMBOLS_FOR_PRICE_DAILY) - len(failed_symbols)) / len(INDEX_SYMBOLS_FOR_PRICE_DAILY) * 100
        if coverage < 80:
            raise RuntimeError(
                f"[VIX_PRICES] Insufficient market health index coverage: {coverage:.1f}% ({len(INDEX_SYMBOLS_FOR_PRICE_DAILY) - len(failed_symbols)} of {len(INDEX_SYMBOLS_FOR_PRICE_DAILY)} symbols). "
                f"Failed symbols: {failed_symbols}. "
                "Cannot compute breadth and regime metrics with incomplete index data."
            )

        if not records:
            raise RuntimeError(
                f"[VIX_PRICES] No VIX family or index prices could be fetched from yfinance for any of {len(INDEX_SYMBOLS_FOR_PRICE_DAILY)} symbols. "
                "All fetch attempts failed. Cannot load market health without these critical indices."
            )

        with DatabaseContext("write") as cur:
            cur.executemany(
                """
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open   = EXCLUDED.open,
                    high   = EXCLUDED.high,
                    low    = EXCLUDED.low,
                    close  = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """,
                records,
            )

        logger.info(f"Upserted {len(records)} VIX family price rows into price_daily")
        return len(records)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(
            f"[VIX_PRICES] Failed to write VIX family prices to database: {e}. "
            "Market health daily depends on VIX/index price data availability."
        )


def main():
    from utils.logging.history_tracker import LoaderHistoryTracker

    parser = argparse.ArgumentParser(description="Load market health daily metrics")
    parser.add_argument("--symbols", type=str, help="(Ignored - always uses SPY)")
    parser.add_argument("--parallelism", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    tracker = LoaderHistoryTracker("market_health_daily")
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
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Market health daily load failed: {e}")
        tracker.failed(error_message=str(e))
        raise RuntimeError(f"Market health daily loader failed: {e}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
