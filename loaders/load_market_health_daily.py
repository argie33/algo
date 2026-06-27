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
        max_iterations = 365
        iterations = 0
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end) and iterations < max_iterations:
            end = end - timedelta(days=1)
            iterations += 1

        if iterations >= max_iterations:
            logger.warning(
                f"[MARKET_HEALTH] MarketCalendar loop exceeded {max_iterations} iterations. "
                "Possible calendar bug. Using {end} as fallback."
            )
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
                    if row is None or len(row) < 2:
                        raise RuntimeError("[MARKET_HEALTH] Watermark query returned no rows")
                    row_count = row[1] if row[1] is not None else 0
                    if row and row[0] is not None:
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
            error_msg = (
                f"[MARKET_HEALTH] {symbol}: No incremental data available. "
                "Market health metrics are CRITICAL for daily circuit breaker decisions. "
                "Cannot proceed without valid health data. Check data sources and try again."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

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
        VIX is CRITICAL for circuit breaker logic. NEVER forward-fill missing dates—they indicate
        data corruption or loader failure. All trading dates MUST have valid VIX.
        FAIL-FAST: Raise error if any date missing or has NULL vix_close.
        """
        vix = self._vix_fetcher.fetch(start, end)
        if not isinstance(vix, dict) or len(vix) == 0:
            raise RuntimeError(
                f"[MARKET_HEALTH] VIX data unavailable or empty for {start} to {end}. "
                "VIX is CRITICAL for circuit breaker halt decisions. "
                "Cannot compute market health metrics without valid VIX data."
            )

        matched_count = 0
        missing_dates = []
        null_values = []

        for m in health_metrics:
            if m["date"] not in vix:
                missing_dates.append(m["date"])
                continue

            vix_data = vix[m["date"]]
            vix_close = vix_data.get("vix_close") if isinstance(vix_data, dict) else vix_data
            if vix_close is None or vix_close == "":
                null_values.append(m["date"])
                continue

            m["vix_level"] = vix_close
            matched_count += 1

        if missing_dates:
            raise RuntimeError(
                f"[MARKET_HEALTH] CRITICAL: VIX data missing for {len(missing_dates)} trading date(s): {missing_dates[:5]}{'...' if len(missing_dates) > 5 else ''}. "
                "VIX is required for circuit breaker decisions. Check VIX fetcher and data source availability."
            )

        if null_values:
            raise RuntimeError(
                f"[MARKET_HEALTH] CRITICAL: VIX has NULL vix_close for {len(null_values)} date(s): {null_values[:5]}{'...' if len(null_values) > 5 else ''}. "
                "Data corruption detected. Check VIX feed and database."
            )

        if matched_count == 0:
            raise RuntimeError(
                "[MARKET_HEALTH] CRITICAL: VIX data fetched but no valid vix_close values found for any trading date. "
                "Data quality issue: check VIX feed format and validation."
            )

        logger.info(f"VIX enrichment: matched {matched_count}/{len(health_metrics)} dates with valid vix_close values")

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

        Yield curve slope is used for market regime detection. For regime accuracy,
        ALL trading dates MUST have valid yield curve data. NEVER forward-fill—missing data
        indicates API failure that should be visible, not hidden.

        Yield curve is OPTIONAL (markets work without Fed inversion data), so unavailability
        returns early without error. But if data DOES exist, it must be 100% complete.
        """
        try:
            yield_curve = self._yield_curve_fetcher.fetch(start, end)

            # Check for unavailability marker (API failed)
            if yield_curve.get("_data_unavailable"):
                reason = yield_curve.get("_reason")
                if reason is None:
                    logger.warning(
                        "Yield curve data unavailable (reason not provided) - market regime will skip inversion detection. "
                        "Check _yield_curve_fetcher.fetch() to ensure it returns '_reason' when data is unavailable."
                    )
                else:
                    logger.warning(f"Yield curve data unavailable ({reason}) - market regime will skip inversion detection")
                return

            if not yield_curve:
                logger.debug("Yield curve data empty - market regime will skip inversion detection")
                return

            matched_count = 0
            missing_dates = []
            null_values = []

            for m in health_metrics:
                slope_data = yield_curve.get(m["date"])
                if slope_data is None:
                    missing_dates.append(m["date"])
                    continue

                slope = slope_data.get("yield_spread")
                if slope is None or slope == "":
                    null_values.append(m["date"])
                    continue

                m["yield_curve_slope"] = slope
                matched_count += 1

            if missing_dates:
                raise RuntimeError(
                    f"[MARKET_HEALTH] Yield curve data incomplete: {len(missing_dates)} date(s) missing "
                    f"({missing_dates[:3]}{'...' if len(missing_dates) > 3 else ''}). "
                    "Market regime detection requires complete yield curve data for inversion detection. "
                    "Cannot proceed with incomplete Fed rate environment data."
                )

            if null_values:
                raise RuntimeError(
                    f"[MARKET_HEALTH] Yield curve has NULL values for {len(null_values)} date(s): "
                    f"({null_values[:3]}{'...' if len(null_values) > 3 else ''}). "
                    "Cannot proceed without complete yield spread data — market regime detection requires valid inversion data."
                )

            if matched_count > 0:
                logger.info(f"Yield curve enrichment: matched {matched_count}/{len(health_metrics)} dates with valid yield_spread")
            else:
                logger.warning("Yield curve data available but no valid slopes found")
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_HEALTH] Yield curve enrichment failed: {e}. "
                "Market regime detection requires yield spread data for inversion signals. "
                "Cannot proceed without valid yield curve data."
            ) from e

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
                        "date": r[0].isoformat() if r[0] is not None else None,
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
            raise RuntimeError(
                "[MARKET_HEALTH] Cannot compute market health: no price data available. "
                "Market health metrics are CRITICAL for circuit breaker decisions. "
                "Check that price_daily table has recent SPY data loaded."
            )
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
        skipped_rows = []
        for idx, row in df.iterrows():
            if not pd.notna(row["close"]) or row["close"] <= 0:
                if 'date' not in row or row.get('date') is None:
                    raise ValueError(
                        "[MARKET_HEALTH_CRITICAL] Market health row missing required 'date' field. "
                        "Cannot process market data without date. Row keys: " + str(list(row.index.tolist()))
                    )
                row_date = row['date']
                logger.error(
                    f"[MARKET_HEALTH_DATA_GAP] Invalid close price for {row_date}: {row['close']}. "
                    f"Skipping row - this creates gap in distribution day counts and market health metrics."
                )
                skipped_rows.append(row_date)
                continue
            close = float(row["close"])
            sma_200 = float(row["sma_200"]) if pd.notna(row["sma_200"]) else None
            sma_50 = float(row["sma_50"]) if pd.notna(row["sma_50"]) else None

            # FAIL-FAST: Market stage classification requires at least SMA_200 (moving average data is critical)
            # Circuit breaker decisions depend on accurate market stage; defaulting to uptrend when data missing is dangerous
            if not sma_200:
                raise RuntimeError(
                    f"[MARKET_HEALTH] Market stage classification failed for {row.get('date', 'unknown')}: "
                    f"SMA_200 is unavailable (None/NaN). Market stage is CRITICAL for circuit breaker decisions. "
                    f"Cannot proceed without valid moving average data. Check price_daily table for SMA computation."
                )

            # Determine market trend and stage
            market_trend = "neutral"
            market_stage: int = 0

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
                logger.error(f"[MARKET_HEALTH] Cannot fetch {sym}: Data format corrupted: {e}")
                raise RuntimeError(
                    f"[MARKET_HEALTH] Market health data corrupted for {sym}. "
                    f"Cannot proceed with incomplete market health context. "
                    f"Error: {e}"
                ) from e
            except RuntimeError:
                raise
            except ZeroDivisionError as e:
                logger.error(f"[MARKET_HEALTH] Unexpected calculation error for {sym}: {e}")
                raise RuntimeError(
                    f"[MARKET_HEALTH] Unexpected error loading market health for {sym}: {e}"
                ) from e

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
