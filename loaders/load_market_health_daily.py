#!/usr/bin/env python3
"""Market Health Daily Loader - Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data and market indicators.
Populates all required market_health_daily columns.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import psycopg2

from loaders.market_health_fetchers import (
    BreadthFetcher,
    PutCallRatioFetcher,
    VIXFetcher,
    YieldCurveFetcher,
)
from loaders.technical_indicators import compute_moving_averages
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class MarketHealthDailyLoader(OptimalLoader):
    """Market health metrics loader.

    Uses specialized fetchers for VIX, put/call, yield curve, breadth data.
    CRITICAL: SPY prices, VIX, yield curve (all required for regime detection)
    OPTIONAL: Put/call ratio (enrichment, non-critical)
    """

    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Initialize fetchers for specialized data sources
        self._vix_fetcher = VIXFetcher()
        self._put_call_fetcher = PutCallRatioFetcher()
        self._yield_curve_fetcher = YieldCurveFetcher()
        self._breadth_fetcher = BreadthFetcher()

    def fetch_vix_with_breaker(self, start: date, end: date) -> dict[str, Any]:
        """Fetch VIX data with circuit breaker protection."""
        return self._vix_fetcher.fetch(start, end)

    def fetch_put_call_with_breaker(self, eval_date: date) -> float | None:
        """Fetch put/call ratio with circuit breaker protection."""
        return self._put_call_fetcher.fetch(eval_date)

    def fetch_yield_curve_with_breaker(self, start: date, end: date) -> dict[str, Any]:
        """Fetch yield curve data with circuit breaker protection."""
        return self._yield_curve_fetcher.fetch(start, end)

    def _get_end_date(self) -> date:
        """Determine end date (latest trading day in ET)."""
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)
        return end

    def _get_start_date(self, end: date, since: date | None) -> date:
        """Determine start date based on watermark or backfill logic.

        Note: market_health_daily is date-only (not symbol-based), so we ignore
        OptimalLoader's per-symbol watermark logic and query directly.
        """
        if since is None:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT MAX(date), COUNT(*) FROM market_health_daily")
                    row = cur.fetchone()
                    row_count = row[1] if row else 0
                    if row and row[0]:
                        if row_count < 5:
                            logger.info(
                                f"market_health_daily has {row_count} rows (< 5), starting from scratch for backfill"
                            )
                            since = None
                        else:
                            since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"[MARKET_HEALTH] Failed to read watermark from market_health_daily: {e}. "
                    "Cannot determine incremental load point."
                ) from e

        if since is None:
            return end - timedelta(days=5 * 365)
        return since - timedelta(days=100)

    def load_symbol(self, symbol: str) -> int:
        """Override OptimalLoader.load_symbol to bypass symbol-based watermarking.

        market_health_daily is date-only, not symbol-based. We fetch incremental
        data and bypass the parent's per-symbol watermark logic entirely.
        """
        previous_date = None
        if self._backfill_days > 0:
            previous_date = datetime.now(timezone.utc).date() - timedelta(days=self._backfill_days)
        else:
            # Use our custom date logic instead of per-symbol watermark
            previous_date = None  # Will be computed by _get_start_date

        try:
            rows = self.fetch_incremental(symbol, previous_date)
        except Exception as e:
            raise RuntimeError(f"[{self.table_name}] {symbol}: Failed to fetch: {e}") from e

        if not rows:
            logger.info(f"[{self.table_name}] No incremental data available for {symbol} - will retry on next run")
            return 1  # Return error code (1) for no data available, will retry on next pipeline run

        # Transform and insert
        transformed = self.transform(rows)
        written = self._bulk_insert_mgr.bulk_insert(transformed)

        # Update stats
        watermark = self.watermark_from_rows(transformed)
        if watermark:
            self._stats.set("watermark", watermark)
        self._stats.increment("rows_inserted", len(transformed))

        return written

    def _merge_breadth_data(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge breadth data into health metrics. Breadth data is optional enrichment.

        If breadth data is unavailable, leaves advance_decline_ratio/new_highs_count/new_lows_count as None.
        These fields can be populated later or remain None without blocking market health calculation.
        """
        breadth = self._breadth_fetcher.fetch(start, end)
        if not breadth:
            logger.info("Breadth data unavailable (optional) - proceeding without advance/decline enrichment")
            return

        matched_count = 0
        for m in health_metrics:
            b = breadth.get(m["date"])
            if b is not None:
                m["advance_decline_ratio"] = b.get("advance_decline_ratio")
                m["new_highs_count"] = b.get("new_highs_count")
                m["new_lows_count"] = b.get("new_lows_count")
                matched_count += 1

        if matched_count > 0:
            logger.info(f"Breadth enrichment: matched {matched_count}/{len(health_metrics)} dates")
        else:
            logger.info("Breadth data available but no date matches found - skipping enrichment")

    def _merge_vix_data(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge VIX data into health metrics.

        VIX fetcher returns dict with vix_close/high/low; we extract vix_close as the level.
        Forward-fill missing VIX dates using the most recent available value (standard market data practice).
        VIX is CRITICAL for circuit breaker logic and must be present.
        """
        vix = self._vix_fetcher.fetch(start, end)
        if not isinstance(vix, dict) or len(vix) == 0:
            raise RuntimeError(
                f"[MARKET_HEALTH] VIX data unavailable or empty for {start} to {end}. "
                "VIX is CRITICAL for circuit breaker halt decisions. "
                "Cannot compute market health metrics without valid VIX data."
            )

        matched_count = 0
        last_vix_level = None

        for m in health_metrics:
            if m["date"] in vix:
                # VIX fetcher returns {'vix_close': float, 'vix_high': float, 'vix_low': float}
                vix_data = vix[m["date"]]
                vix_close = vix_data.get("vix_close") if isinstance(vix_data, dict) else vix_data
                if vix_close is not None:
                    m["vix_level"] = vix_close
                    last_vix_level = vix_close
                    matched_count += 1
                elif last_vix_level is not None:
                    # Forward-fill from previous day
                    m["vix_level"] = last_vix_level
                    matched_count += 1
            elif last_vix_level is not None:
                # Forward-fill missing date with most recent VIX level
                m["vix_level"] = last_vix_level
                matched_count += 1

        if matched_count > 0:
            logger.info(f"VIX enrichment: matched {matched_count}/{len(health_metrics)} dates (forward-filled missing dates)")
        else:
            logger.warning("VIX data available but no valid vix_close values found")

    def _merge_put_call_data(self, health_metrics: list[dict[str, Any]], end: date) -> None:
        """Merge put/call ratio into health metrics."""
        today_pc = self._put_call_fetcher.fetch(end)
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
            logger.debug("Put/call ratio unavailable (optional enrichment skipped)")

    def _merge_yield_curve_data(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge yield curve slope into health metrics.

        Yield curve slope is used for market regime detection. Forward-fill missing dates
        using the most recent available yield curve slope (standard financial data practice).
        """
        try:
            yield_curve = self._yield_curve_fetcher.fetch(start, end)
            if not yield_curve:
                logger.warning("Yield curve data unavailable - proceeding without slope enrichment")
                return

            matched_count = 0
            last_slope = None

            for m in health_metrics:
                slope_data = yield_curve.get(m["date"])
                if slope_data is not None:
                    slope = slope_data.get("yield_spread")
                    if slope is not None:
                        m["yield_curve_slope"] = slope
                        last_slope = slope
                        matched_count += 1
                    elif last_slope is not None:
                        # Forward-fill from previous available date
                        m["yield_curve_slope"] = last_slope
                        matched_count += 1
                elif last_slope is not None:
                    # Forward-fill missing date with most recent yield curve slope
                    m["yield_curve_slope"] = last_slope
                    matched_count += 1

            if matched_count > 0:
                logger.info(f"Yield curve enrichment: matched {matched_count}/{len(health_metrics)} dates (forward-filled missing dates)")
            else:
                logger.warning("Yield curve data available but no valid slopes found")
        except Exception as e:
            logger.warning(f"Yield curve enrichment failed (optional): {e}. Proceeding without slope enrichment.")
            # Don't raise - yield curve slope is enrichment, not critical

    def fetch_incremental(self, symbol: str = "SPY", since: date | None = None) -> list[dict[str, Any]]:
        """Fetch SPY price data and compute market health metrics."""
        end = self._get_end_date()
        start = self._get_start_date(end, since)

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

        date_start = health_metrics[0]["date"]
        date_end = health_metrics[-1]["date"]
        logger.info(f"Computed {len(health_metrics)} metrics from {len(rows)} rows, range: {date_start} to {date_end}")

        self._merge_breadth_data(health_metrics, start, end)
        self._merge_vix_data(health_metrics, start, end)
        self._merge_put_call_data(health_metrics, end)
        self._merge_yield_curve_data(health_metrics, start, end)

        # Optimize breadth data fetching for incremental updates: only compute for dates we'll keep
        if since is not None:
            since_str = since.isoformat()
            before_filter = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] >= since_str]
            logger.info(
                f"Filtered health_metrics: {before_filter} -> {len(health_metrics)} (keeping dates >= {since_str})"
            )

        return health_metrics

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> list[dict[str, float | int | str | None]]:
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
            ) from e

    def _compute_market_health(self, rows: list[dict[str, float | int | None | str]]) -> list[dict[str, Any]]:
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
        df["distribution_day"] = ((df["close"] < df["prev_close"] * 0.998) & (df["volume"] > df["prev_volume"])).astype(
            int
        )

        # Calculate moving averages using shared function
        mas = compute_moving_averages(df["close"])
        df["sma_50"] = mas["sma_50"]
        df["sma_200"] = mas["sma_200"]
        df["breadth_10d"] = df["up_day"].rolling(10, min_periods=1).mean() * 100  # % up days in last 10

        results = []
        for idx, row in df.iterrows():
            if not pd.notna(row["close"]) or row["close"] <= 0:
                logger.warning(f"Market health: Invalid close price for {row.get('date', 'unknown')}: {row['close']}; skipping row")
                continue
            close = float(row["close"])
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
            if idx < 0:
                raise RuntimeError(
                    f"Market health computation failed: invalid index {idx}. "
                    "Cannot compute distribution days without valid row index."
                )
            dist_days_25d = int(df["distribution_day"].iloc[max(0, idx - 24) : idx + 1].sum())
            dist_days_20d = int(df["distribution_day"].iloc[max(0, idx - 19) : idx + 1].sum())

            spy_change_pct = None
            if idx > 0:
                prev_close = float(df.iloc[idx - 1]["close"])
                if prev_close > 0:
                    spy_change_pct = round((close - prev_close) / prev_close * 100, 2)

            up_volume_pct = float(df["up_day"].iloc[max(0, idx - 10) : idx + 1].mean() * 100)
            if pd.isna(up_volume_pct):
                raise RuntimeError(
                    f"Market health computation failed for {row.get('date', 'unknown')}: "
                    "cannot compute up_volume_percent (NaN result). Data quality issue in up_day calculation."
                )

            if pd.isna(row["breadth_10d"]):
                raise RuntimeError(
                    f"Market health computation failed for {row.get('date', 'unknown')}: "
                    "breadth_momentum_10d is NaN. Cannot proceed without valid breadth data."
                )

            results.append(
                {
                    "date": row["date"].date().isoformat(),
                    "market_trend": market_trend,
                    "market_stage": market_stage,
                    "distribution_days_4w": dist_days_25d,
                    "distribution_days_20d": dist_days_20d,
                    "up_volume_percent": up_volume_pct,
                    "advance_decline_ratio": None,  # filled from _merge_breadth_data
                    "new_highs_count": None,  # filled from _merge_breadth_data
                    "new_lows_count": None,  # filled from _merge_breadth_data
                    "breadth_momentum_10d": float(row["breadth_10d"]),
                    "spy_change_pct": spy_change_pct,
                    "vix_level": None,  # populated in fetch_incremental from _merge_vix_data
                    "put_call_ratio": None,
                    "yield_curve_slope": None,
                    "fed_rate_environment": None,
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
    # Skip the fetch - existing price_daily data is still current from the last trading day.
    from algo.infrastructure import MarketCalendar

    today = datetime.now(EASTERN_TZ).date()
    if not MarketCalendar.is_trading_day(today):
        logger.info(f"Market closed today ({today}) - skipping VIX/index yfinance fetch")
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

                df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
                if df is None or df.empty:
                    logger.warning(f"No data for {sym}")
                    failed_symbols[sym] = "Empty data"
                    continue

                for idx, row in df.iterrows():
                    d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])

                    def _v(col: str, row: Any = row, sym: str = sym, d: date = d) -> float | None:
                        val: Any = row.get(col) if hasattr(row, "get") else row[col]
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
                                f"[PRICE_EXTRACTION] Failed to parse {col}={val!r} for {sym}: {e}"
                            ) from e

                    close = _v("Close")
                    if close is None:
                        raise RuntimeError(
                            f"[MARKET_HEALTH] Missing close price for {sym} on {d} — "
                            "cannot compute market health metrics without OHLCV data"
                        )

                    open_val = _v("Open")
                    high_val = _v("High")
                    low_val = _v("Low")
                    volume_val = _v("Volume")

                    if volume_val is None:
                        raise RuntimeError(
                            f"[MARKET_HEALTH] Missing volume data for {sym} on {d} — "
                            "market health calculation requires complete OHLCV data"
                        )
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
                logger.info(f"Fetched {len([r for r in records if r[0] == sym])} rows for {sym}")
            except (AttributeError, KeyError, ValueError, TypeError) as e:
                logger.error(f"Failed to fetch {sym}: Data format error: {e}")
                failed_symbols[sym] = f"Data format error: {str(e)[:50]}"
                continue
            except RuntimeError:
                raise
            except ZeroDivisionError as e:
                logger.error(f"Failed to fetch {sym}: Unexpected error: {e}")
                failed_symbols[sym] = f"Unexpected error: {str(e)[:50]}"
                continue

        coverage = (len(INDEX_SYMBOLS_FOR_PRICE_DAILY) - len(failed_symbols)) / len(INDEX_SYMBOLS_FOR_PRICE_DAILY) * 100
        if coverage < 80:
            count_fetched = len(INDEX_SYMBOLS_FOR_PRICE_DAILY) - len(failed_symbols)
            total_count = len(INDEX_SYMBOLS_FOR_PRICE_DAILY)
            raise RuntimeError(
                f"[VIX_PRICES] Insufficient coverage: {coverage:.1f}% ({count_fetched} of {total_count} symbols). "
                f"Failed symbols: {failed_symbols}"
            )

        if not records:
            raise RuntimeError(
                f"[VIX_PRICES] No prices fetched for {len(INDEX_SYMBOLS_FOR_PRICE_DAILY)} symbols. "
                "All fetch attempts failed."
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
        ) from e


def main() -> int:
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
        raise RuntimeError(f"Market health daily loader failed: {e}") from e


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
