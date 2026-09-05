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
import multiprocessing
import queue
import sys
import threading
import time
from collections.abc import Iterable
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.external.yfinance_symbol import to_yfinance_symbol
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Bounds a percentage-change value to avoid overflowing this table's NUMERIC(10,4) columns
# when the base (denominator) is near zero.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# Bounds margin values computed from a near-zero revenue denominator from producing a
# nonsensical trend (thousands of percentage points).
MAX_MARGIN_ABS_PCT = 1000.0


def _bounded_margin_pct(numerator: float | None, denominator: float | None) -> float | None:
    """(numerator / denominator * 100), or None if denominator missing/non-positive or the
    result exceeds MAX_MARGIN_ABS_PCT (near-zero-denominator garbage value)."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    margin = numerator / denominator * 100
    return None if abs(margin) > MAX_MARGIN_ABS_PCT else margin


_YFINANCE_CALL_TIMEOUT_SECONDS = 20.0


def _yfinance_worker_loop(request_queue: Any, response_queue: Any) -> None:
    """Entry point for a persistent yfinance-fetch worker process.

    Module-level (not a closure/lambda) because multiprocessing's "spawn" start method
    (the default on Windows, used here deliberately - see YfinanceProcessWorker's
    docstring) pickles a reference to the target function by import path, which only
    works for something importable at module scope.

    Reads (request_id, symbol, property_name) tuples from request_queue until it sees a
    None sentinel, fetches `getattr(yf.Ticker(symbol), property_name)`, and puts
    (request_id, success, payload) on response_queue - payload is the fetched value on
    success, or the caught exception object on failure. Deliberately does NOT wrap this
    in a broad try/except at the loop level: if something outside a single fetch attempt
    goes wrong (e.g. the queue itself breaks), letting the process die is correct -
    YfinanceProcessWorker.fetch() detects a dead/unresponsive worker via its own
    response_queue.get(timeout=...) and replaces it, same recovery path as a genuine hang.
    """
    import yfinance as yf

    while True:
        item = request_queue.get()
        if item is None:
            return
        request_id, symbol, property_name = item
        try:
            ticker = yf.Ticker(symbol)
            result = getattr(ticker, property_name)
            response_queue.put((request_id, True, result))
        except Exception as e:
            # Some yfinance/curl_cffi exceptions carry unpicklable C-level state that crashes
            # this queue's internal feed thread on put() - re-wrap into a plain RuntimeError
            # (picklable) since no caller here reads more than str(e).
            response_queue.put((request_id, False, RuntimeError(f"{type(e).__name__}: {e}")))


class YfinanceProcessWorker:
    """Persistent subprocess for yfinance property fetches, immune to hangs that defeat
    Thread.join(timeout=N).

    A thread-based timeout can't bound a curl_cffi hang: its blocking C call can hold the
    GIL indefinitely, which starves even the thread trying to enforce the timeout. A
    separate OS process can be forcibly terminated regardless of internal state, so it's
    the only mechanism that actually enforces a timeout here.

    The worker is spawned lazily and reused across the whole run (not respawned per call)
    to amortize yfinance's import cost across the full symbol universe; a timed-out/dead
    worker is terminated and replaced on the next call.
    """

    def __init__(
        self,
        timeout_seconds: float = _YFINANCE_CALL_TIMEOUT_SECONDS,
        worker_target: Any = None,
    ) -> None:
        """worker_target: override the subprocess entry point (defaults to
        _yfinance_worker_loop). Exists so tests can inject a deliberately-hung or
        deterministic fake worker to verify the timeout/recovery mechanism itself
        without depending on a real network hang - see
        test_load_enhanced_quality_growth_metrics_revision_fields.py."""
        self._timeout = timeout_seconds
        self._worker_target = worker_target or _yfinance_worker_loop
        self._next_request_id = 0
        self._process: Any = None
        self._request_queue: Any = None
        self._response_queue: Any = None

    def _ensure_alive(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        ctx = multiprocessing.get_context("spawn")
        self._request_queue = ctx.Queue()
        self._response_queue = ctx.Queue()
        self._process = ctx.Process(
            target=self._worker_target,
            args=(self._request_queue, self._response_queue),
            daemon=True,
        )
        self._process.start()

    def fetch(self, symbol: str, property_name: str) -> Any:
        """Fetch `getattr(yf.Ticker(symbol), property_name)` via the persistent worker.

        Raises TimeoutError if the worker doesn't respond within timeout_seconds - the
        worker is terminated and replaced on the next call, so the caller sees a clean
        exception rather than a hang. Re-raises whatever exception the worker itself hit
        while fetching (e.g. a real yfinance/network error).
        """
        self._ensure_alive()
        self._next_request_id += 1
        request_id = self._next_request_id
        self._request_queue.put((request_id, symbol, property_name))
        try:
            response_id, success, payload = self._response_queue.get(timeout=self._timeout)
        except queue.Empty:
            self._terminate()
            raise TimeoutError(
                f"[{symbol} {property_name}] yfinance call exceeded {self._timeout:.0f}s - worker terminated"
            ) from None

        if response_id != request_id:
            # A response to an earlier request arrived late (e.g. the worker finished the
            # PREVIOUS call just after this class gave up on it and terminated the
            # process - the response was already queued before termination took effect).
            # Discard rather than risk handing the caller a result for the wrong request.
            raise RuntimeError(f"[{symbol} {property_name}] yfinance worker response id mismatch (stale response)")

        if not success:
            raise payload
        return payload

    def _terminate(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=5)
        except Exception:
            pass
        self._process = None
        self._request_queue = None
        self._response_queue = None

    def shutdown(self) -> None:
        """Best-effort clean shutdown - call once at the end of a loader run()."""
        if self._process is None:
            return
        if not self._process.is_alive():
            self._process = None
            return
        try:
            self._request_queue.put(None)
            self._process.join(timeout=5)
        except Exception:
            pass
        if self._process is not None and self._process.is_alive():
            self._terminate()
        else:
            self._process = None


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

    # Instance attribute, but declared at class level so mypy sees the real type instead
    # of inferring None from the first assignment - actual instances get their own None
    # here per Python's normal instance-attribute-shadows-class-attribute lookup, so this
    # is not shared mutable state across instances.
    _yf_worker: "YfinanceProcessWorker | None" = None

    def _get_yf_worker(self) -> "YfinanceProcessWorker":
        """Lazily create (once per run()) the persistent process-isolated yfinance
        fetcher - see YfinanceProcessWorker's docstring for why this replaced the prior
        thread-based `_yfinance_call_with_timeout`. Not created in `__init__` since
        OptimalLoader instances may be constructed without ever calling run() (e.g. for
        introspection/testing) - no reason to spawn a subprocess for those."""
        if self._yf_worker is None:
            self._yf_worker = YfinanceProcessWorker()
        return self._yf_worker

    def run(  # noqa: C901
        self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to write trend metrics to BOTH quality_metrics and growth_metrics.

        Args:
            symbols: Stock ticker symbols to process
            parallelism: Number of parallel workers (default 1)
            backfill_days: Number of days to backfill (passed to parent)
        """
        from utils.loaders.config import get_default_parallelism

        # This loader fully overrides OptimalLoader.run() and never calls super().run(), so
        # it never gets the base class's SLAMonitor wiring for free - wire it up manually.
        sla_monitor = None
        try:
            from utils.loaders.sla_monitor import SLAMonitor

            sla_monitor = SLAMonitor(self.table_name)
            sla_monitor.start()
        except Exception as e:
            logger.warning(f"[{self.table_name}] SLA monitoring failed: {e}")

        def _log_sla_status() -> None:
            if sla_monitor:
                sla_monitor.log_status("info")
                sla_monitor.publish_metric()

        symbols_succeeded = 0
        symbols_failed = 0
        parallelism = parallelism or get_default_parallelism("quality_metrics")

        # Materialize so len() gives a real total for progress reporting, rather than
        # leaving the dashboard frozen at completion_pct=0 for the whole run.
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

            # Bounds total per-symbol work (DB + fetch_incremental), not just the individual
            # yfinance sub-calls - a hung symbol otherwise blocks every symbol queued behind it.
            per_symbol_timeout_seconds = self.per_symbol_timeout_seconds

            for symbol in symbols:
                # Calculate since_date from backfill_days (matching parent behavior)
                from datetime import datetime, timedelta

                from utils.infrastructure.timezone import EASTERN_TZ

                since_date = None
                if self._backfill_days > 0:
                    since_date = datetime.now(EASTERN_TZ).date() - timedelta(days=self._backfill_days)
                else:
                    # Use watermark for incremental loading
                    since_date = self._watermark.get_current_watermark(symbol=symbol)

                outcome: list[str] = ["failed"]
                thread_exc: list[BaseException | None] = [None]

                # Skip symbols the watermark already shows as done today, so a same-day retry
                # resumes instead of re-running all 3 yfinance calls for the whole universe.
                watermark_current = (
                    since_date is not None
                    and self._backfill_days <= 0
                    and since_date >= datetime.now(EASTERN_TZ).date()
                )
                if watermark_current:
                    # Must NOT `continue` past the progress-persist block below, or a same-day
                    # retry (mostly watermark-current symbols) leaves the dashboard frozen at
                    # completion_pct=0 for the whole run.
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

            # quality_metrics/growth_metrics are shared status rows also written by
            # load_value_quality_growth_metrics.py - pass this run's own counts explicitly, or
            # mark_completed's <98%-completion safety check reads the other loader's stale ones.
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

            _log_sla_status()
            return {"symbols_succeeded": symbols_succeeded, "symbols_failed": symbols_failed, "success": success}

        except (psycopg2.Error, ValueError) as e:
            logger.error(f"[ENHANCED] Fatal error: {type(e).__name__}: {e}")
            _log_sla_status()
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[ENHANCED] Fatal unexpected error: {type(e).__name__}: {e}", exc_info=True)
            _log_sla_status()
            return {"success": False, "error": str(e)}
        finally:
            # Clean up the persistent yfinance worker subprocess (see _get_yf_worker) on
            # every exit path - success, a handled fatal error above, or an unexpected
            # exception this method doesn't catch at all. A leaked worker process is a
            # daemon (won't block interpreter exit) but there's no reason to leave one
            # running past this run() call.
            worker = getattr(self, "_yf_worker", None)
            if worker is not None:
                worker.shutdown()
                self._yf_worker = None

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

        # fetch_incremental() can return a truthy {"data_unavailable": True, ...} marker dict
        # (not an empty list) - the `if not metrics` check above only catches an empty list.
        if metric_dict.get("data_unavailable"):
            return

        with DatabaseContext("write") as cur:
            # quarterly_growth_momentum intentionally excluded - load_value_quality_growth_metrics.py
            # is the sole source for that column (see _compute_quarterly_metrics below).
            growth_fields = [
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "sustainable_growth_rate",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
            ]

            update_fields = []
            values = []
            for key in growth_fields:
                if key in metric_dict and metric_dict[key] is not None:
                    update_fields.append(f"{key} = %s")
                    values.append(metric_dict[key])
                    # Clear the paired _unavailable_reason column whenever a real value lands,
                    # or a stale reason from an earlier pass persists forever.
                    update_fields.append(f"{key}_unavailable_reason = NULL")

            if update_fields:
                # Must be NOW() not CURRENT_DATE (date-only) - a date-truncated timestamp never
                # advances within a run, and the scheduler's stall watchdog reads MAX(updated_at)
                # as a liveness signal, so a flat value looks like a hang and gets killed.
                update_fields.append("updated_at = NOW()")
                cur.execute(
                    f"UPDATE growth_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                    [*values, symbol],
                )

            quality_fields = [
                # quality_metrics shares these 4 trend columns with growth_metrics (both
                # populated from one computation) - must be updatable here too, or this
                # loader can refresh growth_metrics' trend columns but never quality_metrics'.
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                # roic_pct intentionally excluded - this loader's formula (no tax adjustment,
                # no debt/cash netting) is a cruder duplicate of
                # load_value_quality_growth_metrics.py's real NOPAT/invested-capital ROIC.
                # This loader runs in both AWS production and the local "metrics" pipeline
                # (scripts/local_loader_scheduler.py), immediately after value_quality_growth.
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
                    # See matching growth_fields comment above - same stale-reason fix.
                    update_fields.append(f"{key}_unavailable_reason = NULL")

            if update_fields:
                # See matching growth_metrics comment above - must be NOW() not CURRENT_DATE.
                update_fields.append("updated_at = NOW()")
                cur.execute(
                    f"UPDATE quality_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                    [*values, symbol],
                )

        outcome[0] = "success"

        # Pairs with the since_date skip check in run() - without advancing the watermark here,
        # a same-day retry would restart the whole universe from scratch. rows_loaded=1 (not 0)
        # so advance_watermark's non-trading-day guard never applies (this is a same-day
        # completion marker, not a trading-calendar date advance).
        from datetime import datetime as _datetime

        from utils.infrastructure.timezone import EASTERN_TZ as _EASTERN_TZ

        self._watermark.advance_watermark(new_watermark=_datetime.now(_EASTERN_TZ).date(), symbol=symbol, rows_loaded=1)

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[dict[str, Any]]:  # noqa: C901
        # Pre-existing complexity debt (ruff C901), not refactored here under time pressure.
        """Compute enhanced metrics for symbol."""
        with DatabaseContext("read") as cur:
            # Exclude data_unavailable placeholder rows for the current, not-yet-filed fiscal
            # year, or income_rows[0] below is treated as "current year" when it's really an
            # all-NULL placeholder, silently no-op'ing every metric for that symbol.
            cur.execute(
                """
                SELECT i.fiscal_year, i.revenue, i.operating_income, i.net_income,
                       b.total_assets, b.stockholders_equity, b.current_liabilities,
                       c.operating_cash_flow, c.financing_cash_flow
                FROM annual_income_statement i
                LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
                LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
                WHERE i.symbol = %s AND i.data_unavailable IS NOT TRUE
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

            # roic_pct intentionally not computed here - see quality_fields list comment above.

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

                # YoY Growth metrics - only compute if both current and prior values exist and
                # prior > 0. Each is bounded by MAX_TREND_PERCENTAGE_POINTS: a near-zero
                # prior-year base can overflow the NUMERIC(10,4) column, and since
                # growth_fields/quality_fields are written as one multi-column UPDATE, a single
                # unbounded field aborting the statement would erase every other field for
                # that symbol too.
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

            # Small delay spreads out the yfinance request rate across the full-universe run
            # to avoid throttling (same trade-off used elsewhere, see
            # utils/loaders/config.py LOADER_CONSTRAINTS).
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
            from utils.loaders.retry_helper import retry_with_backoff

            yf_symbol = to_yfinance_symbol(symbol)

            # Retried so a single transient yfinance failure isn't indistinguishable from real
            # absence. Fetched via the process-isolated YfinanceProcessWorker (see its
            # docstring) - a thread-based timeout can't bound a genuine curl_cffi hang.
            earnings_dates = retry_with_backoff(
                lambda: self._get_yf_worker().fetch(yf_symbol, "earnings_dates"),
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

        yf.Ticker(symbol).eps_trend is a DataFrame indexed by period ('0q'/'+1q'/'0y'/'+1y')
        with current/7/30/60/90-days-ago consensus EPS columns; eps_revisions (same index) has
        upLast/downLast N-days analyst-revision counts. Uses the '0q' (current-quarter) row as
        the most immediately actionable window.

        Retries the fetch itself (not just logs-and-gives-up on first failure): this call
        transiently fails even for symbols with real data available, so a bare no-retry
        except swallowed real coverage as if it were genuine "no analyst coverage".
        """
        try:
            from utils.loaders.retry_helper import retry_with_backoff

            yf_symbol = to_yfinance_symbol(symbol)

            # max_retries=4/backoff=3.0s (~45s total, capped by RetryHelper's 32s/attempt
            # ceiling) survives sustained per-IP throttling over a full-universe run. Fetched
            # via the process-isolated YfinanceProcessWorker (see its docstring) since an
            # in-process yf.Ticker call can't be bounded by a thread-based timeout.
            eps_trend = retry_with_backoff(
                lambda: self._get_yf_worker().fetch(yf_symbol, "eps_trend"),
                context=f"{symbol} eps_trend",
                max_retries=4,
                backoff_seconds=3.0,
            )
            eps_revisions = retry_with_backoff(
                lambda: self._get_yf_worker().fetch(yf_symbol, "eps_revisions"),
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
            # WARNING not DEBUG: reaching here means retries were exhausted, worth surfacing
            # rather than blending into "no coverage for this symbol".
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
                ORDER BY period_end DESC NULLS LAST, fiscal_year DESC, fiscal_quarter DESC
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
                            # Log at WARNING, not silently pass - hides real data quality issues.
                            logger.warning(
                                f"[{symbol}] Failed to calculate eps_growth_stability: {type(e).__name__}: {e}. "
                                f"Metric will be marked data_unavailable."
                            )

            # quarterly_growth_momentum intentionally not computed here (sequential-QoQ EPS
            # growth) - it would clobber load_value_quality_growth_metrics.py's canonical
            # YoY-revenue value, which is the sole source for that column.


def main() -> int:
    """Entry point."""
    try:
        return run_loader(EnhancedQualityGrowthMetricsLoader)
    except Exception as e:
        logger.error(f"[ENHANCED_METRICS] Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
