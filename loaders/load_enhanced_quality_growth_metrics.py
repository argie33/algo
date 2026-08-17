#!/usr/bin/env python3
"""Enhanced Quality + Growth Metrics - Extended beyond annual data.

Adds 21 new computed fields to quality_metrics and growth_metrics:

TREND FIELDS (from historical annual data, computed YoY):
- gross_margin_trend: (current - prior year) / prior year
- operating_margin_trend: (current - prior year) / prior year
- net_margin_trend: (current - prior year) / prior year
- roe_trend: (current - prior year) / prior year
- net_income_growth_yoy: (current - prior year) / prior year
- operating_income_growth_yoy: (current - prior year) / prior year
- fcf_growth_yoy: (current - prior year) / prior year
- ocf_growth_yoy: (current - prior year) / prior year
- asset_growth_yoy: (current - prior year) / prior year
- quarterly_growth_momentum: Average quarterly growth rate (if available)
- sustainable_growth_rate: ROE * retention ratio

EARNINGS/ESTIMATE FIELDS (from yfinance earnings data):
- earnings_surprise_avg: Average earnings surprise over last 4 quarters
- eps_growth_stability: Std dev of quarterly EPS growth
- earnings_beat_rate: % quarters beating estimates
- consecutive_positive_quarters: Count of consecutive quarters with positive earnings
- estimate_revision_direction: Net up/down of analyst estimate revisions
- revision_activity_30d: Number of estimate revisions in last 30 days
- estimate_momentum_60d/90d: Trend in analyst estimates over 60/90 days
- revision_trend_score: Composite revision momentum
- earnings_growth_4q_avg: Average EPS growth last 4 quarters

This loader enhances the existing quality_metrics and growth_metrics rows
by adding these new columns as UPDATE operations.
"""

import logging
import sys
import threading
import time
from collections.abc import Iterable
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Guards against a near-zero EPS-estimate base blowing up a percentage-change calculation
# into a value that overflows this table's NUMERIC(10,4) revision columns (max magnitude
# 999,999.9999) - same class of guard as load_value_quality_growth_metrics.py's
# MAX_TREND_PERCENTAGE_POINTS, applied here to estimate_momentum_60d/90d and
# revision_trend_score.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# CRITICAL FIX 2026-08-09: same near-zero-revenue-denominator bound as commits 12063b32a/
# 5ceda9952 (which bounded gross_margin/ebitda_margin/roic_pct/operating_margin/net_margin
# in load_value_quality_growth_metrics.py at |ratio| <= 1000). This loader recomputes
# gross/operating/net margin independently from raw annual_income_statement rows to derive
# *_margin_trend/roe_trend, using the same revenue-denominator division pattern, but never
# inherited the bound - a garbage current-year or prior-year margin (e.g. near-zero revenue)
# was flowing straight into a trend value in the thousands of percentage points.
MAX_MARGIN_ABS_PCT = 1000.0


def _bounded_margin_pct(numerator: float | None, denominator: float | None) -> float | None:
    """(numerator / denominator * 100), or None if denominator missing/non-positive or the
    result exceeds MAX_MARGIN_ABS_PCT (near-zero-denominator garbage value)."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    margin = numerator / denominator * 100
    return None if abs(margin) > MAX_MARGIN_ABS_PCT else margin


_YFINANCE_CALL_TIMEOUT_SECONDS = 20.0


def _yfinance_call_with_timeout(fn: Any, context: str, timeout_seconds: float = _YFINANCE_CALL_TIMEOUT_SECONDS) -> Any:
    """Run a single yfinance property fetch on a daemon thread and abandon it if it
    doesn't return within timeout_seconds.

    LIVE-REPRODUCED 2026-08-10: ticker.earnings_dates hung for 40+ minutes on one symbol
    (py-spy showed the main thread idle inside curl_cffi's perform() the entire time),
    blocking the whole loader (and everything queued behind it in local_loader_scheduler.py's
    "metrics" pipeline). yfinance's own _make_request has a timeout=30 default, but that's
    passed to curl_cffi - which is NOT built on Python's socket module, so this codebase's
    usual socket.setdefaulttimeout() fix (used elsewhere for yfinance hangs, e.g.
    utils/external/yfinance_analyst_ratings.py) has no effect on it either, and
    retry_with_backoff can't help since a truly-hung call never raises for it to catch.
    Same daemon-thread-abandon pattern as load_financial_statements.py's proven per-symbol
    timeout (2026-08-09) - daemon=True so an abandoned thread can't block process exit.
    """
    result: list[Any] = [None]
    exc: list[BaseException | None] = [None]

    def _run() -> None:
        try:
            result[0] = fn()
        except BaseException as e:
            exc[0] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(
            f"[{context}] yfinance call exceeded {timeout_seconds:.0f}s - abandoning (thread left running)"
        )
    if exc[0] is not None:
        raise exc[0]
    return result[0]


class EnhancedQualityGrowthMetricsLoader(OptimalLoader):
    """Adds 21 new computed metrics to existing quality_metrics and growth_metrics.

    Runs after load_value_quality_growth_metrics to enhance with trend analysis
    and earnings estimate data.
    """

    table_name = "quality_metrics"  # Primary table for status tracking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0
    exclude_etfs_from_symbols = True

    # Class attribute (not a run() local) so tests can shrink it instead of waiting 60s.
    per_symbol_timeout_seconds = 60.0

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run() to write trend metrics to BOTH quality_metrics and growth_metrics.

        Args:
            symbols: Stock ticker symbols to process
            parallelism: Number of parallel workers (default 1)
            backfill_days: Number of days to backfill (passed to parent)
        """
        from utils.loaders.config import get_default_parallelism

        symbols_succeeded = 0
        symbols_failed = 0
        parallelism = parallelism or get_default_parallelism("quality_metrics")

        # DASHBOARD ACCURACY FIX 2026-08-17: materialize so len() gives a real total for
        # progress reporting - same "frozen at 0% for the entire run" bug class just fixed
        # in load_prices.py (PriceLoader called mark_running()/mark_completed() only, nothing
        # in between). Live-confirmed here too: this loader's own per-symbol log lines show
        # real forward motion while data_loader_status sat at completion_pct=0/symbols_loaded=0
        # for over an hour, indistinguishable from a hang.
        symbols = list(symbols)
        total_symbols = len(symbols)

        try:
            # Use LoaderStatusManager for centralized status updates (RACE CONDITION FIX)
            for table in ["quality_metrics", "growth_metrics"]:
                status_mgr = LoaderStatusManager(table)
                status_mgr.mark_running()

            # Apply backfill_days override if provided
            if backfill_days is not None:
                self._backfill_days = backfill_days

            # PER-SYMBOL TIMEOUT FIX 2026-08-16: live-reproduced today - this loop had NO bound
            # on total per-symbol work (DB reads/writes + fetch_incremental), only the individual
            # yfinance sub-calls inside it were capped at 20s each. growth_metrics/quality_metrics
            # went silent (zero log output, any level) after committing a normal per-symbol write
            # at 16:07:42 and stayed silent for 4+ hours until local_loader_scheduler's external
            # "0%% stall for >1800s" watchdog force-killed the subprocess - a genuinely-hung symbol
            # anywhere in this loop blocks every symbol queued behind it with no visibility into
            # which one. Same daemon-thread-abandon-with-timeout containment already proven for
            # this exact failure class in load_financial_statements.py's per-symbol timeout
            # (2026-08-09) - bounds each symbol to per_symbol_timeout_seconds regardless of root
            # cause, so the loop always keeps moving and logs which symbol stalled.
            per_symbol_timeout_seconds = self.per_symbol_timeout_seconds

            for symbol in symbols:
                # Calculate since_date from backfill_days (matching parent behavior)
                from datetime import datetime, timedelta
                from datetime import timezone as tz

                since_date = None
                if self._backfill_days > 0:
                    since_date = datetime.now(tz.utc).date() - timedelta(days=self._backfill_days)
                else:
                    # Use watermark for incremental loading
                    since_date = self._watermark.get_current_watermark(symbol=symbol)

                outcome: list[str] = ["failed"]
                thread_exc: list[BaseException | None] = [None]

                # ROOT-CAUSE FIX 2026-08-17: since_date was read from the watermark above but
                # never used to skip already-current symbols, and nothing in this loader ever
                # advanced the watermark after a symbol succeeded (see _process_one_symbol) - so
                # every invocation, including same-day retries after a partial failure/timeout,
                # unconditionally re-ran all 3 yfinance calls (earnings_dates/eps_trend/
                # eps_revisions) for the full ~4,900-symbol universe. Live-measured 2026-08-17:
                # ~2.9s/symbol -> ~4h for one full run, serially blocking every downstream
                # "metrics" pipeline loader (analyst_upgrade_downgrade/analyst_sentiment/
                # stability_metrics/scores/buy_sell) queued behind it in PIPELINES["metrics"].
                # Skipping symbols the watermark already shows as done today lets a same-day
                # retry resume instead of restarting the entire universe from scratch.
                watermark_current = (
                    since_date is not None and self._backfill_days <= 0 and since_date >= datetime.now(tz.utc).date()
                )
                if watermark_current:
                    # PROGRESS-UPDATE FIX 2026-08-17: this branch must NOT `continue` past the
                    # progress-persist block below - a same-day retry where most/all symbols are
                    # already watermark-current would then skip that block for the whole run,
                    # leaving the dashboard frozen at completion_pct=0 for exactly the retry
                    # case an operator is most likely to be anxiously watching.
                    logger.debug(f"[ENHANCED] {symbol}: watermark={since_date} already current today, skipping")
                    symbols_succeeded += 1
                else:
                    # Default-arg binding (evaluated now, not at call time): otherwise every
                    # closure across loop iterations shares the same enclosing-scope cells, and
                    # an abandoned (timed-out but not actually dead - daemon threads can't be
                    # force-killed) thread that finishes later would write into whatever
                    # symbol/outcome/thread_exc is current *at that point*, silently corrupting a
                    # different symbol's result.
                    def _process_symbol(
                        self: "EnhancedQualityGrowthMetricsLoader" = self,
                        symbol: str = symbol,
                        since_date: date | None = since_date,
                        outcome: list[str] = outcome,
                        thread_exc: list[BaseException | None] = thread_exc,
                    ) -> None:
                        try:
                            self._process_one_symbol(symbol, since_date, outcome)
                        except (ValueError, KeyError) as e:
                            logger.error(f"[ENHANCED] {symbol}: Data structure error: {e}")
                        except Exception as e:
                            thread_exc[0] = e

                    thread = threading.Thread(target=_process_symbol, daemon=True)
                    thread.start()
                    thread.join(timeout=per_symbol_timeout_seconds)

                    if thread.is_alive():
                        logger.error(
                            f"[ENHANCED] {symbol}: exceeded per-symbol timeout "
                            f"({per_symbol_timeout_seconds:.0f}s) - abandoning (thread left running) "
                            "and moving on to the next symbol."
                        )
                        symbols_failed += 1
                    elif thread_exc[0] is not None:
                        # exc_info can't be passed here (LOG014: only valid inside an except
                        # block) - this is a captured exception object from the abandoned worker
                        # thread, not one currently being handled, so log its repr instead of a
                        # live traceback.
                        logger.error(f"[ENHANCED] {symbol}: Unexpected error: {thread_exc[0]!r}")
                        symbols_failed += 1
                    elif outcome[0] == "success":
                        symbols_succeeded += 1
                    else:
                        symbols_failed += 1

                processed = symbols_succeeded + symbols_failed
                if processed % 50 == 0 or processed == total_symbols:
                    completion_pct = 100.0 * processed / max(total_symbols, 1)
                    for table in ["quality_metrics", "growth_metrics"]:
                        try:
                            LoaderStatusManager(table).update_progress(
                                symbols_loaded=processed,
                                symbol_count=total_symbols,
                                completion_pct=completion_pct,
                            )
                        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                            logger.error(
                                f"[ENHANCED] Progress update failed for {table} (dashboard will "
                                f"show stale completion_pct until next successful update): "
                                f"{type(e).__name__}: {str(e)[:100]}"
                            )

            success = symbols_succeeded > 0
            fail_rate = (symbols_failed / max(symbols_succeeded + symbols_failed, 1)) * 100

            # Use LoaderStatusManager for final status (RACE CONDITION FIX)
            # FIX 2026-08-09: quality_metrics/growth_metrics are shared status rows also
            # written by load_value_quality_growth_metrics.py. A bare mark_completed() (no
            # current_run_* overrides) makes its internal <98%-completion safety check
            # re-read whatever symbol_count/symbols_loaded THAT OTHER loader last wrote,
            # instead of this run's own real counts - so this loader's actual completeness
            # was never actually verified by that safety check. Passing this run's own
            # symbols_succeeded/attempted counts closes that gap (same pattern as the
            # 2026-08-03 fix documented in LoaderStatusManager.mark_completed's docstring).
            for table in ["quality_metrics", "growth_metrics"]:
                status_mgr = LoaderStatusManager(table)
                if success and fail_rate <= self.max_fail_rate:
                    status_mgr.mark_completed(
                        current_run_symbols_loaded=symbols_succeeded,
                        current_run_symbol_count=symbols_succeeded + symbols_failed,
                    )
                else:
                    status_mgr.mark_failed(
                        error_message=f"Failed symbols: {symbols_failed}/{symbols_failed + symbols_succeeded}",
                        completion_pct=100.0 * symbols_succeeded / max(symbols_succeeded + symbols_failed, 1),
                    )

            return {"symbols_succeeded": symbols_succeeded, "symbols_failed": symbols_failed, "success": success}

        except (psycopg2.Error, ValueError) as e:
            logger.error(f"[ENHANCED] Fatal error: {type(e).__name__}: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[ENHANCED] Fatal unexpected error: {type(e).__name__}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _process_one_symbol(self, symbol: str, since_date: date | None, outcome: list[str]) -> None:
        """Fetch + write metrics for one symbol. Sets outcome[0]='success' on a real write.

        Split out of run() so the per-symbol timeout wrapper there can run this whole unit
        of work (DB reads, yfinance calls, DB writes) on a daemon thread and bound it, instead
        of only bounding the yfinance sub-calls inside fetch_incremental().
        """
        metrics = self.fetch_incremental(symbol, since_date)
        if not metrics:
            logger.error(f"[ENHANCED] {symbol}: fetch_incremental returned empty list")
            return

        metric_dict = metrics[0]

        # FIX 2026-08-09: fetch_incremental() returns a truthy
        # {"data_unavailable": True, "reason": ...} marker dict (not an empty list)
        # when the symbol has no annual_income_statement history - the `if not
        # metrics` check above only catches an empty list, not this marker. Without
        # this check, the marker dict has none of the growth_fields/quality_fields
        # keys, so both update_fields lists below stay empty, no UPDATE ever runs,
        # and the caller would silently count zero real data written as a success.
        # Same bug class as earnings_calendar's fetch-failure placeholder rows
        # fooling Phase 8 (see earnings_calendar_placeholder_false_rejection_fix_20260809).
        if metric_dict.get("data_unavailable"):
            return

        with DatabaseContext("write") as cur:
            growth_fields = [
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "sustainable_growth_rate",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
                "quarterly_growth_momentum",
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
            ]

            update_fields = []
            values = []
            for key in growth_fields:
                if key in metric_dict and metric_dict[key] is not None:
                    update_fields.append(f"{key} = %s")
                    values.append(metric_dict[key])

            if update_fields:
                # ROOT-CAUSE FIX 2026-08-16: was "updated_at = CURRENT_DATE" (date-only,
                # truncates to midnight) - every UPDATE for the rest of the same calendar
                # day wrote the identical value, so MAX(updated_at) never advanced during
                # a run. Live-confirmed: this loader ran for 30+ min actively computing and
                # committing per-symbol updates (log showed continuous ENHANCED_METRICS
                # writes through hundreds of symbols) while growth_metrics/quality_metrics
                # both stayed frozen at their pre-run updated_at - the scheduler's stall
                # watchdog reads MAX(updated_at) as one of its 3 liveness signals and,
                # seeing it flat, killed a genuinely-working loader as a false stall
                # (same bug class as [[loader_timestamp_precision_systemic_fix]]).
                update_fields.append("updated_at = NOW()")
                cur.execute(
                    f"UPDATE growth_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                    [*values, symbol],
                )

            quality_fields = [
                # CRITICAL FIX 2026-08-10: quality_metrics has the same
                # gross_margin_trend/operating_margin_trend/net_margin_trend/roe_trend
                # columns as growth_metrics (load_value_quality_growth_metrics.py's
                # own _SHARED_TREND_FIELDS convention mirrors these 4 fields to BOTH
                # tables from one computation), but this loader's quality_fields list
                # never included them while growth_fields above always has - so this
                # loader's per-symbol UPDATE (a partial/conditional SET - only columns
                # present in metric_dict are touched) could refresh growth_metrics'
                # trend columns but could NEVER refresh or clear quality_metrics'
                # corresponding columns, even when this same fetch_incremental() call
                # just computed a fresh, correctly-bounded value for both. Live-
                # confirmed: growth_metrics garbage rows (ABS(trend) > 2000) dropped
                # from 275 to 252 over a ~50-symbol-per-minute full-universe run while
                # quality_metrics' count sat unchanged at 281 the entire time - this
                # loader was structurally incapable of clearing them.
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                # roic_pct REMOVED 2026-08-03: found while fixing
                # quality_metrics.roic_pct's real gap (was hardcoded unavailable in
                # load_value_quality_growth_metrics.py, now computes real
                # NOPAT/invested-capital ROIC using actual SEC-reported income tax
                # data, migration 1178). This loader's own roic_pct formula
                # (operating_income / (total_assets - current_liabilities), no tax
                # adjustment, no debt/cash netting) is a strictly cruder duplicate.
                #
                # CORRECTION 2026-08-09: this comment used to also claim "this loader
                # isn't wired into any active pipeline" as the reason the removal was
                # only theoretical ("if this loader were ever scheduled..."). That was
                # already false the day it was written - terraform/modules/pipeline/
                # main.tf's EnhancedQualityGrowthMetrics Step Functions state and
                # terraform/modules/loaders/main.tf's loader_file_map both schedule
                # this loader in AWS production (a separate same-day 2026-08-03 fix
                # enabled it), running after ValueQualityGrowthMetrics on the real
                # quality_metrics/growth_metrics tables. It does NOT run in the local
                # dev pipeline (scripts/local_loader_scheduler.py has zero references
                # to it), so this file's behavior cannot be verified via a local
                # orchestrator run - only in AWS. The roic_pct removal above was and
                # is load-bearing in production, not a hypothetical.
                "earnings_surprise_avg",
                "eps_growth_stability",
                "earnings_beat_rate",
                "consecutive_positive_quarters",
                "estimate_revision_direction",
                "revision_activity_30d",
                "estimate_momentum_60d",
                "estimate_momentum_90d",
                "revision_trend_score",
                "earnings_growth_4q_avg",
            ]

            update_fields = []
            values = []
            for key in quality_fields:
                if key in metric_dict and metric_dict[key] is not None:
                    update_fields.append(f"{key} = %s")
                    values.append(metric_dict[key])

            if update_fields:
                # ROOT-CAUSE FIX 2026-08-16: was "updated_at = CURRENT_DATE" (date-only,
                # truncates to midnight) - every UPDATE for the rest of the same calendar
                # day wrote the identical value, so MAX(updated_at) never advanced during
                # a run. Live-confirmed: this loader ran for 30+ min actively computing and
                # committing per-symbol updates (log showed continuous ENHANCED_METRICS
                # writes through hundreds of symbols) while growth_metrics/quality_metrics
                # both stayed frozen at their pre-run updated_at - the scheduler's stall
                # watchdog reads MAX(updated_at) as one of its 3 liveness signals and,
                # seeing it flat, killed a genuinely-working loader as a false stall
                # (same bug class as [[loader_timestamp_precision_systemic_fix]]).
                update_fields.append("updated_at = NOW()")
                cur.execute(
                    f"UPDATE quality_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                    [*values, symbol],
                )

        outcome[0] = "success"

        # ROOT-CAUSE FIX 2026-08-17: pairs with the since_date skip check in run() - without
        # advancing the watermark here, that check could never trigger (get_current_watermark
        # would always see None/stale), so a same-day retry would still restart the whole
        # universe from scratch. rows_loaded=1 (not 0) so advance_watermark's non-trading-day
        # guard (utils/data/watermark.py) never applies here - this is a same-day completion
        # marker, not a trading-calendar date advance.
        from datetime import datetime as _datetime
        from datetime import timezone as _timezone

        self._watermark.advance_watermark(
            new_watermark=_datetime.now(_timezone.utc).date(), symbol=symbol, rows_loaded=1
        )

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[dict[str, Any]]:  # noqa: C901
        # Pre-existing complexity debt, surfaced now that the ruff pre-commit hook actually
        # runs (see .pre-commit-config.yaml's 2026-08-10 fix) - not refactoring a finance-
        # metrics computation under time pressure; same call made for market_events.py's
        # check_market_circuit_breaker.
        """Compute enhanced metrics for symbol."""
        with DatabaseContext("read") as cur:
            # Get historical financial data for trend computation
            cur.execute(
                """
                SELECT i.fiscal_year, i.revenue, i.operating_income, i.net_income,
                       b.total_assets, b.stockholders_equity, b.current_liabilities,
                       c.operating_cash_flow, c.financing_cash_flow
                FROM annual_income_statement i
                LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
                LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
                WHERE i.symbol = %s
                ORDER BY i.fiscal_year DESC
                LIMIT 5
            """,
                (symbol,),
            )

            income_rows = cur.fetchall()
            if not income_rows:
                return [{"symbol": symbol, "data_unavailable": True, "reason": "no_historical_data"}]

        # Compute trend metrics
        metrics: dict[str, Any] = {"symbol": symbol}

        try:
            # Extract current year data
            curr_fy, curr_rev, curr_oi, curr_ni, curr_assets, curr_equity, _curr_curr_liab, curr_fcf, curr_ocf = (
                income_rows[0]
            )

            # Convert all to float early to avoid Decimal type issues
            curr_rev_f = safe_float(curr_rev, "revenue")
            curr_oi_f = safe_float(curr_oi, "operating_income")
            curr_ni_f = safe_float(curr_ni, "net_income")
            curr_assets_f = safe_float(curr_assets, "assets")
            curr_equity_f = safe_float(curr_equity, "equity")
            curr_fcf_f = safe_float(curr_fcf, "fcf")
            curr_ocf_f = safe_float(curr_ocf, "ocf")

            # roic_pct computation REMOVED 2026-08-03 - see this loader's quality_fields list
            # comment above for why (confirmed-duplicate, cruder formula vs.
            # load_value_quality_growth_metrics.py's real tax-adjusted NOPAT computation).

            # Get prior year data if available
            if len(income_rows) > 1:
                (
                    prior_fy,
                    prior_rev,
                    prior_oi,
                    prior_ni,
                    prior_assets,
                    prior_equity,
                    _prior_curr_liab,
                    prior_fcf,
                    prior_ocf,
                ) = income_rows[1]

                # Convert prior year values too
                prior_rev_f = safe_float(prior_rev, "revenue")
                prior_oi_f = safe_float(prior_oi, "operating_income")
                prior_ni_f = safe_float(prior_ni, "net_income")
                prior_assets_f = safe_float(prior_assets, "assets")
                prior_equity_f = safe_float(prior_equity, "equity")
                prior_fcf_f = safe_float(prior_fcf, "fcf")
                prior_ocf_f = safe_float(prior_ocf, "ocf")

                # YoY Growth metrics - only compute if both current and prior values exist and prior > 0
                #
                # CRITICAL FIX 2026-08-10: none of these 5 fields had the
                # MAX_TREND_PERCENTAGE_POINTS bound this file already applies to
                # estimate_momentum_60d/90d/revision_trend_score - a near-zero prior-year base
                # (same class of bug as the margin-trend near-zero-denominator fix elsewhere in
                # this file) produces a ratio that overflows the NUMERIC(10,4) column
                # (max magnitude 999,999.9999). Live-confirmed: ALLT ocf_growth_yoy=1,113,500.0,
                # CHAI ocf_growth_yoy=27,256,085.3 - both raised psycopg2.NumericValueOutOfRange
                # on the UPDATE. Because growth_fields/quality_fields are written as ONE
                # multi-column UPDATE per table, that exception aborted the ENTIRE statement -
                # silently losing every other field for that symbol in the same UPDATE, including
                # the correctly-bounded gross_margin_trend/operating_margin_trend/net_margin_trend/
                # roe_trend values computed earlier in this same fetch_incremental() call. A single
                # unbounded field was capable of erasing otherwise-good data for the whole symbol.
                if prior_oi_f and prior_oi_f > 0 and curr_oi_f is not None:
                    oi_growth = ((curr_oi_f or 0) - (prior_oi_f or 0)) / prior_oi_f * 100
                    if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["operating_income_growth_yoy"] = float(oi_growth)
                if prior_ni_f and prior_ni_f > 0 and curr_ni_f is not None:
                    ni_growth = ((curr_ni_f or 0) - (prior_ni_f or 0)) / prior_ni_f * 100
                    if abs(ni_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["net_income_growth_yoy"] = float(ni_growth)

                if prior_assets_f and prior_assets_f > 0 and curr_assets_f is not None:
                    asset_growth = ((curr_assets_f or 0) - (prior_assets_f or 0)) / prior_assets_f * 100
                    if abs(asset_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["asset_growth_yoy"] = float(asset_growth)

                if prior_fcf_f and prior_fcf_f > 0 and curr_fcf_f is not None:
                    fcf_growth = ((curr_fcf_f or 0) - (prior_fcf_f or 0)) / prior_fcf_f * 100
                    if abs(fcf_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["fcf_growth_yoy"] = float(fcf_growth)

                if prior_ocf_f and prior_ocf_f > 0 and curr_ocf_f is not None:
                    ocf_growth = ((curr_ocf_f or 0) - (prior_ocf_f or 0)) / prior_ocf_f * 100
                    if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["ocf_growth_yoy"] = float(ocf_growth)

                # Margin trends
                if prior_rev_f and prior_rev_f > 0 and curr_rev_f and curr_rev_f > 0:
                    # Get COGS from income statement to compute margins
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT fiscal_year, cost_of_revenue, gross_profit
                            FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year IN (%s, %s)
                            ORDER BY fiscal_year DESC
                        """,
                            (symbol, curr_fy, prior_fy),
                        )

                        margin_rows = cur.fetchall()
                        if len(margin_rows) == 2:
                            # Current year margin (using gross_profit / revenue)
                            curr_gross_profit = safe_float(margin_rows[0][2], "gross_profit")
                            curr_cogs = safe_float(margin_rows[0][1], "cogs")
                            prior_gross_profit = safe_float(margin_rows[1][2], "gross_profit")
                            prior_cogs = safe_float(margin_rows[1][1], "cogs")

                            # Fallback: compute gross_profit from revenue - COGS if not directly available
                            if curr_gross_profit is None and curr_cogs is not None:
                                curr_gross_profit = curr_rev_f - curr_cogs
                            if prior_gross_profit is None and prior_cogs is not None:
                                prior_gross_profit = prior_rev_f - prior_cogs

                            curr_gross_margin = _bounded_margin_pct(curr_gross_profit, curr_rev_f)
                            prior_gross_margin = _bounded_margin_pct(prior_gross_profit, prior_rev_f)
                            if curr_gross_margin is not None and prior_gross_margin is not None:
                                metrics["gross_margin_trend"] = float(curr_gross_margin - prior_gross_margin)

                            # Operating margin trend
                            curr_op_margin = _bounded_margin_pct(curr_oi_f, curr_rev_f)
                            prior_op_margin = _bounded_margin_pct(prior_oi_f, prior_rev_f)
                            if curr_op_margin is not None and prior_op_margin is not None:
                                metrics["operating_margin_trend"] = float(curr_op_margin - prior_op_margin)

                            # Net margin trend
                            curr_net_margin = _bounded_margin_pct(curr_ni_f, curr_rev_f)
                            prior_net_margin = _bounded_margin_pct(prior_ni_f, prior_rev_f)
                            if curr_net_margin is not None and prior_net_margin is not None:
                                metrics["net_margin_trend"] = float(curr_net_margin - prior_net_margin)

                # ROE trend
                if curr_equity_f and curr_equity_f > 0 and prior_equity_f and prior_equity_f > 0:
                    curr_roe = _bounded_margin_pct(curr_ni_f, curr_equity_f)
                    prior_roe = _bounded_margin_pct(prior_ni_f, prior_equity_f)
                    if curr_roe and prior_roe:
                        metrics["roe_trend"] = float(curr_roe - prior_roe)

                # Sustainable growth rate = ROE * retention ratio. Left unset (not a fabricated
                # assumed retention ratio) because this loader's fetch_incremental() query never
                # selects dividends_paid, so a real retention ratio = (earnings - dividends) /
                # earnings can't be computed here. The sibling loader
                # load_value_quality_growth_metrics.py does fetch dividends_paid and computes
                # this field for real - that's the live path stock_scores actually reads from.

            # Compute quarterly earnings metrics (includes consecutive_positive_quarters, eps_growth_stability, etc.)
            self._compute_quarterly_metrics(symbol, metrics)

            # Log computed quarterly metrics for debugging
            quarterly_fields = [
                "consecutive_positive_quarters",
                "earnings_growth_4q_avg",
                "eps_growth_stability",
                "quarterly_growth_momentum",
            ]
            computed_quarterly = {k: v for k, v in metrics.items() if k in quarterly_fields and v is not None}
            if computed_quarterly:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed quarterly metrics: {computed_quarterly}")
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No quarterly metrics computed")

            # Compute earnings surprise and beat rate from yfinance
            self._compute_earnings_surprise_metrics(symbol, metrics)

            # Log computed surprise metrics for debugging
            surprise_fields = ["earnings_surprise_avg", "earnings_beat_rate"]
            computed_surprise = {k: v for k, v in metrics.items() if k in surprise_fields and v is not None}
            if computed_surprise:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed surprise metrics: {computed_surprise}")

            # PACING FIX 2026-08-10: estimate_revision_direction/revision_activity_30d/
            # estimate_momentum_60d/90d/revision_trend_score were only ~8-9% populated
            # (498-551/5701 in quality_metrics) vs. earnings_surprise_avg/earnings_beat_rate
            # computed by this SAME loader run at ~59-60% - despite live spot-checks showing
            # real yfinance eps_trend/eps_revisions data available for the large majority of
            # sampled symbols. A full-universe run makes 3 yfinance calls/symbol back-to-back
            # for ~25 minutes with zero pacing; this small delay spreads the request rate out,
            # same trade-off (slower, more complete) already applied to stock_prices_daily/
            # positioning_metrics/value_metrics for the identical yfinance-throttling failure
            # mode (see utils/loaders/config.py LOADER_CONSTRAINTS comments). Needs a fresh
            # full run to confirm coverage actually improves.
            time.sleep(0.3)

            # Compute estimate revision trend metrics from yfinance eps_trend/eps_revisions
            self._compute_estimate_revision_metrics(symbol, metrics)

            revision_fields = [
                "estimate_revision_direction",
                "revision_activity_30d",
                "estimate_momentum_60d",
                "estimate_momentum_90d",
                "revision_trend_score",
            ]
            computed_revision = {k: v for k, v in metrics.items() if k in revision_fields and v is not None}
            if computed_revision:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed revision metrics: {computed_revision}")

            for field in revision_fields:
                if field not in metrics:
                    metrics[field] = None

            metrics["updated_at"] = date.today().isoformat()
            metrics["data_unavailable"] = False

            return [metrics]

        except Exception as e:
            logger.error(f"[ENHANCED_METRICS] {symbol}: Computation failed: {e}")
            return [{"symbol": symbol, "data_unavailable": True, "reason": str(e)}]

    def _compute_earnings_surprise_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute earnings surprise and beat rate from yfinance earnings dates.

        Uses yfinance earnings_dates which provides:
        - EPS Estimate: Analyst consensus EPS estimate
        - Reported EPS: Actual reported EPS
        - Surprise(%): (Reported - Estimate) / Estimate * 100
        """
        try:
            import yfinance as yf

            from utils.loaders.retry_helper import retry_with_backoff

            ticker = yf.Ticker(symbol)

            # Get last 4 quarters of earnings data. Retried (2026-08-09) for the same reason
            # as _compute_estimate_revision_metrics's eps_trend/eps_revisions fetch - a single
            # transient yfinance failure here shouldn't be indistinguishable from real absence.
            # Each attempt is timeout-bounded (2026-08-10 fix; the eps_trend/eps_revisions sibling
            # call was NOT actually wrapped despite this comment claiming parity - live-reproduced
            # 2026-08-16 hanging the loader for 30+min until the scheduler's external stall-killer
            # intervened - see _yfinance_call_with_timeout's docstring for why a hang here can't
            # just be caught by retry_with_backoff on its own).
            earnings_dates = retry_with_backoff(
                lambda: _yfinance_call_with_timeout(lambda: ticker.earnings_dates, f"{symbol} earnings_dates"),
                context=f"{symbol} earnings_dates",
                max_retries=2,
                backoff_seconds=1.0,
            )
            if earnings_dates is None or earnings_dates.empty:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No earnings_dates from yfinance")
                return

            # Take most recent 4 reported earnings
            reported = earnings_dates[earnings_dates["Reported EPS"].notna()].head(4)
            if len(reported) < 2:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: Only {len(reported)} quarters with reported EPS")
                return

            surprises = reported["Surprise(%)"].dropna()
            if len(surprises) > 0:
                # Average surprise over available quarters (guard against outlier earnings surprises)
                avg_surprise = float(surprises.mean())
                if abs(avg_surprise) < MAX_TREND_PERCENTAGE_POINTS:
                    metrics["earnings_surprise_avg"] = avg_surprise

                # Beat rate: % of quarters with positive surprise
                beat_count = (surprises > 0).sum()
                beat_rate = (beat_count / len(surprises)) * 100
                if beat_rate <= 100:  # Should always be <=100 but guard anyway
                    metrics["earnings_beat_rate"] = float(beat_rate)

                logger.info(
                    f"[ENHANCED_METRICS] {symbol}: earnings_surprise_avg={metrics['earnings_surprise_avg']:.2f}%, earnings_beat_rate={metrics['earnings_beat_rate']:.2f}%"
                )
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No surprise data in earnings_dates")

        except ImportError:
            logger.debug(f"[ENHANCED_METRICS] {symbol}: yfinance not available")
        except Exception as e:
            logger.warning(
                f"[ENHANCED_METRICS] {symbol}: Could not fetch earnings surprise after retries: {type(e).__name__}: {e}"
            )

    def _compute_estimate_revision_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute analyst estimate revision trend metrics from yfinance eps_trend/eps_revisions.

        Live-verified 2026-08-04: yf.Ticker(symbol).eps_trend is a real DataFrame indexed by
        period ('0q'/'+1q'/'0y'/'+1y') with current/7daysAgo/30daysAgo/60daysAgo/90daysAgo
        consensus EPS columns; yf.Ticker(symbol).eps_revisions is a real DataFrame (same index)
        with upLast7days/upLast30days/downLast30days/downLast7Days analyst-revision counts.
        Uses the '0q' (current-quarter) row - the most immediately actionable estimate window,
        matching the same non-`.info` API family already used for forward_eps
        (utils/external/yfinance_analyst_ratings.py) and upgrades_downgrades.

        CONFIRMED 2026-08-09: on a full-universe run, this call transiently fails for many
        symbols that DO have real eps_trend/eps_revisions data (live-verified: CMS, D, TNDM all
        got a real earnings_surprise_avg from _compute_earnings_surprise_metrics on the same run,
        proving the symbol/loader/DB path works, yet estimate_momentum_60d/revision_activity_30d
        stayed NULL - re-fetching eps_trend for the same symbols moments later succeeded
        instantly). The bare `except Exception: logger.debug(...)` below used to swallow this
        indistinguishably from genuine "no analyst coverage", with no retry - explains most of
        the low (~7-8%) coverage on these fields despite real data being available. Now retries
        the fetch itself before giving up.
        """
        try:
            import yfinance as yf

            from utils.loaders.retry_helper import retry_with_backoff

            ticker = yf.Ticker(symbol)

            # PACING FIX 2026-08-10: bumped from max_retries=2/backoff=1.0s (~3s total wait) to
            # max_retries=4/backoff=3.0s (~45s total wait, capped by RetryHelper's 32s/attempt
            # ceiling) - the shorter window wasn't enough to survive sustained per-IP throttling
            # over this loader's ~25min full-universe run (measured coverage stayed ~8-9% even
            # after the original retry fix landed and ran live - see this method's docstring).
            eps_trend = retry_with_backoff(
                lambda: _yfinance_call_with_timeout(lambda: ticker.eps_trend, f"{symbol} eps_trend"),
                context=f"{symbol} eps_trend",
                max_retries=4,
                backoff_seconds=3.0,
            )
            eps_revisions = retry_with_backoff(
                lambda: _yfinance_call_with_timeout(lambda: ticker.eps_revisions, f"{symbol} eps_revisions"),
                context=f"{symbol} eps_revisions",
                max_retries=4,
                backoff_seconds=3.0,
            )

            if eps_trend is not None and not eps_trend.empty and "0q" in eps_trend.index:
                row = eps_trend.loc["0q"]
                current = row.get("current")
                ago_60 = row.get("60daysAgo")
                ago_90 = row.get("90daysAgo")

                if current is not None and ago_60 not in (None, 0):
                    momentum_60d = ((current - ago_60) / abs(ago_60)) * 100
                    if abs(momentum_60d) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["estimate_momentum_60d"] = float(round(momentum_60d, 2))

                if current is not None and ago_90 not in (None, 0):
                    momentum_90d = ((current - ago_90) / abs(ago_90)) * 100
                    if abs(momentum_90d) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["estimate_momentum_90d"] = float(round(momentum_90d, 2))

                momentum_values = [
                    v
                    for v in (metrics.get("estimate_momentum_60d"), metrics.get("estimate_momentum_90d"))
                    if v is not None
                ]
                if momentum_values:
                    metrics["revision_trend_score"] = float(round(sum(momentum_values) / len(momentum_values), 2))
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No eps_trend '0q' row from yfinance")

            if eps_revisions is not None and not eps_revisions.empty and "0q" in eps_revisions.index:
                row = eps_revisions.loc["0q"]
                up_30d = row.get("upLast30days")
                down_30d = row.get("downLast30days")

                if up_30d is not None and down_30d is not None:
                    metrics["revision_activity_30d"] = float(up_30d + down_30d)
                    metrics["estimate_revision_direction"] = float(up_30d - down_30d)
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No eps_revisions '0q' row from yfinance")

        except ImportError:
            logger.debug(f"[ENHANCED_METRICS] {symbol}: yfinance not available")
        except Exception as e:
            # WARNING not DEBUG (2026-08-09): retries above already absorb transient blips;
            # a failure reaching here means 2 retries were exhausted, which is worth surfacing
            # instead of silently blending into "no coverage for this symbol".
            logger.warning(
                f"[ENHANCED_METRICS] {symbol}: Could not fetch estimate revisions after retries: "
                f"{type(e).__name__}: {e}"
            )

    def _compute_quarterly_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute metrics from quarterly earnings data."""
        with DatabaseContext("read") as cur:
            # Get last 8 quarters of earnings data
            cur.execute(
                """
                SELECT fiscal_year, fiscal_quarter, earnings_per_share, net_income
                FROM quarterly_income_statement
                WHERE symbol = %s AND data_unavailable IS NOT TRUE
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT 8
            """,
                (symbol,),
            )

            quarters = cur.fetchall()
            if not quarters or len(quarters) < 2:
                return

            # quarters is sorted newest first
            eps_values = [safe_float(q[2], "earnings_per_share") for q in quarters]  # EPS
            ni_values = [safe_float(q[3], "net_income") for q in quarters]  # Net Income
            valid_eps = [e for e in eps_values if e is not None]

            # Compute consecutive positive quarters (from most recent going backwards)
            consecutive_positive = 0
            for ni in ni_values:
                if ni is not None and ni > 0:
                    consecutive_positive += 1
                else:
                    break
            if consecutive_positive > 0:
                metrics["consecutive_positive_quarters"] = float(consecutive_positive)

            # Compute EPS growth rates over last 4 quarters (if we have 5 quarters)
            if len(valid_eps) >= 5:
                eps_growth_rates = []
                for i in range(len(valid_eps) - 1):
                    if valid_eps[i + 1] is not None and valid_eps[i + 1] != 0:
                        growth = (valid_eps[i] - valid_eps[i + 1]) / abs(valid_eps[i + 1])
                        eps_growth_rates.append(growth)

                if eps_growth_rates:
                    # Average EPS growth (last 4 quarters)
                    if len(eps_growth_rates) >= 4:
                        avg_growth = sum(eps_growth_rates[:4]) / 4
                        avg_growth_pct = avg_growth * 100
                        # Guard against overflow: EPS near-zero can cause huge percentage swings
                        if abs(avg_growth_pct) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["earnings_growth_4q_avg"] = float(avg_growth_pct)

                    # EPS growth stability (standard deviation)
                    if len(eps_growth_rates) >= 2:
                        import statistics

                        try:
                            stdev = statistics.stdev(eps_growth_rates)
                            # Cap stability metric too (same reason as growth rates)
                            if stdev < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["eps_growth_stability"] = float(stdev)
                        except (ValueError, statistics.StatisticsError) as e:
                            # CRITICAL FIX 2026-08-02: Log failed calculations at WARNING level
                            # Silent pass hides data quality issues (insufficient data, invalid values)
                            logger.warning(
                                f"[{symbol}] Failed to calculate eps_growth_stability: {type(e).__name__}: {e}. "
                                f"Metric will be marked data_unavailable."
                            )

            # Compute quarterly growth momentum (average of recent quarterly growth rates)
            if len(valid_eps) >= 4:
                recent_growth = []
                for i in range(min(4, len(valid_eps) - 1)):
                    if valid_eps[i + 1] is not None and valid_eps[i + 1] != 0:
                        growth = (valid_eps[i] - valid_eps[i + 1]) / abs(valid_eps[i + 1]) * 100
                        recent_growth.append(growth)
                if recent_growth:
                    momentum = sum(recent_growth) / len(recent_growth)
                    # Guard against overflow: same near-zero EPS issue
                    if abs(momentum) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["quarterly_growth_momentum"] = float(momentum)


def main() -> int:
    """Entry point."""
    try:
        return run_loader(EnhancedQualityGrowthMetricsLoader)
    except Exception as e:
        logger.error(f"[ENHANCED_METRICS] Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
