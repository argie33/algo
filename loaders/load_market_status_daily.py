#!/usr/bin/env python3
"""Market Status Daily Loader - Consolidated market health + exposure + sentiment.

CONSOLIDATION: Merges 3 separate market-wide loaders into one atomic operation:
  - load_market_health_daily.py (VIX, breadth, yield curve, put/call)
  - load_market_exposure_daily.py (market regime, exposure %)
  - load_market_sentiment.py (fear/greed index)

Benefits:
  - 1 ECS task instead of 3 (saves ~$0.02-0.03/run)
  - VIX/breadth/yields fetched once, used 3 ways
  - Atomic operation (all market metrics succeed/fail together)
  - Better error handling (single failure point)
  - All market regime logic in one place
  - 10-15 min faster orchestrator

Outputs:
  - market_health_daily (VIX, breadth, yields, put/call)
  - market_exposure_daily (regime, exposure %, factors)
  - market_sentiment (fear/greed, bull/bear %)

Run: python3 loaders/load_market_status_daily.py [--backfill-days N]
"""

import logging
import sys
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loaders.market_health_fetchers import (
    BreadthFetcher,
    PutCallRatioFetcher,
    VIXFetcher,
    YieldCurveFetcher,
)
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class MarketStatusDailyLoader(OptimalLoader):
    """Consolidated market status loader: health + exposure + sentiment.

    Market-wide loader (pseudo-symbol "market"). Fetches all market metrics once,
    computes regime/exposure/sentiment, writes to all 3 output tables atomically.
    """

    table_name = "market_health_daily"  # Primary table for watermark tracking
    primary_key = ("date",)
    watermark_field = "date"
    is_symbol_based = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._vix_fetcher = VIXFetcher()
        self._put_call_fetcher = PutCallRatioFetcher()
        self._yield_curve_fetcher = YieldCurveFetcher()
        self._breadth_fetcher = BreadthFetcher()
        self._fred_api_key: str | None = None

    def run(
        self, symbols: Iterable[str] | None = None, parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to provide market-wide pseudo-symbol."""
        # CRITICAL FIX: Skip loading on non-trading days
        # Markets are closed on weekends/holidays, so no new market data is available
        from algo.infrastructure import MarketCalendar

        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(
                f"[{self.table_name}] Skipping load: today ({run_date}) is not a trading day. "
                f"Market data will use last available trading day's data."
            )
            # Refresh data_loader_status from the real table state even when skipping the
            # fetch. Without this, the status row (latest_date, last_updated) freezes at
            # whatever it was on the last trading day this loader ran, and monitoring
            # reads that as "no/stale data" even though market_health_daily itself has
            # current data through the last trading day.
            self._update_final_status(1)
            return {
                "symbols_processed": 0,
                "symbols_failed": 0,
                "rows_inserted": 0,
                "duration_sec": 0,
                "latest_date": None,
                "status": "SKIPPED_NON_TRADING_DAY",
            }

        symbol_list: list[str]
        if symbols is None or (isinstance(symbols, (list, tuple)) and len(symbols) == 0):
            symbol_list = ["market"]
        else:
            symbol_list = list(symbols) if not isinstance(symbols, list) else symbols
        return super().run(symbols=symbol_list, parallelism=parallelism, backfill_days=backfill_days)

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | dict[str, Any]:
        """Fetch global market data. Skips on non-trading days.

        Returns:
            list[dict]: Market data rows if trading day.
            dict: Marker dict if non-trading day or data unavailable.
        """
        from algo.infrastructure import MarketCalendar

        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(
                f"[{self.table_name}] Skipping fetch_global: today ({run_date}) is not a trading day. "
                f"Market data will use last available trading day's data."
            )
            return {"data_unavailable": True, "reason": "non_trading_day"}

        return self.fetch_incremental("market", since)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch and compute all market metrics for one date.

        Args:
            symbol: Pseudo-symbol "market" (ignored, used by framework)
            since: Optional backfill start date

        Returns:
            List with single market status dict or data_unavailable marker
        """
        if symbol != "market":
            return [{"date": date.today(), "data_unavailable": True, "reason": "invalid_symbol"}]

        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end_date = now_et.date()

            # Fetch all market data (health, breadth, vix, yields)
            health_data = self._fetch_market_health(end_date)
            if health_data.get("data_unavailable"):
                return [health_data]

            # Compute exposure (regime, exposure %, factors)
            exposure_data = self._compute_market_exposure(end_date, health_data)

            # Compute sentiment (fear/greed from VIX + AAII sentiment)
            sentiment_data = self._compute_market_sentiment(end_date, health_data)

            # Market stage/trend (CB6 + Follow-Through-Day re-engagement gate on these)
            stage_data = self._compute_market_stage_trend(end_date)

            # Return consolidated data (caller will write to all 3 tables)
            # GOVERNANCE: data_unavailable must reflect whether exposure computation
            # actually succeeded, not be hardcoded False. Regime/exposure_pct/factors feed
            # directly into position sizing and risk tier classification (exposure_policy.py)
            # - if _compute_market_exposure() failed, those fields land as NULL while this
            # row was still marked "available", so downstream consumers gating on
            # data_unavailable would trust a NULL as "checked, fine" instead of halting.
            exposure_unavailable = bool(exposure_data.get("data_unavailable"))
            return [
                {
                    "date": end_date,
                    "data_unavailable": exposure_unavailable,
                    # Always include "reason" explicitly (None on success) - bulk_insert_manager
                    # derives each row's UPSERT column list from its own dict keys, so omitting
                    # the key entirely (as the previous conditional-unpack did) meant a successful
                    # run's UPDATE never touched the reason column, leaving a stale failure message
                    # in place even though data_unavailable correctly flipped back to False
                    # (confirmed live 2026-07-20: market_health_daily showed data_unavailable=False
                    # with reason still reading a 7h-old "exposure_computation_failed" message).
                    "reason": exposure_data.get("reason") if exposure_unavailable else None,
                    # market_health_daily fields (column names per market_health_daily schema -
                    # health_data uses different internal key names, see _fetch_market_health)
                    "vix_level": health_data.get("vix_level"),
                    "advance_decline_ratio": health_data.get("advance_decline_ratio"),
                    "new_highs_count": health_data.get("new_highs"),
                    "new_lows_count": health_data.get("new_lows"),
                    "breadth_momentum_10d": health_data.get("breadth_momentum_10d"),
                    "up_volume_percent": health_data.get("up_volume_percent"),
                    "yield_curve_slope": health_data.get("yield_10y_2y_spread"),
                    "yield_curve_data_unavailable": health_data["yield_curve_data_unavailable"],
                    "yield_curve_unavailable_reason": health_data.get("yield_curve_unavailable_reason"),
                    "put_call_ratio": health_data.get("put_call_ratio"),
                    "put_call_ratio_data_unavailable": health_data["put_call_ratio_data_unavailable"],
                    "put_call_ratio_unavailable_reason": health_data.get("put_call_ratio_unavailable_reason"),
                    "fed_rate_environment": health_data.get("fed_rate_environment"),
                    "fed_rate_data_unavailable": health_data["fed_rate_data_unavailable"],
                    "fed_rate_unavailable_reason": health_data.get("fed_rate_unavailable_reason"),
                    "market_stage": stage_data.get("market_stage"),
                    "market_trend": stage_data.get("market_trend"),
                    # market_exposure_daily fields
                    "regime": exposure_data.get("regime"),
                    "exposure_pct": exposure_data.get("exposure_pct"),
                    "raw_score": exposure_data.get("raw_score"),
                    "halt_reasons": exposure_data.get("halt_reasons"),
                    "distribution_days": exposure_data.get("distribution_days"),
                    "factors": exposure_data.get("factors"),
                    # market_sentiment fields
                    "fear_greed_index": sentiment_data.get("fear_greed_index"),
                    "sentiment_score": sentiment_data.get("sentiment_score"),
                    "bullish_pct": sentiment_data.get("bullish_pct"),
                    "bearish_pct": sentiment_data.get("bearish_pct"),
                    "neutral_pct": sentiment_data.get("neutral_pct"),
                }
            ]

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Fatal error: {e}", exc_info=True)
            return [
                {
                    "date": date.today(),
                    "data_unavailable": True,
                    # Truncate the full formatted string (not just str(e)) to the reason column's
                    # actual VARCHAR(255) limit - see _compute_market_exposure's identical fix for
                    # why a 100-char cap silently destroys these diagnostic messages.
                    "reason": f"market_status_error: {e}"[:255],
                }
            ]

    def _fetch_fed_rate_environment(self, eval_date: date) -> dict[str, Any]:
        """Fetch current federal funds rate and determine policy environment.

        Uses SOFR (Secured Overnight Financing Rate), the Fed's official benchmark
        rate published daily. Replaces legacy FEDFUNDS (monthly data with gaps).

        Returns:
            {
                "fed_rate_environment": "neutral" | "accommodative" | "restrictive" | None,
                "fed_rate": float (latest SOFR rate) | None,
                "fed_rate_data_unavailable": bool,
                "fed_rate_unavailable_reason": str | None,
            }

        Policy environments:
        - "accommodative": rate < 2.0% (supporting growth)
        - "neutral": rate 2.0% - 4.0% (balanced)
        - "restrictive": rate > 4.0% (fighting inflation)
        """
        try:
            from loaders.load_economic_data import fetch_from_fred, get_fred_api_key

            # Get FRED API key (will raise if missing)
            if not self._fred_api_key:
                self._fred_api_key = get_fred_api_key()

            # Fetch latest SOFR rate (last 30 days to ensure we have data)
            start_date = eval_date - timedelta(days=30)
            fred_data = fetch_from_fred(self._fred_api_key, "SOFR", start_date, eval_date)

            if not fred_data:
                return {
                    "fed_rate_environment": None,
                    "fed_rate": None,
                    "fed_rate_data_unavailable": True,
                    "fed_rate_unavailable_reason": "no_fred_data_returned",
                }

            # Get latest rate (should be sorted by date from FRED API)
            latest_record = fred_data[-1]  # Assuming FRED returns sorted by date ascending
            fed_rate = latest_record["value"]
            rate_date = latest_record["date"]

            # Validate rate is recent (within 5 trading days)
            from algo.infrastructure import MarketCalendar

            last_trading_day = MarketCalendar.get_previous_trading_day(eval_date)
            rate_date_obj = datetime.fromisoformat(rate_date).date() if isinstance(rate_date, str) else rate_date
            days_old = (eval_date - rate_date_obj).days

            if days_old > 7:  # More than a week old
                logger.warning(
                    f"[MARKET_STATUS] SOFR data is {days_old} days old (from {rate_date}). "
                    f"Using stale rate={fed_rate:.2f}% for regime classification."
                )

            # Determine environment based on rate level
            if fed_rate < 2.0:
                environment = "accommodative"
            elif fed_rate >= 4.0:
                environment = "restrictive"
            else:
                environment = "neutral"

            logger.info(f"[MARKET_STATUS] Fed funds rate: {fed_rate:.2f}% ({environment})")

            return {
                "fed_rate_environment": environment,
                "fed_rate": fed_rate,
                "fed_rate_data_unavailable": False,
                "fed_rate_unavailable_reason": None,
            }

        except Exception as e:
            logger.warning(f"[MARKET_STATUS] Fed rate fetch failed: {e}")
            return {
                "fed_rate_environment": None,
                "fed_rate": None,
                "fed_rate_data_unavailable": True,
                "fed_rate_unavailable_reason": f"fetch_failed: {str(e)[:100]}",
            }

    def _fetch_market_health(self, eval_date: date) -> dict[str, Any]:
        """Fetch all health metrics (VIX, breadth, yields, put/call)."""
        try:
            from algo.infrastructure import MarketCalendar

            # Session 299 FIX: Don't fetch from non-trading days
            # Find the most recent trading day (eval_date or earlier)
            last_trading_day = eval_date
            search_date = eval_date
            while search_date >= eval_date - timedelta(days=10):
                if MarketCalendar.is_trading_day(search_date):
                    last_trading_day = search_date
                    break
                search_date -= timedelta(days=1)

            # Fetch VIX (from previous trading day to most recent trading day)
            # This ensures we don't try to fetch non-trading day data
            fetch_start = last_trading_day - timedelta(days=1)
            while fetch_start >= last_trading_day - timedelta(days=5):
                if MarketCalendar.is_trading_day(fetch_start):
                    break
                fetch_start -= timedelta(days=1)

            vix_data = self._vix_fetcher.fetch(fetch_start, last_trading_day)
            if not vix_data or vix_data.get("data_unavailable"):
                return {"data_unavailable": True, "reason": "vix_unavailable"}

            # vix_data is keyed by ISO date string (see VIXFetcher._fetch_vix_data),
            # e.g. {"2026-07-17": {"vix_close": ..., ...}} - not a flat {"vix_close": ...}
            # dict. Take the most recent date's close.
            latest_vix_date = max(vix_data.keys())
            vix_level = vix_data[latest_vix_date].get("vix_close")

            # Fetch breadth (advance/decline, new highs/lows)
            start_date = eval_date - timedelta(days=60)
            breadth_data = self._breadth_fetcher.fetch(start_date, eval_date)
            if not breadth_data or breadth_data.get("data_unavailable"):
                return {"data_unavailable": True, "reason": "breadth_unavailable"}

            # breadth_data is keyed by ISO date string (see BreadthFetcher.fetch),
            # e.g. {"2026-07-17": {"advance_decline_ratio": ..., "new_highs_count": ...,
            # "new_lows_count": ...}} - not a flat dict. Take the most recent date's values.
            latest_breadth_date = max(breadth_data.keys())
            latest_breadth = breadth_data[latest_breadth_date]
            advance_decline = latest_breadth.get("advance_decline_ratio")
            new_highs = latest_breadth.get("new_highs_count")
            new_lows = latest_breadth.get("new_lows_count")

            # Breadth momentum: % of the last 10 trading days (from the same real
            # advance/decline data already fetched above) with more advancers than
            # decliners. Optional enrichment - insufficient history just leaves it
            # unavailable rather than computing a partial/misleading window.
            last_10_dates = sorted(breadth_data.keys())[-10:]
            if len(last_10_dates) < 10:
                breadth_momentum_10d = None
                logger.debug(
                    f"[MARKET_STATUS] breadth_momentum_10d unavailable: only "
                    f"{len(last_10_dates)}/10 days of breadth history available."
                )
            else:
                # CRITICAL: Don't silently default missing advance_decline_ratio to 0
                # That treats a missing field (data error) the same as ratio=0 (down day)
                # Either all 10 days have valid ratio data, or breadth_momentum is unavailable
                missing_ratio_dates = [d for d in last_10_dates if "advance_decline_ratio" not in breadth_data[d]]
                if missing_ratio_dates:
                    logger.warning(
                        f"[MARKET_STATUS] breadth_momentum_10d cannot be computed: "
                        f"advance_decline_ratio missing on {len(missing_ratio_dates)}/10 dates: {missing_ratio_dates}"
                    )
                    breadth_momentum_10d = None
                else:
                    # All dates have ratio data - safe to compute
                    up_days = sum(1 for d in last_10_dates if float(breadth_data[d]["advance_decline_ratio"]) > 1.0)
                    breadth_momentum_10d = round(up_days / 10 * 100, 2)

            # Up-volume percent: real market-wide volume breadth (see BreadthFetcher.
            # fetch_up_volume_percent) - optional enrichment, unavailable is non-fatal.
            up_volume_result = self._breadth_fetcher.fetch_up_volume_percent(eval_date)
            up_volume_percent = (
                up_volume_result.get("up_volume_percent") if not up_volume_result.get("data_unavailable") else None
            )

            # Fetch yield curve (10Y-2Y spread) - use same date range as VIX
            yield_data = self._yield_curve_fetcher.fetch(fetch_start, last_trading_day)
            yield_curve_unavailable = False
            yield_curve_reason = None
            if not yield_data or yield_data.get("data_unavailable"):
                yield_spread = None
                yield_curve_unavailable = True
                # CRITICAL: Distinguish between "reason provided" vs "reason missing"
                if isinstance(yield_data, dict) and "reason" in yield_data:
                    yield_curve_reason = yield_data["reason"]
                else:
                    # Reason missing - don't silently default to "unknown"
                    yield_curve_reason = "yield_curve_fetcher_returned_unavailable_without_reason"
                    logger.warning("[MARKET_STATUS] Yield curve unavailable but reason field missing")
            else:
                # yield_data is keyed by ISO date string (see YieldCurveFetcher._fetch_yield_curve_data),
                # e.g. {"2026-07-17": {"yield_spread": ..., ...}} - not a flat dict, and the field is
                # named "yield_spread" not "yield_10y_2y_spread".
                if not yield_data or not isinstance(yield_data, dict) or not yield_data:
                    yield_spread = None
                    yield_curve_unavailable = True
                    yield_curve_reason = "yield_data_dict_empty_or_invalid"
                    logger.warning(f"[MARKET_STATUS] Yield data is empty/invalid: {type(yield_data).__name__}")
                else:
                    latest_yield_date = max(yield_data.keys())
                    yield_date_record = yield_data.get(latest_yield_date)
                    if not yield_date_record or "yield_spread" not in yield_date_record:
                        yield_spread = None
                        yield_curve_unavailable = True
                        yield_curve_reason = f"yield_spread_missing_on_{latest_yield_date}"
                        logger.warning(
                            f"[MARKET_STATUS] Yield spread missing for latest date {latest_yield_date}. "
                            f"Available keys: {list(yield_date_record.keys()) if yield_date_record else 'None'}"
                        )
                    else:
                        yield_spread = yield_date_record["yield_spread"]

            # Fetch put/call ratio (optional market sentiment indicator)
            put_call = None
            put_call_unavailable = False
            put_call_reason = None
            try:
                put_call_result = self._put_call_fetcher.fetch(eval_date)
                # FAIL-FAST: Explicitly check for data_unavailable flag (missing = error, not "data OK")
                if isinstance(put_call_result, dict) and not put_call_result.get("data_unavailable"):
                    put_call = put_call_result.get("put_call_ratio")
                elif isinstance(put_call_result, dict) and put_call_result.get("data_unavailable"):
                    # Put/call data unavailable - log at WARNING for visibility (not DEBUG)
                    put_call_unavailable = True
                    put_call_reason = put_call_result.get("reason", "unknown")
                    logger.warning(f"[MARKET_STATUS] Put/call ratio unavailable for {eval_date}: {put_call_reason}")
                else:
                    put_call_unavailable = True
                    put_call_reason = "unexpected_response_format"
            except Exception as e:
                # Exception catch is now explicit with WARNING log - not silent DEBUG
                put_call_unavailable = True
                put_call_reason = f"fetcher_error: {str(e)[:100]}"
                logger.warning(f"[MARKET_STATUS] Put/call ratio fetcher failed: {e}")
                # put_call remains None - optional indicator

            # Fetch Federal Reserve funds rate (for policy environment classification)
            fed_rate_data = self._fetch_fed_rate_environment(eval_date)
            fed_rate_environment = fed_rate_data["fed_rate_environment"]
            fed_rate_unavailable = fed_rate_data["fed_rate_data_unavailable"]
            fed_rate_reason = fed_rate_data["fed_rate_unavailable_reason"]

            # CRITICAL FIX (Session 416): Add explicit unavailable markers for breadth_momentum_10d
            # Per GOVERNANCE.md line 47-48: "Every record must have data_unavailable flag"
            # When breadth_momentum_10d is None, set corresponding unavailable flag and reason.
            breadth_momentum_unavailable = breadth_momentum_10d is None
            breadth_momentum_reason = None
            if breadth_momentum_unavailable:
                # Provide reason when data unavailable (see lines 275-290)
                breadth_momentum_reason = "insufficient_breadth_history_or_missing_ratios"
                logger.warning(
                    f"[MARKET_STATUS] breadth_momentum_10d unavailable for {eval_date}: "
                    f"{breadth_momentum_reason}. Marking data_unavailable=True with explicit reason."
                )

            return {
                "data_unavailable": False,
                "vix_level": vix_level,
                "advance_decline_ratio": advance_decline,
                "new_highs": new_highs,
                "new_lows": new_lows,
                "yield_10y_2y_spread": yield_spread,
                "yield_curve_data_unavailable": yield_curve_unavailable,
                "yield_curve_unavailable_reason": yield_curve_reason,
                "put_call_ratio": put_call,
                "put_call_ratio_data_unavailable": put_call_unavailable,
                "put_call_ratio_unavailable_reason": put_call_reason,
                "fed_rate_environment": fed_rate_environment,
                "fed_rate_data_unavailable": fed_rate_unavailable,
                "fed_rate_unavailable_reason": fed_rate_reason,
                "breadth_momentum_10d": breadth_momentum_10d,
                "breadth_momentum_10d_data_unavailable": breadth_momentum_unavailable,
                "breadth_momentum_10d_unavailable_reason": breadth_momentum_reason,
                "up_volume_percent": up_volume_percent,
            }

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Health fetch failed: {e}")
            return {"data_unavailable": True, "reason": f"health_fetch_failed: {e}"[:255]}

    def _compute_market_exposure(self, eval_date: date, health_data: dict[str, Any]) -> dict[str, Any]:
        """Compute market regime and exposure % from health metrics."""
        try:
            from algo.risk.market_exposure import MarketExposure

            # Delegate to MarketExposure compute logic (reuse existing computation)
            exposure = MarketExposure()
            result = exposure.compute(eval_date, force_recompute=False)

            if not result or result.get("data_unavailable"):
                if not result:
                    reason = "exposure_no_result"
                else:
                    reason = result["reason"] if "reason" in result else "exposure_data_unavailable"
                unavailable_result = {
                    "regime": None,
                    "exposure_pct": None,
                    "raw_score": None,
                    "halt_reasons": None,
                    "distribution_days": None,
                    "factors": None,
                    "data_unavailable": True,
                    "reason": reason,
                }
                # CRITICAL FIX: Persist unavailable exposure data to market_exposure_daily
                # even when unavailable, so the table gets updated with data_unavailable=True
                # instead of remaining stale with old data. Without this persist, the table
                # can lag behind market_health_daily by days.
                self._persist_market_exposure(eval_date, unavailable_result)
                return unavailable_result

            result_with_data = {
                "regime": result.get("regime"),
                "exposure_pct": result.get("exposure_pct"),
                "raw_score": result.get("raw_score"),
                "halt_reasons": result.get("halt_reasons"),
                "distribution_days": result.get("distribution_days"),
                "factors": result.get("factors"),
            }
            # CRITICAL FIX: Persist successful exposure data to market_exposure_daily table.
            # The consolidated loader returns this data as part of fetch_incremental's row,
            # but BulkInsertManager silently drops columns that don't exist in market_health_daily
            # (the base table_name). Without this persist, market_exposure_daily never gets updated.
            self._persist_market_exposure(eval_date, result_with_data)
            return result_with_data

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Exposure computation failed: {e}")
            error_result = {
                "regime": None,
                "exposure_pct": None,
                "raw_score": None,
                "halt_reasons": None,
                "distribution_days": None,
                "factors": None,
                "data_unavailable": True,
                # Truncate the FULL formatted string (not just the exception text) to the
                # market_health_daily.reason column's actual VARCHAR(255) limit - the previous
                # str(e)[:100] cut most error messages down to a bare, useless "computed " with
                # no age/threshold, exactly the operator-visibility failure GOVERNANCE.md's
                # "Explicit logging" rule exists to prevent (confirmed live: a real 2h-staleness
                # halt reason was reduced to "...computed " with the actual age silently lost).
                "reason": f"exposure_computation_failed: {e}"[:255],
            }
            # CRITICAL FIX: Persist exception case to market_exposure_daily so error is recorded
            # and table is not left stale.
            try:
                self._persist_market_exposure(eval_date, error_result)
            except Exception as persist_err:
                logger.error(f"[MARKET_STATUS] market_exposure persist also failed: {persist_err}")
            return error_result

    def _compute_market_stage_trend(self, eval_date: date) -> dict[str, Any]:
        """Market stage (Weinstein 1-4) + trend for SPY, derived from `trend_template_data`.

        `market_health_daily.market_stage` had no writer since the Session 275 consolidation
        dropped the standalone `load_market_health_daily.py`'s own SMA-50/SMA-200
        classification logic without replacing it - the column silently stopped being
        populated (last real value: 2026-07-17). Both `circuit_breaker.py`'s CB6 (halts new
        entries when market_stage=4) and its Follow-Through-Day re-engagement check read this
        column with only a 10-day staleness grace window before fail-closed halting, so this
        was a live ticking time bomb for a safety-critical gate, not a cosmetic gap.

        `loaders/load_trend_analysis.py` already computes the identical Weinstein 1-4
        classification for every symbol (including SPY) earlier in the same EOD pipeline run
        and persists it to `trend_template_data` - reuse that instead of recomputing SMA
        classification from price_daily a second time (the "derive, don't re-fetch"
        principle in steering/DATA_LOADERS.md).
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT weinstein_stage, trend_direction, data_unavailable
                    FROM trend_template_data
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 1
                    """,
                    (eval_date,),
                )
                row = cur.fetchone()

            if row is None:
                logger.warning(f"[MARKET_STATUS] No trend_template_data row for SPY on/before {eval_date}")
                return {"market_stage": None, "market_trend": None}

            if len(row) < 3:
                logger.error(
                    f"[MARKET_STATUS] Trend template query returned {len(row)} columns, expected 3. "
                    f"Database schema mismatch or corrupted query result."
                )
                return {"market_stage": None, "market_trend": None}

            weinstein_stage, trend_direction, unavailable = row[0], row[1], row[2]
            if unavailable or weinstein_stage is None:
                logger.warning(
                    f"[MARKET_STATUS] SPY weinstein_stage unavailable in trend_template_data for {eval_date}"
                )
                return {"market_stage": None, "market_trend": None}

            return {"market_stage": int(weinstein_stage), "market_trend": trend_direction}

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Market stage lookup failed: {e}")
            return {"market_stage": None, "market_trend": None}

    def _compute_market_sentiment(self, eval_date: date, health_data: dict[str, Any]) -> dict[str, Any]:
        """Compute fear/greed index and sentiment from VIX + AAII sentiment.

        Persists directly to `market_sentiment` as a side effect (same pattern as
        `MarketExposure.compute()` persisting to `market_exposure_daily`), because
        `market_health_daily` - the only table this loader's return dict is bulk-inserted
        into - has no fear_greed_index/sentiment_score/bullish_pct/bearish_pct/neutral_pct
        columns; those keys were being silently dropped by bulk_insert_manager's
        column-filter behavior with no error, leaving `market_sentiment` unwritten since
        the yfinance-era standalone loader was deprecated.
        """
        vix = health_data.get("vix_level")
        put_call_ratio = health_data.get("put_call_ratio")
        try:
            if not vix:
                result: dict[str, Any] = {
                    "fear_greed_index": None,
                    "sentiment_score": None,
                    "bullish_pct": None,
                    "bearish_pct": None,
                    "neutral_pct": None,
                    "data_unavailable": True,
                    "reason": "vix_unavailable",
                }
                self._persist_market_sentiment(eval_date, vix, put_call_ratio, result)
                return result

            # Map VIX to fear/greed index: VIX 10-50 → fear/greed 80-20
            fear_greed = max(10, min(90, 100 - (vix * 2)))

            # Fetch AAII sentiment (latest within 14 days)
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT date, bullish, bearish, neutral FROM aaii_sentiment
                    WHERE date >= %s - INTERVAL '14 days'
                      AND bullish IS NOT NULL AND bearish IS NOT NULL AND neutral IS NOT NULL
                    ORDER BY date DESC LIMIT 1
                    """,
                    (eval_date,),
                )
                aaii_row = cur.fetchone()

            bullish_pct = bearish_pct = neutral_pct = None
            if aaii_row:
                if len(aaii_row) < 4:
                    logger.error(
                        f"[MARKET_STATUS] AAII sentiment query returned {len(aaii_row)} columns, expected 4. "
                        f"Database schema mismatch or corrupted query result."
                    )
                else:
                    # aaii_sentiment stores as fractions (0-1)
                    bullish_pct = float(aaii_row[1]) * 100
                    bearish_pct = float(aaii_row[2]) * 100
                    neutral_pct = float(aaii_row[3]) * 100
            else:
                logger.debug(f"[MARKET_STATUS] AAII sentiment not available for {eval_date}")

            result = {
                "fear_greed_index": round(fear_greed, 2),
                "sentiment_score": None,  # Computed from bull/bear/neutral if available
                # `is not None`, not truthiness: a genuine 0.0% reading (all bearish,
                # zero bullish) is a real, meaningful value and must not collapse to NULL.
                "bullish_pct": round(bullish_pct, 2) if bullish_pct is not None else None,
                "bearish_pct": round(bearish_pct, 2) if bearish_pct is not None else None,
                "neutral_pct": round(neutral_pct, 2) if neutral_pct is not None else None,
                "data_unavailable": False,
            }
            self._persist_market_sentiment(eval_date, vix, put_call_ratio, result)
            return result

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Sentiment computation failed: {e}")
            result = {
                "fear_greed_index": None,
                "sentiment_score": None,
                "bullish_pct": None,
                "bearish_pct": None,
                "neutral_pct": None,
                "data_unavailable": True,
                "reason": f"sentiment_computation_failed: {e}"[:255],
            }
            try:
                self._persist_market_sentiment(eval_date, vix, put_call_ratio, result)
            except Exception as persist_err:
                logger.error(f"[MARKET_STATUS] market_sentiment persist also failed: {persist_err}")
            return result

    def _persist_market_exposure(self, eval_date: date, exposure: dict[str, Any]) -> None:
        """Write the computed exposure row directly to `market_exposure_daily` (upsert by date).

        CRITICAL FIX: The consolidated loader computes exposure but the base OptimalLoader
        only persists to self.table_name (market_health_daily). BulkInsertManager silently
        drops columns that don't exist in the target table, so exposure_pct/regime/factors
        never reach market_exposure_daily. This explicit persist ensures the table stays fresh.
        """
        import json

        # JSON-serialize halt_reasons and factors for database storage
        halt_reasons_val = exposure.get("halt_reasons")
        halt_reasons_json = json.dumps(halt_reasons_val) if halt_reasons_val is not None else None

        factors_val = exposure.get("factors")
        factors_json = json.dumps(factors_val) if factors_val is not None else None

        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO market_exposure_daily
                    (date, regime, exposure_pct, raw_score, halt_reasons, distribution_days, factors, data_unavailable, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    regime = EXCLUDED.regime,
                    exposure_pct = EXCLUDED.exposure_pct,
                    raw_score = EXCLUDED.raw_score,
                    halt_reasons = EXCLUDED.halt_reasons,
                    distribution_days = EXCLUDED.distribution_days,
                    factors = EXCLUDED.factors,
                    data_unavailable = EXCLUDED.data_unavailable,
                    reason = EXCLUDED.reason,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    eval_date,
                    exposure.get("regime"),
                    exposure.get("exposure_pct"),
                    exposure.get("raw_score"),
                    halt_reasons_json,
                    exposure.get("distribution_days"),
                    factors_json,
                    bool(exposure.get("data_unavailable", False)),
                    exposure.get("reason"),
                ),
            )

    def _persist_market_sentiment(
        self, eval_date: date, vix: float | None, put_call_ratio: float | None, sentiment: dict[str, Any]
    ) -> None:
        """Write the computed sentiment row directly to `market_sentiment` (upsert by date)."""
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO market_sentiment
                    (date, fear_greed_index, put_call_ratio, vix, sentiment_score,
                     bullish_pct, bearish_pct, neutral_pct, data_unavailable, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    fear_greed_index = EXCLUDED.fear_greed_index,
                    put_call_ratio = EXCLUDED.put_call_ratio,
                    vix = EXCLUDED.vix,
                    sentiment_score = EXCLUDED.sentiment_score,
                    bullish_pct = EXCLUDED.bullish_pct,
                    bearish_pct = EXCLUDED.bearish_pct,
                    neutral_pct = EXCLUDED.neutral_pct,
                    data_unavailable = EXCLUDED.data_unavailable,
                    reason = EXCLUDED.reason,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    eval_date,
                    sentiment.get("fear_greed_index"),
                    put_call_ratio,
                    vix,
                    sentiment.get("sentiment_score"),
                    sentiment.get("bullish_pct"),
                    sentiment.get("bearish_pct"),
                    sentiment.get("neutral_pct"),
                    bool(sentiment.get("data_unavailable", False)),
                    sentiment.get("reason"),
                ),
            )

    def load_global(self) -> int:
        """Market-wide loader uses load_global pattern."""
        result = self.run(["market"], parallelism=1)
        if result.get("status") == "SKIPPED_NON_TRADING_DAY":
            return 1
        # CRITICAL FIX: Check for None (missing data) vs 0 (zero rows inserted)
        rows = result.get("rows_inserted")
        if rows is None:
            raise RuntimeError(
                "[MarketStatusDaily] LOADER FAILURE: rows_inserted missing from loader result. "
                "This indicates the market data fetch failed. Check: (1) API connectivity, "
                "(2) VIX/breadth/yields fetcher logs, (3) market health pipeline completion"
            )
        return int(rows)


if __name__ == "__main__":
    sys.exit(
        run_loader(
            MarketStatusDailyLoader,
            description="Consolidated market status (health + exposure + sentiment)",
            global_mode=True,
        )
    )
