#!/usr/bin/env python3
"""Market Health Daily Loader - Market stage, distribution days, advance/decline.

Computes market-wide health metrics from SPY price data and market indicators.
Populates all required market_health_daily columns.

Run: python3 load_market_health_daily.py [--parallelism 1]
"""

import argparse
import logging
import sys
import time
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
from utils.data.age_validator import DataAgeValidator
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

    def fetch_put_call_with_breaker(self, eval_date: date) -> dict[str, Any] | float:
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
            raise RuntimeError(
                f"[MARKET_HEALTH] MarketCalendar loop exceeded {max_iterations} iterations. "
                "Calendar is corrupted or has no trading days in last 365 days. "
                "Manual investigation required. Cannot compute market health with invalid calendar data."
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
                    if row[1] is None:
                        raise RuntimeError(
                            "[MARKET_HEALTH] Row count query returned NULL — database query may have failed"
                        )
                    row_count = int(row[1])
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
            # Limit initial backfill to 365 days to match available VIX data (pre-loaded in main())
            # This ensures SMA_200 calculations have sufficient history (200+ trading days = ~280 calendar days)
            return end - timedelta(days=365)
        # Backfill 300 days (~250 trading days after weekends/holidays).
        # This ensures we have sufficient history to compute SMA_200 (needs 200 trading days).
        return since - timedelta(days=300)

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
        """Merge breadth data into health metrics.

        Breadth data (% stocks > 200-DMA, advance/decline ratio) is CRITICAL for market exposure scoring.
        Fail-fast if unavailable; don't silently skip.
        FRESHNESS: Validate that advance_decline_daily and technical_data_daily are recent.
        """
        # Validate upstream data freshness
        tech_freshness = DataAgeValidator.check("technical_data_daily")
        if not tech_freshness["is_fresh"]:
            raise RuntimeError(
                f"[MARKET_HEALTH CRITICAL] Technical data is stale: {tech_freshness['message']}. "
                f"Cannot compute market breadth metrics without fresh technical indicators. "
                f"Check technical_data_daily loader completion."
            )

        breadth = self._breadth_fetcher.fetch(start, end)

        if not breadth or len(breadth) == 0:
            msg = (
                f"[MARKET_HEALTH CRITICAL] Breadth data unavailable for {start} to {end}. "
                f"Advance/decline metrics are required inputs to market exposure calculation (10pt + 6pt = 16% of score). "
                f"Cannot proceed without valid breadth data. "
                f"Check breadth fetcher and ensure advance_decline_daily table has complete data."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        matched_count = 0
        unmatched_dates = []
        for m in health_metrics:
            b = breadth.get(m["date"])
            if b is not None:
                # CRITICAL: Breadth fields are required for market exposure scoring
                # Validate all required keys exist - don't silently default to None
                required_fields = ["advance_decline_ratio", "new_highs_count", "new_lows_count"]
                for field in required_fields:
                    if field not in b:
                        raise RuntimeError(
                            f"[MARKET_HEALTH CRITICAL] Breadth data for {m['date']} missing required field '{field}'. "
                            f"All breadth metrics (advance/decline ratio, new highs/lows) are CRITICAL for market exposure scoring. "
                            f"Cannot proceed with incomplete breadth data. Check breadth fetcher implementation."
                        )
                # Validate values are not None/empty
                for field in required_fields:
                    val = b[field]
                    if val is None or (isinstance(val, float) and val != val):  # NaN check
                        raise RuntimeError(
                            f"[MARKET_HEALTH CRITICAL] Breadth data for {m['date']} has NULL/NaN value for '{field}'. "
                            f"All breadth metrics must be valid numbers for market exposure scoring. "
                            f"Check advance_decline_daily and technical_data_daily table data quality."
                        )
                m["advance_decline_ratio"] = b["advance_decline_ratio"]
                m["new_highs_count"] = b["new_highs_count"]
                m["new_lows_count"] = b["new_lows_count"]
                m["breadth_data_available"] = True
                matched_count += 1
            else:
                # Mark this date as missing breadth data (CRITICAL field)
                logger.warning(f"[MARKET_HEALTH] Breadth data missing for critical date {m['date']}")
                unmatched_dates.append(m["date"])

        if matched_count == 0:
            msg = (
                f"[MARKET_HEALTH CRITICAL] Breadth data fetched but no dates matched with health metrics ({len(health_metrics)} dates). "
                f"This indicates data misalignment: breadth available dates don't overlap with trading dates. "
                f"Cannot compute market exposure without valid breadth/advance-decline metrics. "
                f"Verify breadth_fetcher date logic and technical_data_daily completeness."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        if unmatched_dates:
            # Special case: If only today's date is missing breadth data, skip it (technical data may not be ready yet)
            # This allows market health to complete for previous dates and retry today on the next run
            today_str = datetime.now(EASTERN_TZ).date().isoformat()
            if len(unmatched_dates) == 1 and unmatched_dates[0] == today_str:
                logger.warning(
                    f"[MARKET_HEALTH] Breadth data unavailable for today ({today_str}) - "
                    f"technical data may still be processing. Skipping today, will be included in next run."
                )
                # Remove today from health_metrics so it won't be inserted
                health_metrics[:] = [m for m in health_metrics if m["date"] != today_str]
                if not health_metrics:
                    logger.warning("[MARKET_HEALTH] All dates removed (only today was computed). No data to insert.")
                return

            # For historical dates, breadth data MUST be available
            msg = (
                f"[MARKET_HEALTH CRITICAL] Breadth enrichment: matched {matched_count}/{len(health_metrics)} dates. "
                f"Missing breadth data for {len(unmatched_dates)} critical date(s): "
                f"{unmatched_dates[:5]}{'...' if len(unmatched_dates) > 5 else ''}. "
                f"Breadth metrics are CRITICAL for market exposure scoring (16% of score). "
                f"Cannot proceed without complete breadth data for all trading dates."
            )
            logger.error(msg)
            raise RuntimeError(msg)

    def _merge_vix_data(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge VIX data into health metrics.

        VIX fetcher returns dict with vix_close/high/low; we extract vix_close as the level.
        VIX is CRITICAL for circuit breaker logic. NEVER forward-fill missing dates—they indicate
        data corruption or loader failure. All trading dates MUST have valid VIX.
        FAIL-FAST: Raise error if any date missing or has NULL vix_close.
        FRESHNESS: Validate that vix_history table was updated recently before using data.
        Validates against placeholder/fallback values (0, 0.0).
        """
        # Validate upstream data freshness before using it
        vix_freshness = DataAgeValidator.check("vix_history")
        if not vix_freshness["is_fresh"]:
            raise RuntimeError(
                f"[MARKET_HEALTH CRITICAL] VIX source data is stale: {vix_freshness['message']}. "
                f"Cannot compute circuit breaker decisions with stale volatility data. "
                f"Check vix_history loader and ensure it ran recently."
            )

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
                logger.warning(f"[MARKET_HEALTH] VIX data missing for critical date {m['date']}")
                missing_dates.append(m["date"])
                continue

            vix_data = vix[m["date"]]
            # CRITICAL: Validate VIX data structure - don't silently default to None
            if isinstance(vix_data, dict):
                # Explicit validation before bracket access
                if "vix_close" not in vix_data:
                    logger.error(
                        f"[MARKET_HEALTH] VIX data structure corrupted for {m['date']}. "
                        f"Missing required field 'vix_close'. "
                        f"Available keys: {list(vix_data.keys())}. Full data: {vix_data}"
                    )
                    raise ValueError(
                        f"Market health data missing required field 'vix_close' for {m['date']}, "
                        f"data structure corrupted. Expected dict with 'vix_close' field. "
                        f"Available keys: {list(vix_data.keys())}. Check VIX fetcher and vix_history table."
                    )
                vix_close = vix_data["vix_close"]
            else:
                # VIX data may be raw value (backward compatibility)
                vix_close = vix_data

            # Check for NULL/None values
            if vix_close is None or vix_close == "":
                logger.warning(f"[MARKET_HEALTH] VIX close value is NULL for critical date {m['date']}")
                null_values.append(m["date"])
                continue

            # Check for placeholder/fallback values (0, 0.0) which indicate missing data
            if vix_close == 0 or vix_close == 0.0:
                logger.warning(f"[MARKET_HEALTH] VIX has placeholder value (0.0) for critical date {m['date']}")
                raise RuntimeError(
                    f"[MARKET_HEALTH CRITICAL] VIX has placeholder/fallback value (0.0) for {m['date']}: {vix_close}. "
                    "Cannot use fallback zeros for circuit breaker decisions. Check vix_history loader."
                )

            # Validate VIX is in realistic range (VIX typically 5-100, occasionally beyond)
            try:
                vix_float = float(vix_close)
                if vix_float < 0:
                    logger.warning(f"[MARKET_HEALTH] VIX value negative for critical date {m['date']}: {vix_float}")
                    raise RuntimeError(
                        f"[MARKET_HEALTH CRITICAL] VIX value is negative for {m['date']}: {vix_float}. "
                        f"VIX cannot be negative. Data corruption detected in vix_history. "
                        f"Check VIX feed and fetcher validation."
                    )
            except (TypeError, ValueError) as e:
                logger.warning(f"[MARKET_HEALTH] VIX conversion failed for critical date {m['date']}: {vix_close}")
                raise RuntimeError(
                    f"[MARKET_HEALTH CRITICAL] VIX value cannot be converted to float for {m['date']}: {vix_close}. "
                    f"Check vix_history data type and VIX fetcher."
                ) from e

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

    def _fetch_put_call_with_retries(
        self, end_date: date, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> dict[str, Any]:
        """Fetch put/call ratio with retry logic for transient errors.

        Retries on transient errors (ConnectionError, timeout, 503).
        Returns explicit data_unavailable marker dict after all retries exhausted.

        Args:
            end_date: Date to fetch put/call ratio for
            max_retries: Maximum number of retry attempts (default 3)
            backoff_seconds: Initial backoff delay in seconds (default 1.0)

        Returns:
            Dict with either {put_call_ratio: float} if successful,
            or {data_unavailable: True, reason: "..."} if unavailable
        """
        for attempt in range(max_retries):
            try:
                result = self._put_call_fetcher.fetch(end_date)
                # Check if result is a dict with "data_unavailable" key
                if isinstance(result, dict) and result.get("data_unavailable"):
                    if "reason" not in result:
                        raise ValueError(
                            "[MARKET_HEALTH] Put/call fetcher returned data_unavailable=True but missing reason field. "
                            "Data structure corruption or incomplete error handling."
                        )
                    reason = result["reason"]
                    logger.debug(f"[MARKET_HEALTH] Put/call ratio unavailable from fetcher: {reason}")
                    return {"data_unavailable": True, "reason": reason, "put_call_ratio": None}
                # If it's a float, return it as the ratio
                if isinstance(result, float):
                    return {"put_call_ratio": result}
                # Shouldn't reach here, but handle unexpected types defensively
                logger.debug("[MARKET_HEALTH] Put/call fetcher returned unexpected type, marking unavailable")
                return {"data_unavailable": True, "reason": "unexpected_return_type", "put_call_ratio": None}
            except (ConnectionError, TimeoutError) as e:
                # Transient errors: retry with backoff
                if attempt < max_retries - 1:
                    wait_time = backoff_seconds * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"[MARKET_HEALTH] Put/call ratio fetch attempt {attempt + 1}/{max_retries} failed with "
                        f"transient error: {type(e).__name__}: {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[MARKET_HEALTH] Put/call ratio fetch failed after {max_retries} attempts. "
                        f"All retries exhausted on transient error: {e}"
                    )
                    logger.debug("[MARKET_HEALTH] Put/call ratio unavailable after max retries on transient error")
                    return {"data_unavailable": True, "reason": "transient_error_max_retries", "put_call_ratio": None}
            except Exception as e:
                # Other exceptions: don't retry, mark unavailable
                logger.warning(
                    f"[MARKET_HEALTH] Put/call ratio fetch failed with non-transient error: {type(e).__name__}: {e}. "
                    f"Options sentiment is optional - marking unavailable."
                )
                logger.debug(
                    f"[MARKET_HEALTH] Put/call ratio unavailable due to non-transient exception: {type(e).__name__}"
                )
                return {"data_unavailable": True, "reason": "fetch_exception", "put_call_ratio": None}
        logger.debug("[MARKET_HEALTH] Put/call ratio fetch exhausted all retries, marking unavailable")
        return {"data_unavailable": True, "reason": "transient_error_max_retries", "put_call_ratio": None}

    def _merge_put_call_data(self, health_metrics: list[dict[str, Any]], end: date) -> None:
        """Merge put/call ratio into health metrics.

        Put/call ratio is OPTIONAL enrichment for market exposure scoring (8pt factor).
        Options sentiment (put/call) is useful for assessing market risk appetite, but
        market can function without it. Gracefully degrade if unavailable.

        Uses retry logic for transient errors. Marks data_unavailable when unavailable.
        """
        result = self._fetch_put_call_with_retries(end)

        end_str = end.isoformat()
        matched_count = 0

        # CRITICAL: Check if data is available - fail if marker missing (don't default to False)
        if "data_unavailable" not in result:
            logger.error(
                "[MARKET_HEALTH] Put/call ratio result missing data_unavailable marker. "
                "Cannot determine if data is available. Data structure invalid."
            )
            raise ValueError(
                "[MARKET_HEALTH] Put/call result missing required data_unavailable marker. "
                "Result structure: " + str(result)
            )

        data_is_unavailable = result["data_unavailable"]
        if not data_is_unavailable:
            today_pc = result.get("put_call_ratio")
            if today_pc is not None and today_pc != 0.0:
                for m in health_metrics:
                    if m["date"] == end_str:
                        m["put_call_ratio"] = today_pc
                        m["put_call_ratio_available"] = True
                        m["put_call_ratio_data_unavailable"] = False
                        matched_count += 1
                    # Note: Do NOT set put_call_ratio for historical dates
                    # Historical dates keep their existing put_call_ratio values (if any)
                logger.info(f"Put/call ratio: {today_pc:.3f} (matched {matched_count} rows)")
            else:
                # Data available but invalid/zero, mark unavailable
                if "reason" not in result:
                    raise ValueError(
                        "[MARKET_HEALTH] Put/call result has data_unavailable marker but missing reason field. "
                        "Data structure corruption or incomplete error handling."
                    )
                reason = result["reason"]
                if not reason or not isinstance(reason, str) or not reason.strip():
                    raise ValueError(
                        "[MARKET_HEALTH] Put/call result has reason field but it's empty or invalid. "
                        f"Got: {type(reason).__name__} = {reason!r}. "
                        "Reason must be a non-empty string describing why data is unavailable."
                    )
                for m in health_metrics:
                    if m["date"] == end_str:
                        m["put_call_ratio"] = None
                        m["put_call_ratio_available"] = False
                        m["put_call_ratio_data_unavailable"] = True
                        m["put_call_ratio_unavailable_reason"] = reason
                        matched_count += 1
                logger.warning(
                    f"[MARKET_HEALTH] Put/call ratio invalid/unavailable for {end} — marked explicitly as data_unavailable. "
                    f"Options sentiment is optional enrichment."
                )
        else:
            # Explicitly mark which date is missing put/call ratio with data_unavailable flag
            if "reason" not in result:
                raise ValueError(
                    "[MARKET_HEALTH] Put/call result missing reason field for data_unavailable case. "
                    "Data structure corruption or incomplete error handling."
                )
            error_reason = result["reason"]
            if not error_reason or not isinstance(error_reason, str) or not error_reason.strip():
                raise ValueError(
                    "[MARKET_HEALTH] Put/call result has reason field but it's empty or invalid. "
                    f"Got: {type(error_reason).__name__} = {error_reason!r}. "
                    "Reason must be a non-empty string describing why data is unavailable."
                )
            for m in health_metrics:
                if m["date"] == end_str:
                    m["put_call_ratio"] = None
                    m["put_call_ratio_available"] = False
                    m["put_call_ratio_data_unavailable"] = True
                    m["put_call_ratio_unavailable_reason"] = error_reason
                    matched_count += 1
            reason_str = f" ({error_reason})" if error_reason else ""
            logger.warning(
                f"[MARKET_HEALTH] Put/call ratio unavailable for {end}{reason_str} — marked explicitly as data_unavailable. "
                f"Options sentiment is optional enrichment."
            )

    def _fetch_yield_curve_with_retries(
        self, start: date, end: date, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> dict[str, Any]:
        """Fetch yield curve data with retry logic for transient errors.

        Retries on transient errors (API timeout, connection issues).
        Returns explicit data_unavailable marker dict after all retries exhausted.

        Args:
            start: Start date for yield curve range
            end: End date for yield curve range
            max_retries: Maximum number of retry attempts (default 3)
            backoff_seconds: Initial backoff delay in seconds (default 1.0)

        Returns:
            Dict with either yield curve data if successful,
            or {data_unavailable: True, reason: "..."} if unavailable
        """
        for attempt in range(max_retries):
            try:
                yield_curve = self._yield_curve_fetcher.fetch(start, end)
                # Success: return the data (may have data_unavailable flag set by fetcher)
                return (
                    yield_curve
                    if yield_curve is not None
                    else {"data_unavailable": True, "reason": "fetcher_returned_none"}
                )
            except (ConnectionError, TimeoutError) as e:
                # Transient errors: retry with backoff
                if attempt < max_retries - 1:
                    wait_time = backoff_seconds * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"[MARKET_HEALTH] Yield curve fetch attempt {attempt + 1}/{max_retries} failed with "
                        f"transient error: {type(e).__name__}: {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[MARKET_HEALTH] Yield curve fetch failed after {max_retries} attempts. "
                        f"All retries exhausted on transient error: {e}"
                    )
                    logger.debug("[MARKET_HEALTH] Yield curve unavailable after max retries on transient error")
                    return {"data_unavailable": True, "reason": "transient_error_max_retries"}
            except Exception as e:
                # Other exceptions: don't retry, mark unavailable
                logger.warning(
                    f"[MARKET_HEALTH] Yield curve fetch failed with non-transient error: {type(e).__name__}: {e}. "
                    f"Market regime detection will skip inversion signals."
                )
                logger.debug(
                    f"[MARKET_HEALTH] Yield curve unavailable due to non-transient exception: {type(e).__name__}"
                )
                return {"data_unavailable": True, "reason": "fetch_exception"}
        logger.debug("[MARKET_HEALTH] Yield curve fetch exhausted all retries, marking unavailable")
        return {"data_unavailable": True, "reason": "transient_error_max_retries"}

    def _merge_yield_curve_data(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge yield curve slope into health metrics.

        Yield curve slope (10Y-2Y spread) is optional enrichment for market regime detection.
        If yield curve data is unavailable, market regime detection is skipped (graceful degradation).
        If data DOES exist, it must be complete (no forward-fill, no stale fallbacks).
        FRESHNESS: Validate upstream data is recent before using (don't accept week-old Treasury data).

        On data unavailability: Log and mark with data_unavailable flag.
        This allows market health metrics to continue without regime classification.
        Uses retry logic for transient errors.
        """
        try:
            # Check freshness of economic_metrics (contains yield curve data)
            econ_freshness = DataAgeValidator.check("economic_metrics_daily")
            if not econ_freshness["is_fresh"]:
                logger.warning(
                    f"[MARKET_HEALTH] Yield curve source data is stale: {econ_freshness['message']}. "
                    f"Market regime will skip yield curve inversion detection. Marking data_unavailable and continuing."
                )
                logger.debug("[MARKET_HEALTH] Yield curve data unavailable due to stale source data")
                # Mark all metrics as having unavailable yield curve data
                for m in health_metrics:
                    m["yield_curve_slope"] = None
                    m["yield_curve_data_unavailable"] = True
                    m["yield_curve_unavailable_reason"] = "source_data_stale"
                return

            yield_curve = self._fetch_yield_curve_with_retries(start, end)

            # Check for explicit data_unavailable marker from fetch or fetcher
            if yield_curve.get("data_unavailable"):
                if "reason" not in yield_curve:
                    raise ValueError(
                        "[MARKET_HEALTH] Yield curve result has data_unavailable=True but missing reason field. "
                        "Data structure corruption or incomplete error handling."
                    )
                reason = yield_curve["reason"]
                logger.warning(
                    f"[MARKET_HEALTH] Yield curve data unavailable ({reason}) - "
                    f"marking data_unavailable and skipping inversion detection"
                )
                logger.debug(f"[MARKET_HEALTH] Yield curve unavailable, reason: {reason}")
                # Mark all metrics as having unavailable yield curve data
                for m in health_metrics:
                    m["yield_curve_slope"] = None
                    m["yield_curve_data_unavailable"] = True
                    m["yield_curve_unavailable_reason"] = reason
                return

            if not yield_curve or len(yield_curve) == 0:
                logger.warning(
                    "[MARKET_HEALTH] Yield curve data empty (no dates returned) - "
                    "marking data_unavailable and skipping inversion detection"
                )
                # Mark all metrics as having unavailable yield curve data
                for m in health_metrics:
                    m["yield_curve_slope"] = None
                    m["yield_curve_data_unavailable"] = True
                    m["yield_curve_unavailable_reason"] = "no_data_returned"
                return

            matched_count = 0
            missing_dates = []
            null_values = []

            for m in health_metrics:
                slope_data = yield_curve.get(m["date"])
                if slope_data is None:
                    logger.warning(f"[MARKET_HEALTH] Yield curve data missing for date {m['date']}")
                    missing_dates.append(m["date"])
                    # Explicitly mark as unavailable for this date
                    m["yield_curve_data_unavailable"] = True
                    m["yield_curve_unavailable_reason"] = "date_not_in_source"
                    continue

                # CRITICAL: Validate yield_spread key exists in slope_data
                # Explicit validation before bracket access - don't silently default to None if key is missing
                if not isinstance(slope_data, dict):
                    logger.error(
                        f"[MARKET_HEALTH] Yield curve data structure corrupted for {m['date']}. "
                        f"Expected dict but got type {type(slope_data).__name__}. Full data: {slope_data}"
                    )
                    raise ValueError(
                        f"Market health data structure corrupted for {m['date']}, "
                        f"expected dict with 'yield_spread' field. "
                        f"Got type {type(slope_data).__name__}. Full data: {slope_data}"
                    )

                if "yield_spread" not in slope_data:
                    logger.error(
                        f"[MARKET_HEALTH] Yield curve data structure corrupted for {m['date']}. "
                        f"Missing required field 'yield_spread'. "
                        f"Available keys: {list(slope_data.keys())}. Full data: {slope_data}"
                    )
                    raise ValueError(
                        f"Market health data missing required field 'yield_spread' for {m['date']}, "
                        f"data structure corrupted. Expected dict with 'yield_spread' field. "
                        f"Available keys: {list(slope_data.keys())}"
                    )

                slope = slope_data["yield_spread"]
                if slope is None or slope == "":
                    logger.warning(f"[MARKET_HEALTH] Yield curve spread is NULL for date {m['date']}")
                    null_values.append(m["date"])
                    # Explicitly mark as unavailable for this date
                    m["yield_curve_data_unavailable"] = True
                    m["yield_curve_unavailable_reason"] = "null_value_in_source"
                    continue

                m["yield_curve_slope"] = slope
                m["yield_curve_data_unavailable"] = False
                m["yield_curve_unavailable_reason"] = None
                matched_count += 1

            if missing_dates:
                logger.warning(
                    f"[MARKET_HEALTH] Yield curve data incomplete: {len(missing_dates)} date(s) missing "
                    f"({missing_dates[:3]}{'...' if len(missing_dates) > 3 else ''}). "
                    f"Partial data available ({matched_count}/{len(health_metrics)} dates). "
                    f"Market regime detection will use available data and mark unavailable dates."
                )

            if null_values:
                logger.warning(
                    f"[MARKET_HEALTH] Yield curve has NULL values for {len(null_values)} date(s): "
                    f"({null_values[:3]}{'...' if len(null_values) > 3 else ''}). "
                    f"Partial data available ({matched_count}/{len(health_metrics)} dates). "
                    f"These dates marked as data_unavailable."
                )

            if matched_count > 0:
                logger.info(
                    f"Yield curve enrichment: matched {matched_count}/{len(health_metrics)} dates with valid yield_spread"
                )
            elif matched_count == 0:
                logger.warning(
                    "[MARKET_HEALTH] Yield curve data available but no valid slopes found for any date - "
                    "all dates marked as data_unavailable"
                )
        except Exception as e:
            logger.warning(
                f"[MARKET_HEALTH] Yield curve enrichment failed: {e}. "
                f"Market regime detection will skip inversion signals. Marking data_unavailable and continuing."
            )
            # Mark all metrics as having unavailable yield curve data on exception
            for m in health_metrics:
                m["yield_curve_slope"] = None
                m["yield_curve_data_unavailable"] = True
                m["yield_curve_unavailable_reason"] = "fetcher_exception"

    def _fetch_fed_rate_with_retries(
        self, start: date, end: date, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> dict[str, Any]:
        """Fetch Fed rate data from database with retry logic for transient errors.

        Retries on OperationalError (connection pool exhaustion, transient failures).
        Raises on DatabaseError (permanent failures - table missing, permissions, etc).

        Args:
            start: Start date for query range
            end: End date for query range
            max_retries: Maximum number of retry attempts (default 3)
            backoff_seconds: Initial backoff delay in seconds (default 1.0)

        Returns:
            Dict with either {fed_rate_rows: list} if successful,
            or {data_unavailable: True, reason: "..."} if unavailable after retries.
            Raises RuntimeError on permanent database errors.
        """
        for attempt in range(max_retries):
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT value::float, date FROM economic_data
                        WHERE series_id = 'FEDFUNDS' AND date >= %s AND date <= %s
                        ORDER BY date DESC
                        LIMIT 60
                        """,
                        (start, end),
                    )
                    rows = cur.fetchall()
                    return {"fed_rate_rows": rows}
            except psycopg2.OperationalError as e:
                # Transient error: connection pool exhaustion, temporary network issue
                if attempt < max_retries - 1:
                    wait_time = backoff_seconds * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"[MARKET_HEALTH] Fed rate fetch attempt {attempt + 1}/{max_retries} failed with "
                        f"transient OperationalError: {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[MARKET_HEALTH] Fed rate fetch failed after {max_retries} attempts. "
                        f"All retries exhausted on transient OperationalError: {e}"
                    )
                    logger.debug(
                        "[MARKET_HEALTH] Fed rate data unavailable after max retries on database connection failure"
                    )
                    return {"data_unavailable": True, "reason": "database_connection_failed", "fed_rate_rows": None}
            except psycopg2.DatabaseError as e:
                # Permanent error: invalid SQL, table missing, permissions, schema mismatch
                logger.error(
                    f"[MARKET_HEALTH] Fed rate fetch failed with permanent DatabaseError "
                    f"(not retrying): {e}. Check economic_data table schema and permissions."
                )
                raise RuntimeError(
                    f"[MARKET_HEALTH] Permanent database error fetching Fed rate data: {e}. "
                    "This indicates a schema or configuration problem that requires investigation."
                ) from e
        logger.debug("[MARKET_HEALTH] Fed rate fetch exhausted all retries, marking unavailable")
        return {"data_unavailable": True, "reason": "database_connection_failed", "fed_rate_rows": None}

    def _merge_fed_rate_environment(self, health_metrics: list[dict[str, Any]], start: date, end: date) -> None:
        """Merge Fed rate environment classification into health metrics.

        Classifies Fed policy stance (tightening/neutral/easing) based on Fed funds rate trend.
        Fed policy environment is optional enrichment for market regime detection.
        Marks data_unavailable when data cannot be fetched or is insufficient.

        Uses retry logic for transient database errors (OperationalError).
        Raises on permanent database errors (DatabaseError).
        """
        try:
            # Fetch Fed rate data with retry logic for transient errors
            result = self._fetch_fed_rate_with_retries(start, end)

            # Check for explicit data_unavailable marker
            if result.get("data_unavailable"):
                if "reason" not in result:
                    raise ValueError(
                        "[MARKET_HEALTH] Fed rate result has data_unavailable=True but missing reason field. "
                        "Data structure corruption or incomplete error handling."
                    )
                error_reason = result["reason"]
                msg = (
                    f"[MARKET_HEALTH] Fed rate enrichment unavailable after retries: {error_reason}. "
                    f"Fed policy environment optional enrichment unavailable. Marking data_unavailable and continuing."
                )
                logger.warning(msg)
                logger.debug(f"[MARKET_HEALTH] Fed rate data unavailable, reason: {error_reason}")
                for m in health_metrics:
                    m["fed_rate_environment"] = None
                    m["fed_rate_data_unavailable"] = True
                    m["fed_rate_unavailable_reason"] = error_reason
                return

            rows = result.get("fed_rate_rows")
            if not rows:
                msg = (
                    f"[MARKET_HEALTH] Fed funds rate data missing for {start} to {end}. "
                    f"Fed policy environment optional enrichment unavailable. "
                    f"Marking data_unavailable and continuing (check economic_data table for FEDFUNDS series)."
                )
                logger.warning(msg)
                # Mark all metrics with data_unavailable for fed_rate_environment
                for m in health_metrics:
                    m["fed_rate_environment"] = None
                    m["fed_rate_data_unavailable"] = True
                    m["fed_rate_unavailable_reason"] = "no_historical_data"
                return

            # Get current and historical rates to determine trend
            current_rate = float(rows[0][0]) if rows[0][0] is not None else None
            if current_rate is None:
                msg = (
                    f"[MARKET_HEALTH] Fed funds rate is NULL for current period {start} to {end}. "
                    f"Fed policy environment unavailable. Marking data_unavailable and continuing."
                )
                logger.warning(f"[MARKET_HEALTH] Fed rate NULL check: {msg}")
                # Mark all metrics with data_unavailable
                for m in health_metrics:
                    m["fed_rate_environment"] = None
                    m["fed_rate_data_unavailable"] = True
                    m["fed_rate_unavailable_reason"] = "current_rate_null"
                return

            # Get rate 30 days ago for trend
            rate_30d_ago = None
            for r in rows:
                d = r[1]
                if d and (start - d).days >= 30:
                    rate_30d_ago = float(r[0]) if r[0] is not None else None
                    break

            # Classify environment: requires 30+ days of history for trend comparison
            if rate_30d_ago is not None:
                if current_rate > rate_30d_ago * 1.05:
                    env = "tightening"
                elif current_rate < rate_30d_ago * 0.95:
                    env = "easing"
                else:
                    env = "neutral"
                # Apply to all metrics with available data marker
                for m in health_metrics:
                    m["fed_rate_environment"] = env
                    m["fed_rate_data_unavailable"] = False
                    m["fed_rate_unavailable_reason"] = None
                logger.info(f"Fed rate environment: {env} (current={current_rate}%, 30d_ago={rate_30d_ago}%)")
            else:
                # Insufficient history: don't classify (don't mix stale trend with absolute levels)
                logger.warning(
                    f"[MARKET_HEALTH] Fed rate environment skipped: <30 days history available. "
                    f"Cannot classify trend without 30-day baseline (current={current_rate}%). "
                    f"Marking data_unavailable for trend classification."
                )
                for m in health_metrics:
                    m["fed_rate_environment"] = None
                    m["fed_rate_data_unavailable"] = True
                    m["fed_rate_unavailable_reason"] = "insufficient_history"
        except RuntimeError:
            # Permanent database error (re-raised from _fetch_fed_rate_with_retries)
            # This is a critical configuration problem - let it propagate up
            raise
        except Exception as e:
            logger.warning(
                f"[MARKET_HEALTH] Fed rate enrichment failed: {e}. "
                f"Fed policy environment optional enrichment unavailable. Marking data_unavailable and continuing."
            )
            # Mark all metrics with data_unavailable on any exception
            for m in health_metrics:
                m["fed_rate_environment"] = None
                m["fed_rate_data_unavailable"] = True
                m["fed_rate_unavailable_reason"] = "enrichment_exception"

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

        # Filter to only dates we need to insert BEFORE fetching external data (VIX, breadth, etc.).
        # The full SPY price range is needed above for SMA calculations, but external data sources
        # (VIX in price_daily, breadth from advance_decline tables) only need to cover the
        # incremental window — not the full 300-day backfill range. Without this filter, the loader
        # fails when VIX history in price_daily doesn't extend as far back as the computation window.
        if since is not None:
            since_str = since.isoformat()
            before_filter = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] >= since_str]
            logger.info(
                f"Filtered health_metrics: {before_filter} -> {len(health_metrics)} (keeping dates >= {since_str})"
            )
            if not health_metrics:
                logger.info(f"[MARKET_HEALTH] No new dates to process (all dates before watermark {since_str})")
                return health_metrics

        # Cap health_metrics to the latest date for which VIX data is available in price_daily.
        # VIX is populated by a separate daily load; on trading days the intraday run of
        # market_health_daily often runs before VIX data for today exists. Attempting to merge
        # VIX for "today" when it hasn't been loaded yet causes a hard failure. Instead, we only
        # compute health metrics up to the latest date VIX is available — today's row is computed
        # on the next run once VIX data lands.
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = '^VIX'")
                vix_max_row = cur.fetchone()
                max_vix_date: date | None = vix_max_row[0] if vix_max_row else None
        except Exception as e:
            logger.warning(f"[MARKET_HEALTH] Could not query max VIX date: {e} — proceeding without cap")
            max_vix_date = None

        if max_vix_date is not None:
            max_vix_str = max_vix_date.isoformat()
            before_vix_cap = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] <= max_vix_str]
            if len(health_metrics) < before_vix_cap:
                logger.info(
                    f"[MARKET_HEALTH] Capped health_metrics to VIX availability: {before_vix_cap} -> {len(health_metrics)} "
                    f"(VIX in price_daily through {max_vix_str}; skipping dates beyond that)"
                )
            if not health_metrics:
                # FAIL-FAST: Market health is critical for circuit breaker evaluation
                # Cannot silently skip all dates - must raise error so orchestrator knows to retry
                raise RuntimeError(
                    "[MARKET_HEALTH CRITICAL] No dates with VIX coverage available. "
                    "Cannot compute market health metrics without VIX data. "
                    "Check price_daily table for ^VIX symbol data availability."
                )

            # Filter to only dates where VIX actually exists in price_daily.
            # The cap above removes dates AFTER the latest VIX row, but VIX coverage may be
            # sparse within the range (e.g., only recent months loaded due to rate limiting).
            # Filtering here prevents _merge_vix_data() from failing on historical gaps —
            # we compute market_health_daily for the dates we DO have VIX, rather than failing
            # for all dates because some historical dates are missing.
            vix_range_start = date.fromisoformat(health_metrics[0]["date"]) if health_metrics else start
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT date FROM price_daily WHERE symbol = '^VIX' AND date >= %s AND date <= %s",
                        (vix_range_start, max_vix_date),
                    )
                    vix_dates: set[str] = {row[0].isoformat() for row in cur.fetchall()}
                if vix_dates:
                    before_sparse = len(health_metrics)
                    # Track which dates are skipped for audit trail (Issue #25 fix)
                    skipped_dates = [m["date"] for m in health_metrics if m["date"] not in vix_dates]
                    health_metrics = [m for m in health_metrics if m["date"] in vix_dates]
                    skipped = before_sparse - len(health_metrics)
                    if skipped > 0:
                        logger.info(
                            f"[MARKET_HEALTH] Filtered to VIX-covered dates: {before_sparse} -> "
                            f"{len(health_metrics)} (skipped {skipped} historical dates without VIX). "
                            f"Skipped dates: {skipped_dates}"
                        )
                        # Track skipped dates in stats for orchestrator access (Issue #25)
                        self._stats.set("skipped_dates_vix_coverage", skipped_dates)
                        self._stats.set("skipped_count_vix_coverage", skipped)
                    if not health_metrics:
                        # FAIL-FAST: Market health is critical for circuit breaker evaluation
                        # Cannot silently defer when VIX filtering eliminates all dates
                        raise RuntimeError(
                            "[MARKET_HEALTH CRITICAL] VIX pre-filtering eliminated all dates. "
                            "Check VIX data availability in price_daily for ^VIX symbol. "
                            "Market health metrics require complete VIX coverage."
                        )
            except Exception as e:
                logger.warning(f"[MARKET_HEALTH] Could not pre-filter by VIX dates: {e} — proceeding")

        # Derive the actual date range for external data fetches (only covers retained dates)
        merge_start = date.fromisoformat(health_metrics[0]["date"]) if health_metrics else start
        merge_end = date.fromisoformat(health_metrics[-1]["date"]) if health_metrics else end

        # Breadth data (new highs/lows, advance/decline) is critical for market analysis
        # Fail-fast if unavailable; don't silently skip with NULL values
        self._merge_breadth_data(health_metrics, merge_start, merge_end)

        self._merge_vix_data(health_metrics, merge_start, merge_end)
        self._merge_put_call_data(health_metrics, merge_end)
        self._merge_yield_curve_data(health_metrics, merge_start, merge_end)
        self._merge_fed_rate_environment(health_metrics, merge_start, merge_end)

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
                logger.debug(f"[MARKET_HEALTH] Row {idx}: invalid close price {row.get('close')}")
                if "date" not in row or row.get("date") is None:
                    raise ValueError(
                        "[MARKET_HEALTH_CRITICAL] Market health row missing required 'date' field. "
                        "Cannot process market data without date. Row keys: " + str(list(row.index.tolist()))
                    )
                # Explicit validation before bracket access to date field
                if "date" not in row:
                    logger.error(
                        f"[MARKET_HEALTH] Market health row {idx} missing 'date' key. "
                        f"Available keys: {list(row.index.tolist())}. Full row: {row.to_dict()}"
                    )
                    raise ValueError(
                        f"Market health data missing required field 'date' for row {idx}, "
                        f"data structure corrupted. Available keys: {list(row.index.tolist())}"
                    )
                row_date = row["date"]
                logger.warning(
                    f"[MARKET_HEALTH_DATA_GAP] Invalid close price for {row_date}: {row['close']}. "
                    f"Critical price data unavailable. Skipping row - this creates gap in distribution day counts and market health metrics."
                )
                skipped_rows.append(row_date)
                continue
            close = float(row["close"])
            sma_200 = float(row["sma_200"]) if pd.notna(row["sma_200"]) else None
            sma_50 = float(row["sma_50"]) if pd.notna(row["sma_50"]) else None

            # Skip rows with missing SMA (first ~200 rows when computing from historical backfill).
            # These rows lack sufficient history for moving average calculation.
            # Only store rows with valid SMA data for circuit breaker decisions.
            if not sma_200:
                logger.debug(
                    f"[MARKET_HEALTH] Skipping row {row.get('date', 'unknown')}: SMA_200 not yet computed (insufficient history)"
                )
                skipped_rows.append(row.get("date", "unknown"))
                continue

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
                    # CRITICAL breadth data (filled from _merge_breadth_data, no fallback)
                    "advance_decline_ratio": None,
                    "new_highs_count": None,
                    "new_lows_count": None,
                    "breadth_momentum_10d": float(row["breadth_10d"]),
                    "spy_change_pct": spy_change_pct,
                    # CRITICAL VIX data (filled from _merge_vix_data, must be present)
                    "vix_level": None,
                    # OPTIONAL enrichment data (marked as initially unavailable, may be filled by merge operations)
                    "put_call_ratio": None,
                    "put_call_ratio_available": False,
                    "put_call_ratio_data_unavailable": True,
                    "yield_curve_slope": None,
                    "yield_curve_data_unavailable": True,
                    "yield_curve_unavailable_reason": "not_yet_fetched",
                    "fed_rate_environment": None,
                    "fed_rate_data_unavailable": True,
                    "fed_rate_unavailable_reason": "not_yet_fetched",
                }
            )

        # Return results with metadata about skipped dates for audit trail and orchestrator visibility
        if skipped_rows:
            logger.warning(
                f"[MARKET_HEALTH] Data completeness: {len(results)} dates processed, "
                f"{len(skipped_rows)} dates skipped: {skipped_rows[:10]}"
                f"{'...' if len(skipped_rows) > 10 else ''}. "
                f"Coverage: {len(results) / (len(results) + len(skipped_rows)) * 100:.1f}%"
            )

        # Attach metadata for caller visibility
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


def _write_vix_family_prices(start: date, end: date) -> int:  # noqa: C901
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

    # Pre-check: find which symbols already have fresh data in price_daily.
    # Avoids yfinance calls for symbols that are already up-to-date, preventing rate-limit cascades
    # when multiple loaders run simultaneously.
    existing_dates: dict[str, date] = {}
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT symbol, MAX(date) AS max_date
                FROM price_daily
                WHERE symbol = ANY(%s) AND date >= %s
                GROUP BY symbol
                """,
                (INDEX_SYMBOLS_FOR_PRICE_DAILY, start),
            )
            existing_dates = {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"[MARKET_HEALTH] Could not check existing price_daily freshness: {e}")

    # A symbol is "fresh" if its latest date is the previous calendar day or newer.
    # 1-day tolerance: skips re-fetch only when yesterday's data is already there.
    # 5-day was too lenient — on Monday it treated Friday's VIX as fresh and skipped today's fetch.
    fresh_cutoff = end - timedelta(days=1)
    symbols_needing_refresh = {
        sym for sym in INDEX_SYMBOLS_FOR_PRICE_DAILY if sym not in existing_dates or existing_dates[sym] < fresh_cutoff
    }

    if not symbols_needing_refresh:
        logger.info(
            f"[MARKET_HEALTH] All {len(INDEX_SYMBOLS_FOR_PRICE_DAILY)} index symbols already "
            f"fresh in price_daily (through {max(existing_dates.values())}) — skipping yfinance"
        )
        return 0

    logger.info(
        f"[MARKET_HEALTH] Refreshing {len(symbols_needing_refresh)} symbols from yfinance: "
        f"{sorted(symbols_needing_refresh)}"
    )

    try:
        from utils.external.yfinance import YFinanceWrapper

        records = []
        failed_symbols = {}
        for sym in INDEX_SYMBOLS_FOR_PRICE_DAILY:
            if sym not in symbols_needing_refresh:
                logger.debug(f"[MARKET_HEALTH] {sym} already fresh in price_daily — skipping yfinance")
                continue
            try:
                ticker = YFinanceWrapper.get_ticker(sym)
                if not ticker:
                    logger.warning(f"[MARKET_HEALTH] Ticker data unavailable for index {sym}")
                    failed_symbols[sym] = "Ticker unavailable"
                    continue

                df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
                if df is None or df.empty:
                    logger.warning(f"[MARKET_HEALTH] Price history empty for index {sym}")
                    failed_symbols[sym] = "Empty data"
                    continue

                for idx, row in df.iterrows():
                    d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])

                    def _v(col: str, row: Any = row, sym: str = sym, d: date = d) -> float:
                        val: Any = row.get(col) if hasattr(row, "get") else row[col]
                        if val is None:
                            logger.warning(f"[MARKET_HEALTH] Missing {col} for {sym} on {d}")
                            raise RuntimeError(
                                f"[MARKET_HEALTH] Missing {col} data for {sym} on {d} — "
                                "cannot compute market health metrics without complete OHLCV data"
                            )
                        if hasattr(val, "__len__"):
                            try:
                                val = val.iloc[0] if len(val) else None
                            except (IndexError, AttributeError):
                                val = None
                        if val is None:
                            logger.warning(f"[MARKET_HEALTH] Empty {col} for {sym} on {d}")
                            raise RuntimeError(
                                f"[MARKET_HEALTH] Empty {col} data for {sym} on {d} — "
                                "cannot compute market health metrics without complete OHLCV data"
                            )
                        try:
                            f = float(val)
                            if f != f:  # NaN check
                                logger.warning(f"[MARKET_HEALTH] NaN detected in {col} for {sym} on {d}")
                                raise RuntimeError(
                                    f"[MARKET_HEALTH] Invalid {col}={val!r} (NaN) for {sym} on {d} — "
                                    "cannot compute market health metrics with NaN values"
                                )
                            return round(f, 4)
                        except RuntimeError:
                            raise
                        except (TypeError, ValueError) as e:
                            logger.warning(f"[MARKET_HEALTH] Price conversion failed for {col} {sym} {d}: {val!r}")
                            raise RuntimeError(
                                f"[PRICE_EXTRACTION] Failed to parse {col}={val!r} for {sym}: {e}"
                            ) from e

                    close = _v("Close")

                    open_val = _v("Open")
                    high_val = _v("High")
                    low_val = _v("Low")
                    volume_val = int(_v("Volume"))

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
            except RuntimeError as e:
                # yfinance failed (rate-limit, auth error, network) — FAIL-FAST, do NOT use stale data
                logger.error(
                    f"[MARKET_HEALTH CRITICAL] yfinance failed for {sym}: {e}. "
                    f"Cannot use stale price_daily data (violates fail-fast governance). "
                    f"Marking as unavailable."
                )
                failed_symbols[sym] = f"yfinance_failed_using_stale: {e!s}"
            except ZeroDivisionError as e:
                logger.error(f"[MARKET_HEALTH] Unexpected calculation error for {sym}: {e}")
                raise RuntimeError(f"[MARKET_HEALTH] Unexpected error loading market health for {sym}: {e}") from e

        coverage = (len(INDEX_SYMBOLS_FOR_PRICE_DAILY) - len(failed_symbols)) / len(INDEX_SYMBOLS_FOR_PRICE_DAILY) * 100
        if coverage < 100:
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
        # CRITICAL: Write VIX-family prices BEFORE market health load
        # Market health loader needs VIX data to compute metrics
        # Use ET date for consistency with trading calendar
        end = datetime.now(EASTERN_TZ).date()
        start = end - timedelta(days=365)  # 1 year of history for SMA calculations
        written = _write_vix_family_prices(start, end)
        logger.info(f"Pre-loaded {written} VIX family prices into price_daily before market health computation")

        loader = MarketHealthDailyLoader()
        loader.run(["SPY"], parallelism=args.parallelism)
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
