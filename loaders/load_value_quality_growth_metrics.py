#!/usr/bin/env python3
"""Consolidated Value + Quality + Growth Metrics Loader.

CONSOLIDATION: Merges 2 separate metric loaders into one:
  - load_yfinance_derived_metrics.py (reads yfinance_snapshot → value_metrics + others)
  - load_quality_growth_metrics.py (reads financial_statements → quality + growth)

CRITICAL DEPENDENCY: Requires these to run first (Session 271 - yfinance-free):
  1. load_financial_statements.py → annual_income_statement, balance_sheet, cash_flow
  2. load_sec_valuations.py → sec_valuations (computed PE/PB/PS/PEG/FCF)

Data Flow (SEC-only, no yfinance):
  Phase 1: load_financial_statements.py fetches SEC data
  Phase 1: load_sec_valuations.py computes PE/PB/PS/PEG/FCF from SEC
  Phase 2: load_value_quality_growth_metrics.py (THIS LOADER) - SEC ONLY
    ├─ Reads: sec_valuations (PE, PB, PS, PEG, FCF, dividend yield)
    ├─ Reads: financial_statements (ROE, margins, EPS growth)
    ├─ Computes: value_metrics (PE, PB, PS, PEG, FCF, dividend yield - no yfinance)
    ├─ Computes: quality_metrics (ROE, margins, debt ratios)
    ├─ Computes: growth_metrics (revenue/EPS growth)
    └─ Writes: value_metrics, quality_metrics, growth_metrics (3 tables)

Benefits:
  - 1 ECS task instead of 2 (saves ~$0.05-0.10/run + 10-15 min runtime)
  - All value/quality/growth metrics computed together (atomic operation)
  - Single validation point (one fail-fast path)
  - Eliminates ~5,300 yfinance quoteSummary calls/day
  - Better data quality (SEC-audited valuations)
  - All metric families computed once from fresh SEC data
  - Easier to maintain (single loader, single error handler)

Run: python3 loaders/load_value_quality_growth_metrics.py [--symbols AAPL,MSFT]
"""

import itertools
import logging
import sys
import time
from datetime import date, datetime, timezone
from math import isnan, sqrt
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# SESSION 114+ FIX: Use full timestamp (with time component) instead of just date.
# Previously date.today().isoformat() produced "2026-08-12" which casts to "2026-08-12 00:00:00",
# making data always appear to be from midnight even when loader runs in afternoon.
# This caused freshness monitor to report stale data 16+ hours after actual load time.
# Now captures current time at module load (when run() is invoked) - all rows get same timestamp.
_LOADER_RUN_TIMESTAMP = None


def get_loader_timestamp() -> str:
    """Get the current run timestamp (ISO format with time component).

    Initialized on first call to capture when the loader run() started.
    All rows written in this run will have the same timestamp for consistency.
    """
    global _LOADER_RUN_TIMESTAMP
    if _LOADER_RUN_TIMESTAMP is None:
        _LOADER_RUN_TIMESTAMP = datetime.now(timezone.utc).isoformat()
    return _LOADER_RUN_TIMESTAMP


def peg_ratio_reason_from_eps_history(eps_rows: list[tuple[Any, Any]]) -> str:
    """Given the two most recent (fiscal_year, earnings_per_share) rows (newest first, both
    non-NULL EPS), decide why peg_ratio is unavailable when pe_ratio IS present.

    FIXED 2026-08-18 (live audit, "no SEC data" follow-up): this branch was hardcoded
    "missing_sec_data" regardless of cause. load_sec_valuations.py only computes peg_ratio
    when growth_rate = (ttm_eps - prior_year_eps) / |prior_year_eps| is > 0 (declining or
    newly-profitable earnings make PEG not meaningful, same "not applicable" class as
    unprofitable_stock/non_dividend_paying_stock elsewhere in this file). Live audit: 1273 of
    1282 universe rows in this exact state (pe present, peg NULL, "missing_sec_data") have
    declining or newly-positive EPS - only 8 are genuine missing-prior-year-EPS gaps.

    Args:
        eps_rows: 0-2 (fiscal_year, earnings_per_share) tuples, already filtered to non-NULL
            EPS and ordered fiscal_year DESC (i.e. exactly what the caller's DB query returns).
    """
    if len(eps_rows) < 2:
        return "missing_sec_data"
    ttm_eps_for_growth, prior_eps_for_growth = eps_rows[0][1], eps_rows[1][1]
    if prior_eps_for_growth is None or prior_eps_for_growth <= 0:
        return "negative_earnings_growth"
    if ttm_eps_for_growth is not None and ttm_eps_for_growth <= prior_eps_for_growth:
        return "negative_earnings_growth"
    return "missing_sec_data"


def intrinsic_value_reason_from_fcf_yield(fcf_yield: float | None) -> str:
    """Decide why intrinsic_value_per_share (the DCF result) is unavailable when it's NULL.

    FIXED 2026-08-18 (goal session, value_metrics audit): this was collapsed to
    "missing_cash_flow_data" if fcf_yield is None else "implausible_dcf_result" on the
    assumption that fcf_yield being present implied FCF was positive - but fcf_yield only
    requires being within [-1000%, 1000%] of market cap, not being positive, and
    load_sec_valuations.py's _compute_dcf_intrinsic_value's very first gate is `fcf <= 0`
    (the 2-stage FCFE model can't discount a company that burned cash that year). Live audit:
    100% of the 2184 implausible_dcf_result rows (2177 negative + 7 zero) had fcf_yield <= 0 -
    same "not applicable" class as unprofitable_stock/non_dividend_paying_stock elsewhere in
    this file, not a genuinely implausible computed result.

    Args:
        fcf_yield: sec_valuations.fcf_yield for this symbol (same sign as the FCF that fed
            the DCF, since both derive from the same ocf - capex over the same positive
            market_cap).
    """
    if fcf_yield is None:
        return "missing_cash_flow_data"
    if fcf_yield <= 0:
        return "negative_free_cash_flow"
    return "implausible_dcf_result"


# GOVERNANCE: quality/growth metrics previously stamped updated_at=today() regardless of
# how old the underlying SEC fiscal-year data was - verified live examples scoring stocks
# off 13-17 year old financials as if freshly updated (LPL/SID fiscal_year 2009-2012). The
# universe's actual fiscal-year-age distribution has a sharp cliff at 2 years (156 symbols
# at age=2, only 6 at age=3) - real active filers report annually with at most ~2 years of
# lag through this pipeline, so anything older is either delisted/inactive or a genuine
# data gap that must be flagged, not silently scored as current.
MAX_FISCAL_YEAR_AGE_YEARS = 3

# Sanity bound for the 4 percentage-point-delta trend fields below (gross/operating/net
# margin trend, ROE trend) - all stored in NUMERIC(10,4) columns (max abs value < 10^6).
# A near-zero prior-year denominator (stockholders_equity/revenue close to $0, common for
# a company that just crossed from negative to barely-positive equity/revenue) makes the
# prior-period ratio - and therefore the delta - mathematically enormous despite being a
# "real" computation, not a data-fetch bug. Live-confirmed: ORKA's roe_trend computed as
# 8,372,395.55 (prior_year_stockholders_equity was a few dollars from a recent capital
# raise/burn crossover), which overflowed the DB column and rolled back the entire
# 3-table (value/quality/growth) write transaction for that symbol - not just quality_metrics,
# also discarding an otherwise-good value_metrics row. Treating an implausible delta as
# unavailable (like the existing ROIC tax-rate bound elsewhere in this file) instead of
# storing it prevents that crash without fabricating a fake capped number.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# ADDED 2026-08-28 (goal: Growth-formula quality pass, user-directed): MAX_TREND_PERCENTAGE_
# POINTS above only ever existed to stop a NUMERIC column overflow crash - it was never a
# plausibility bound, and 100,000% is far too loose to catch a near-zero-denominator artifact
# before it gets displayed/scored as if it were real. Live-confirmed universe-wide sweep:
# net_income_growth_yoy (196 symbols >1000%, max 99,900% - one tick under the overflow wall),
# earnings_growth_4q_avg (160 symbols, max 70,022%), fcf_growth_yoy (158 symbols, max 56,806%),
# eps_growth_1y (70 symbols, max 88,476%), revenue_growth_1y (67 symbols, max a nonsensical
# 1,631,667% - _compute_period_growth below had NO bound at all, not even the loose one),
# sustainable_growth_rate (37 symbols, max 24,155%), quarterly_growth_momentum (27 symbols,
# max 50,362%). None of these are real growth rates - a genuine hypergrowth small-cap can
# realistically hit a few hundred percent, essentially never four or five digits. 2000% is
# generous enough to keep real extreme-but-real cases (a company going from near-breakeven to
# solidly profitable) while rejecting near-zero-denominator noise. Growth-RATE fields only -
# margin/ROE trend fields (gross_margin_trend/operating_margin_trend/net_margin_trend/
# roe_trend) stay on MAX_TREND_PERCENTAGE_POINTS above: those are percentage-POINT deltas
# bounded by the 0-100% margin range in practice, a different scale/failure mode not covered
# by this sweep.
MAX_PLAUSIBLE_GROWTH_PCT = 2_000.0

# Sanity bound for absolute-dollar fields (free_cash_flow, operating_cash_flow, total_debt,
# total_cash, ebitda) - all stored in NUMERIC(15,2) columns (max abs value < 10^13, i.e.
# $10 trillion). Live-confirmed via the 2026-08-09 metrics pipeline run: VFS and KEP (both
# foreign filers reporting in local currency - VND/KRW) overflowed this column, aborting
# the entire 3-table quality/value/growth write transaction for those symbols - not just
# the one garbage field, the whole row, same failure mode as MAX_TREND_PERCENTAGE_POINTS
# above.
#
# UPDATE 2026-08-19 (goal: factor-input-sources audit): root cause fixed upstream in
# sec_statements.py on 2026-08-17 - KRW is now in fx_rates.py's MAJOR_CURRENCIES and gets
# converted to USD via a real historical FX rate before it ever reaches this file (VND is
# not a major currency, so VFS's local-currency facts are dropped to NULL rather than
# converted - also correct, just a different resolution). Live-reverified 2026-08-19: KEP's
# sec_valuations row (total_debt=$10.8B, ebitda=$15.1B) and annual_income_statement revenue
# ($62.77B, matches KEPCO's real FY2024 revenue) are both now correctly USD-scaled. BUT the
# fix only applies going forward through the normal incremental fetch - a symbol whose
# annual_balance_sheet/annual_income_statement/annual_cash_flow rows were last written
# BEFORE 2026-08-17 keeps the old raw-local-currency values until something re-fetches that
# symbol (no new filing means the incremental cursor has no reason to re-pull it). Live
# DB scan 2026-08-19: SKM/KT/SKHY/GGAL/BMA/BBAR/IBN/KSPI/TEO/SMFG/MUFG/etc. still carry
# pre-fix raw-currency values (e.g. SKM operating_cash_flow=5,087,285,000,000, exactly the
# raw KRW SEC fact) dated 2026-08-18 20:xx or earlier - the currently-running metrics
# pipeline scheduler (PID 26892, started 2026-08-19T09:44 UTC per algo-scheduler.lock) is
# progressively correcting these as it works through the symbol queue (KEP flipped to the
# correct value at 2026-08-19 10:00 in this same run). This bound stays as a safety net
# regardless - it only prevents the crash-and-lose-everything symptom by marking the
# implausible value unavailable instead of writing it, and remains correct for any future
# currency/scale bug of this shape.
MAX_ABSOLUTE_DOLLAR_VALUE = 1_000_000_000_000.0  # $1 trillion - no real company in this universe exceeds this for any single one of these fields

# Computed once in _compute_quality_metrics (needs balance-sheet data _compute_growth_metrics
# doesn't have), then mirrored into growth_dict in fetch_incremental - see that call site for
# why quality_metrics and growth_metrics each carry their own copy of the same values.
# These are computed from quarterly data in _compute_quarterly_metrics() (which is called
# from _compute_quality_metrics), and must be propagated to growth_metrics via this list
# to avoid dropping quarterly-derived metrics that growth_metrics doesn't compute on its own.
_SHARED_TREND_FIELDS = (
    "net_income_growth_yoy",
    "operating_income_growth_yoy",
    "gross_margin_trend",
    "operating_margin_trend",
    "net_margin_trend",
    "roe_trend",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy",
    "consecutive_positive_quarters",
    "earnings_growth_4q_avg",
    "eps_growth_stability",
    "earnings_surprise_avg",
    "earnings_beat_rate",
)


class ValueQualityGrowthMetricsLoader(OptimalLoader):
    """Consolidated value + quality + growth metrics from SEC + valuations.

    Writes to 3 output tables in single per-symbol transaction:
    - value_metrics (PE, PB, PS, PEG, FCF, dividend yield from SEC)
    - quality_metrics (ROE, margins, debt ratios from SEC)
    - growth_metrics (revenue/EPS growth from SEC)
    """

    # ADDED 2026-08-31 (goal session: "VCIG tops the scores, dig in" investigation,
    # continuation of load_sec_valuations.py's MIN_PLAUSIBLE_PB_RATIO/PE_RATIO fix - see
    # that constant's docstring for the full VCIG evidence). forward_pe = current_price /
    # forward_eps below had no plausibility floor at all (unlike pe_ratio/pb_ratio/
    # ps_ratio, which are computed in load_sec_valuations.py and got this same floor
    # earlier in this session) - a symbol whose tiny real share count inflates every
    # per-share figure (forward EPS included) would win percentile 100 in Value's
    # _percent_rank_cheap_high the same way VCIG's pe/pb/ps did, just via its forward
    # estimate instead. Same 0.05 floor, same "exclude from the percentile universe
    # rather than force a floor/ceiling score" treatment.
    MIN_PLAUSIBLE_FORWARD_PE_RATIO = 0.05

    # TIGHTENED 2026-09-01 (goal session, "get the missing data"/"bizarre results" audit) -
    # same fix, same rationale, as load_sec_valuations.py's MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO
    # (see that constant's docstring for the live-confirmed evidence: HVT.A 63%/#1 Value rank,
    # JEM/HTCR 95%, LZM 92%, TASK 88%, 30+ symbols above 30%, no genuine case found above it).
    # This file's TIER 3/TIER 4 dividend_yield fallbacks below copied the same now-corrected
    # <=1.0 bound from that file's primary computation - kept in sync here for the same reason.
    MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO = 0.30

    table_name = "value_metrics"  # Primary table for watermarking
    # Deliberately NOT declaring output_tables here (unlike e.g. load_sector_industry_daily).
    # That mechanism makes runner.py force quality_metrics/growth_metrics to the SAME
    # success/failure verdict as the primary table - correct for loaders with one shared
    # per-symbol outcome, wrong here: this loader tracks value/quality/growth failures
    # independently (see per_table_counts below, and the quality_succeeded/growth_succeeded
    # comment near their declaration) specifically because they fail independently in real
    # data (216 symbols: value ok, growth unavailable).
    #
    # CRITICAL: This loader's run() method handles marking ALL THREE tables independently
    # with their own per-table success/failure counts (lines 347-360). It queries each table's
    # MAX(updated_at) independently and calls mark_completed() separately for each.
    # runner.py's output_tables mechanism would force all 3 to the same verdict, losing
    # the independent tracking. Do NOT add output_tables or runner.py will break this.
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0  # CRITICAL: Fail-fast if >20% of liquid stocks lack SEC data (data source issue). Foreign/OTC/microcaps expected to fail.
    exclude_etfs_from_symbols = True

    def run(  # noqa: C901
        self, symbols: list[str], parallelism: int | None = None, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to write to 3 tables instead of 1.

        backfill_days: accepted for interface parity with runner.py's generic --backfill-days/
        BACKFILL_DAYS CLI/env path (loaders/runner.py calls loader.run(symbols, parallelism=...,
        backfill_days=...) whenever either is set) - unused here since fetch_incremental() always
        recomputes from the latest SEC/sec_valuations rows rather than filtering by date.
        """
        from utils.loaders.config import get_default_parallelism

        start_time = time.time()

        # This loader fully overrides OptimalLoader.run() (writes 3 tables per-symbol) and
        # never calls super().run(), so it never got the SLAMonitor wiring the base class
        # does - confirmed 2026-08-23 during the goal session's "meet our SLAs" audit (see
        # [[sla_monitor_table_name_key_mismatches_fixed_20260823]]). LOADER_SLA_TARGETS had
        # no "value_metrics" entry either; added one below calibrated from real log durations
        # (consistently ~30-40s across multiple 2026-08-21/22 runs).
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

        value_inserts = 0
        quality_inserts = 0
        growth_inserts = 0
        symbols_succeeded = 0
        symbols_failed = 0
        # Tracked independently from symbols_succeeded/symbols_failed (which reflect only
        # value_row - see the completion-pct fix below) because quality_row/growth_row come
        # from different source queries and fail independently in practice: live-confirmed
        # 216 symbols where value_metrics succeeds but growth_metrics is unavailable, and 18
        # where value succeeds but quality is unavailable. Reusing value's counter for all 3
        # tables' completion_pct would silently mask quality/growth-specific failure rates.
        quality_succeeded = 0
        quality_failed = 0
        growth_succeeded = 0
        growth_failed = 0

        parallelism = parallelism or get_default_parallelism("value_quality_growth_metrics")

        try:
            # Mark all 3 tables as loading via LoaderStatusManager (uses advisory locks)
            managers = {}
            for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                manager = LoaderStatusManager(table)
                manager.mark_running(symbol_count=len(symbols))
                managers[table] = manager

            # Process each symbol
            for symbol in symbols:
                try:
                    # Fetch all metrics for symbol
                    metrics = self.fetch_incremental(symbol, None)
                    if not metrics:
                        logger.error(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: fetch_incremental returned empty list (CRITICAL BUG)"
                        )
                        symbols_failed += 1
                        quality_failed += 1
                        growth_failed += 1
                        continue

                    # Debug: check metrics structure before unpacking
                    if not isinstance(metrics, list) or not metrics[0]:
                        logger.error(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: metrics is {type(metrics)}, metrics[0] is {type(metrics[0]) if metrics else 'None'} (CRITICAL BUG)"
                        )
                        symbols_failed += 1
                        quality_failed += 1
                        growth_failed += 1
                        continue

                    metric_tuple = metrics[0]
                    if not isinstance(metric_tuple, tuple) or len(metric_tuple) != 3:
                        logger.error(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: metric_tuple is {type(metric_tuple)}, len={len(metric_tuple) if hasattr(metric_tuple, '__len__') else 'unknown'} (expected tuple of 3)"
                        )
                        symbols_failed += 1
                        quality_failed += 1
                        growth_failed += 1
                        continue

                    # Extract metrics tuple
                    value_row, quality_row, growth_row = metric_tuple

                    # Fetch value_score from stock_scores to sync into value_metrics
                    if value_row:
                        try:
                            with DatabaseContext("read") as cur:
                                cur.execute("SELECT value_score FROM stock_scores WHERE symbol = %s", (symbol,))
                                score_row = cur.fetchone()
                                if score_row and score_row[0] is not None:
                                    value_row["value_score"] = score_row[0]
                        except Exception as e:
                            logger.debug(
                                f"[VALUE_QUALITY_GROWTH] {symbol}: Could not fetch value_score from stock_scores: {e}"
                            )

                    # Write to all 3 tables in single transaction. GOVERNANCE: always upsert
                    # all 3, even when value_row is data_unavailable - quality_row/growth_row
                    # are computed independently above (different source queries), so a value
                    # metrics failure must not discard them. This branch previously `continue`d
                    # here before ever reaching the quality/growth inserts below, leaving those
                    # 2 tables with NO row at all (not even an unavailable marker) for any
                    # symbol whose value metrics failed - live-confirmed 44 such symbols in the
                    # local DB, all missing from quality_metrics/growth_metrics entirely despite
                    # having a real value_metrics row. Same bug class the comment below already
                    # fixed for the quality/growth-specific unavailable case.
                    with DatabaseContext("write") as cur:
                        # Insert value metrics (ALWAYS present, either data or unavailable marker)
                        self._insert_value_metrics(cur, value_row)
                        value_inserts += 1

                        # Insert quality metrics (write the unavailable marker too, same as
                        # value_metrics above - GOVERNANCE: previously this branch only wrote
                        # on success and skipped the write entirely when data_unavailable=True,
                        # so a symbol whose quality data later became unavailable (stale fiscal
                        # data, source removed, etc.) kept showing its last-good row forever
                        # with no way to ever downgrade it. Always upsert so the table reflects
                        # current truth.
                        if quality_row:
                            self._insert_quality_metrics(cur, quality_row)
                            if not quality_row.get("data_unavailable"):
                                quality_inserts += 1
                                quality_succeeded += 1
                            else:
                                logger.warning(
                                    f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics unavailable: {quality_row.get('reason')}"
                                )
                                quality_failed += 1
                        else:
                            quality_failed += 1

                        # Insert growth metrics (same reasoning as quality metrics above).
                        if growth_row:
                            self._insert_growth_metrics(cur, growth_row)
                            if not growth_row.get("data_unavailable"):
                                growth_inserts += 1
                                growth_succeeded += 1
                            else:
                                logger.warning(
                                    f"[VALUE_QUALITY_GROWTH] {symbol}: Growth metrics unavailable: {growth_row.get('reason')}"
                                )
                                growth_failed += 1
                        else:
                            growth_failed += 1

                    if value_row and value_row.get("data_unavailable"):
                        logger.warning(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: Value metrics unavailable: {value_row.get('reason')}"
                        )
                        symbols_failed += 1
                    else:
                        symbols_succeeded += 1

                except Exception as e:
                    import traceback

                    logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: {type(e).__name__}: {e}")
                    logger.error(f"[TRACEBACK]\n{traceback.format_exc()}")
                    symbols_failed += 1
                    quality_failed += 1
                    growth_failed += 1

            # VERIFY: Confirm all 3 tables actually have TODAY's data before claiming success (FAIL-FAST)
            # SESSION 118 FIX: Use UTC date, not ET date - loader inserts use DB timestamps (UTC),
            # but date.today() was ET-based, causing verification to fail even when data was written.
            # Confirmed live: loader inserted 4922 rows with updated_at='2026-08-14 00:01:51 UTC' but
            # verification checked for updated_at::date='2026-08-13' (ET), found 0 rows, falsely
            # reported "Data was NOT persisted". Now queries UTC date to match the inserted data.
            utc_today = datetime.now(timezone.utc).date().isoformat()
            with DatabaseContext("read") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    safe_table = assert_safe_table(table)
                    cur.execute(f"SELECT COUNT(*) FROM {safe_table} WHERE updated_at::date = %s", (utc_today,))
                    result = cur.fetchone()
                    today_count = result[0] if result else 0
                    if today_count == 0:
                        raise RuntimeError(
                            f"[VALUE_QUALITY_GROWTH VERIFICATION FAILED] {table}: "
                            f"0 rows with today's date ({utc_today} UTC) found after load. "
                            f"Data was NOT persisted. This is a CRITICAL DATA INTEGRITY issue."
                        )
                    logger.info(f"[VALUE_QUALITY_GROWTH VERIFIED] {table}: {today_count} rows with today's date (UTC)")

            # Mark all 3 tables as ok via LoaderStatusManager (uses advisory locks)
            # BUG FOUND 2026-08-10: actual_latest_date used to be computed here but never
            # passed to mark_completed() below - data_loader_status.latest_date silently
            # never refreshed for any of these 3 tables. Also, since it was a bare loop
            # variable (not captured per-table), even wiring it up naively would have used
            # whichever table's date was queried LAST for all 3 mark_completed() calls.
            # Captured into a per-table dict instead, same pattern as per_table_counts below.
            latest_dates: dict[str, Any] = {}
            with DatabaseContext("write") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    # Query the actual MAX(date) from each table
                    safe_table = assert_safe_table(table)
                    cur.execute(f"SELECT MAX(updated_at)::date FROM {safe_table}")
                    result = cur.fetchone()
                    latest_dates[table] = result[0] if result and result[0] else None

            execution_duration = time.time() - start_time
            # FIXED 2026-08-10: this used to unconditionally write symbols_loaded=len(symbols)/
            # completion_pct=100.0 to data_loader_status for all 3 tables, completely discarding
            # the symbols_succeeded/symbols_failed counters this same run just computed above -
            # every run of this loader claimed perfect 100% completion regardless of real outcome,
            # whether that was a full-universe run with a genuine 15% SEC-data failure rate or a
            # tiny scoped --symbols diagnostic run that failed every symbol it touched. Since
            # mark_completed() re-reads exactly these two columns to decide COMPLETED vs FAILED,
            # this made that safety check a no-op for value_metrics/quality_metrics/growth_metrics
            # specifically - no run of this loader could ever be caught by it. Also meant any
            # consumer reading data_loader_status.completion_pct for these 3 tables (dashboards,
            # freshness checks) saw "100% complete" even when large-scale extraction failures were
            # actually happening upstream. Now reports the real success ratio, and passes this
            # loader's own already-declared max_fail_rate tolerance (20%) as the mark_completed()
            # threshold instead of falling back to its generic 98% default - that default doesn't
            # apply here per runner.py's own comment: "value/growth/quality metrics may have higher
            # expected failure rates for symbols without financial data" (foreign filers, ADRs,
            # non-SEC-reporting issuers, etc. are legitimately unavailable, not a loader failure).
            # Per-table counters (not one shared count) - see the quality_succeeded/growth_succeeded
            # comment near their declaration above for why value/quality/growth can't share one
            # completion figure: they come from independent source queries and fail independently.
            per_table_counts = {
                "value_metrics": (symbols_succeeded, symbols_failed),
                "quality_metrics": (quality_succeeded, quality_failed),
                "growth_metrics": (growth_succeeded, growth_failed),
            }
            min_completion_pct = max(0.0, 100.0 - self.max_fail_rate)
            for table, (table_succeeded, table_failed) in per_table_counts.items():
                table_completion_pct = (table_succeeded / len(symbols) * 100.0) if symbols else 100.0
                manager = managers.get(table) or LoaderStatusManager(table)
                manager.update_progress(
                    symbols_loaded=table_succeeded,
                    symbol_count=len(symbols),
                    completion_pct=table_completion_pct,
                )
                manager.mark_completed(
                    execution_duration_sec=execution_duration,
                    symbols_failed=table_failed,
                    min_completion_pct=min_completion_pct,
                    latest_date=latest_dates.get(table),
                )

            logger.info(
                f"[VALUE_QUALITY_GROWTH] Consolidated load complete: "
                f"{value_inserts} value, {quality_inserts} quality, {growth_inserts} growth"
            )

            # Update watermarks for all processed symbols (Session 337 fix)
            # CRITICAL: This loader overrides run() completely, so watermark updates don't happen
            # automatically via OptimalLoader base class. Must call explicitly here.
            # Update watermarks in bulk to mark successful run for ALL symbols.
            try:
                if symbols:
                    # Build bulk updates: symbol -> (today, count)
                    updates = {sym: (date.today(), 1) for sym in symbols}
                    self._watermark.advance_watermarks_bulk(updates)
                    logger.info(
                        f"[VALUE_QUALITY_GROWTH] Watermarks updated for {len(symbols)} symbols to {date.today()}"
                    )
                else:
                    logger.warning("[VALUE_QUALITY_GROWTH] No symbols processed - watermark update skipped")
            except Exception as e:
                logger.error(f"[VALUE_QUALITY_GROWTH] Failed to update watermarks: {e}")
                # Don't fail the entire loader if watermark update fails - data was written successfully

            _log_sla_status()
            return {
                "symbols_succeeded": symbols_succeeded,
                "symbols_loaded": symbols_succeeded,  # runner.py's completion log/mark_failed() read this key, not symbols_succeeded
                "symbols_failed": symbols_failed,
                "quality_symbols_succeeded": quality_succeeded,
                "quality_symbols_failed": quality_failed,
                "growth_symbols_succeeded": growth_succeeded,
                "growth_symbols_failed": growth_failed,
                "value_metrics": value_inserts,
                "quality_metrics": quality_inserts,
                "growth_metrics": growth_inserts,
                # FIXED 2026-08-25 (goal session, root-causing
                # sla_sweep_technical_data_daily_fixed_value_metrics_null_duration_open_20260825):
                # runner.py ALWAYS re-marks the loader's primary table (self.table_name =
                # "value_metrics" - see the class docstring) via its own generic
                # LoaderStatusManager(loader.table_name).mark_completed(execution_duration_sec=...)
                # call after run() returns (loaders/runner.py ~line 449-454), reading the duration
                # from stats.get("duration_sec"). This loader's return dict never had that key, so
                # runner.py's execution_duration resolved to None and clobbered the CORRECT,
                # real execution_duration this run() already wrote for value_metrics moments
                # earlier via mark_completed() in the per-table loop above - explaining exactly
                # the observed symptom: value_metrics NULL while quality_metrics/growth_metrics
                # (declared secondary via NOT setting output_tables - see this class's own
                # docstring above - so runner.py never re-marks them) stayed correct. Quality/
                # growth are unaffected by this fix (runner.py's secondary-table re-mark block
                # only fires when output_tables is set, which this loader deliberately never
                # sets - see comment above table_name).
                "duration_sec": execution_duration,
            }

        except Exception as e:
            logger.error(f"[VALUE_QUALITY_GROWTH FATAL] {type(e).__name__}: {e}", exc_info=True)
            error_msg = str(e)[:500]
            for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                manager = managers.get(table) or LoaderStatusManager(table)
                manager.mark_failed(error_msg)
            _log_sla_status()
            raise

    def fetch_incremental(
        self, symbol: str, since: date | None
    ) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
        """Fetch all metrics from SEC financial statements + sec_valuations for one symbol.

        Returns: List with single tuple of (value_dict, quality_dict, growth_dict)
        """
        try:
            with DatabaseContext("read") as cur:
                # Get value metrics from sec_valuations (primary source) - as tuple for backward compatibility
                cur.execute(
                    "SELECT * FROM sec_valuations WHERE symbol = %s",
                    (symbol,),
                )
                sec_val_row = cur.fetchone()

                # Also fetch EV metrics by column name to avoid index confusion
                # FIXED 2026-09-02 (goal: "no SEC data" audit continuation, same mislabeled-
                # genuine-gap class as debt_to_equity/roe/roa above): `reason` added as a 4th
                # column so total_cash/cash_per_share's own reason block (below) can reuse the
                # specific cause load_sec_valuations.py already computed for this exact row
                # (e.g. "income_statement_revenue_and_eps_null", "no_income_statement") instead
                # of a generic "missing_sec_data" - same propagation _compute_value_metrics_
                # from_sec already does for value_metrics, just never extended here. Appended
                # last so the existing positional ev_metrics[0..2] reads stay unchanged.
                if sec_val_row:
                    cur.execute(
                        "SELECT total_debt, total_cash, ebitda, reason FROM sec_valuations WHERE symbol = %s",
                        (symbol,),
                    )
                    ev_metrics = cur.fetchone()
                else:
                    ev_metrics = None

                # Get quality from SEC financials (annual balance sheet + income statement latest year)
                # Also fetch prior year EPS/revenue for YoY growth calculation
                # shares_outstanding is in sec_valuations, not annual_balance_sheet
                # CRITICAL: Must get latest sec_valuations row to avoid duplicate joins
                # FIXED 2026-08-05: Prioritize years with actual FCF data (many recent years have NULL FCF
                # because they're estimates, while prior years have audited FCF). Get most recent year with
                # either free_cash_flow OR operating_cash_flow populated (not latest fiscal_year blindly).
                # BOUNDED 2026-08-03: that FCF preference had no recency limit, so for filers whose
                # free_cash_flow is NULL across their entire modern filing history (live-confirmed: APD/
                # Air Products has NULL FCF for every year 2012-2026, but a real value from FY2011), it
                # reached back over a decade into history to satisfy "has FCF" - discarding a perfectly
                # fresh, complete balance sheet (real FY2026 stockholders_equity/total_assets) in favor of
                # a stale one, then falsely tripping the stale_fiscal_data gate below. Confirmed 53 real
                # symbols universe-wide hit this. Bounding the FCF preference to MAX_FISCAL_YEAR_AGE_YEARS
                # keeps the original intent (prefer audited-FCF years among the recent ones) without ever
                # trading a fresh balance sheet for an ancient FCF value.
                # FIXED 2026-08-10: the FCF-recency CASE was the ONLY tiebreaker, so absent that,
                # the query fell straight to bare `abs.fiscal_year DESC` - picking whichever
                # fiscal year has the newest BALANCE SHEET row, with zero regard for whether that
                # same year's income statement is actually usable. Live-confirmed on BFS: FY2026's
                # annual_balance_sheet row is real (data_unavailable=FALSE) but FY2026's
                # annual_income_statement row is data_unavailable=TRUE ('incomplete_sec_filing_income'),
                # so the LEFT JOIN's `ais.data_unavailable = FALSE` ON-condition silently nulled out
                # net_income/operating_income/revenue for the picked row - even though FY2023-FY2025
                # all have complete, real income statements sitting right there. roe/roa/
                # operating_margin/net_margin/revenue_growth_yoy/earnings_growth_yoy all came back
                # "missing_sec_data" as a result, despite the data existing. Universe-wide query
                # confirmed 347 symbols hit this exact pattern (latest balance-sheet fiscal year has
                # no matching usable income statement, but an earlier year does). Fixed by adding a
                # higher-priority CASE that prefers fiscal years where the ais join actually matched
                # (ais.symbol IS NOT NULL) before falling back to the FCF/recency tiebreaker - this
                # also keeps balance-sheet and income-statement fields from the SAME fiscal year
                # (picking an older year for both is strictly better than pairing a fresh balance
                # sheet with a stale/absent income statement).
                # FIXED 2026-08-17 (goal: "no SEC data"/loader audit): the ais.symbol IS NOT
                # NULL tier above only checks that a joined row exists, not that it's usable -
                # live-confirmed AMZN's FY2026 annual_income_statement row has data_unavailable
                # =FALSE and a real net_income ($135.281B) but NULL revenue/operating_income/
                # cost_of_revenue/gross_profit (a partial/interim fact set, likely a duration-
                # matched NetIncomeLoss with no matching Revenues concept for the same period -
                # passes load_financial_statements.py's transform() because its required-metrics
                # check only demands ONE of {revenue, net_income}, not both). This row still
                # ranked ahead of the complete FY2025 row (real revenue/operating_income/
                # net_income) under the old 2-tier CASE, so operating_margin/net_margin computed
                # off it: operating_margin failed outright (no revenue), net_margin silently fell
                # into the bank/no-revenue fallback (net_income / total_assets) and returned a
                # real-looking but WRONG 12.35% instead of the correct revenue-based ~9.85% -
                # worse than "missing_sec_data", a plausible wrong number with no unavailable_
                # reason to flag it. gross_margin was accidentally spared by its own separate
                # prior-year-fallback query (see gross_profit_used below), but nothing else was.
                # A DB-wide audit found 288 symbols whose most recent usable income-statement
                # fiscal year has NULL revenue while an earlier year has real revenue - all
                # candidates for this same silent-wrong-value trap. New top CASE tier prefers a
                # fiscal year with real revenue over a merely-joined one, same "prefer usable
                # data over merely-present data" principle as the ais.symbol IS NOT NULL tier.
                cur.execute(
                    """
                    SELECT abs.stockholders_equity, abs.total_liabilities, abs.total_assets,
                           ais.net_income, ais.revenue, ais.operating_income,
                           abs.current_assets, abs.current_liabilities, abs.fiscal_year,
                           abs.inventory, ais.interest_expense, sv.shares_outstanding,
                           ais.cost_of_revenue, acf.operating_cash_flow, acf.free_cash_flow,
                           acf.dividends_paid, ais.earnings_per_share,
                           (SELECT earnings_per_share FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_eps,
                           (SELECT revenue FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_revenue,
                           ais.gross_profit, abs.long_term_debt, abs.cash_and_equivalents,
                           ais.income_tax_expense, ais.pretax_income,
                           (SELECT net_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_net_income,
                           (SELECT operating_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_operating_income,
                           (SELECT operating_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_operating_cash_flow,
                           (SELECT free_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_free_cash_flow,
                           (SELECT cost_of_revenue FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_cost_of_revenue,
                           (SELECT total_assets FROM annual_balance_sheet
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_total_assets,
                           (SELECT stockholders_equity FROM annual_balance_sheet
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_stockholders_equity,
                           (SELECT pretax_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_pretax_income,
                           (SELECT interest_expense FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_interest_expense,
                           (SELECT gross_profit FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_gross_profit,
                           (SELECT dividends_paid FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_dividends_paid
                    FROM annual_balance_sheet abs
                    LEFT JOIN annual_income_statement ais ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year AND ais.data_unavailable = FALSE
                    LEFT JOIN annual_cash_flow acf ON abs.symbol = acf.symbol AND abs.fiscal_year = acf.fiscal_year AND acf.data_unavailable = FALSE
                    LEFT JOIN (
                        SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                        FROM sec_valuations
                        ORDER BY symbol, updated_at DESC
                    ) sv ON abs.symbol = sv.symbol
                    WHERE abs.symbol = %s AND abs.data_unavailable = FALSE
                    -- FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): the
                    -- revenue/matched-income tiers below were UNBOUNDED by recency, exactly the
                    -- same bug class as the FCF tier had before its own 2026-08-03 bounding fix
                    -- (see that fix's comment above) - just never applied here too. Live-confirmed
                    -- against the real DB: 98 of 100 symbols hitting quality_metrics'
                    -- stale_fiscal_data gate actually HAVE a real, complete balance sheet within
                    -- MAX_FISCAL_YEAR_AGE_YEARS (e.g. ACHV has real FY2026 stockholders_equity/
                    -- total_assets), but the anchor query picked a much older year instead purely
                    -- because that old year's income statement had a non-NULL revenue value (often
                    -- literally $0 for a pre-revenue clinical-stage biotech, or a real but ancient
                    -- figure) - "has revenue" outranked "is recent" with no floor, so a technically-
                    -- non-null revenue from 7 years ago could beat a fresh, complete balance sheet.
                    -- Now freshness (within the same staleness window the gate below checks) is
                    -- the PRIMARY sort key, with the old revenue/matched-income preference applied
                    -- only as a tiebreak WITHIN the fresh tier and, separately, WITHIN the stale
                    -- tier (preserved unchanged for genuinely-stale filers with no fresh balance
                    -- sheet at all - picking their best available old year, preferring one with
                    -- revenue, is still the right fallback for those).
                    ORDER BY (CASE
                                   WHEN abs.fiscal_year > EXTRACT(YEAR FROM CURRENT_DATE)::int - %s
                                        AND ais.revenue IS NOT NULL THEN 0
                                   WHEN abs.fiscal_year > EXTRACT(YEAR FROM CURRENT_DATE)::int - %s
                                        AND ais.symbol IS NOT NULL THEN 1
                                   WHEN abs.fiscal_year > EXTRACT(YEAR FROM CURRENT_DATE)::int - %s THEN 2
                                   WHEN ais.revenue IS NOT NULL THEN 3
                                   WHEN ais.symbol IS NOT NULL THEN 4
                                   ELSE 5 END),
                             (CASE WHEN acf.free_cash_flow IS NOT NULL
                                    AND abs.fiscal_year > EXTRACT(YEAR FROM CURRENT_DATE)::int - %s
                                    THEN 0 ELSE 1 END), abs.fiscal_year DESC
                    LIMIT 1
                    """,
                    (
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        symbol,
                        MAX_FISCAL_YEAR_AGE_YEARS,
                        MAX_FISCAL_YEAR_AGE_YEARS,
                        MAX_FISCAL_YEAR_AGE_YEARS,
                        MAX_FISCAL_YEAR_AGE_YEARS,
                    ),
                )
                quality_row_db = cur.fetchone()

                # Get annual income statement history for growth computation (not from growth_metrics table)
                # NOTE: Removed revenue IS NOT NULL filter - banks often have NULL revenue but valid net_income
                # Individual growth metrics will only be calculated if their specific inputs are available
                # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): LIMIT 10 assumed
                # a company's most recent 10 fiscal-year rows always contain enough usable data
                # points for a 5y CAGR (needs 6: revenue_growth_5y/eps_growth_5y use offset=5 into
                # `revenues`/`eps_values`, which only keep years with real positive revenue / nonzero
                # EPS - see _compute_growth_metrics below). That's false for any filer with gap years
                # mixed into its recent history (a NULL-revenue restatement gap, or - common for
                # early-stage biotechs - real $0 revenue years). Live-confirmed: OGEN has 8 real
                # positive-revenue fiscal years across 2010-2023, but 5 of its most recent 10 raw rows
                # (2025/2024 NULL, 2020/2019/2018 NULL, 2017/2016/2015 = $0) are unusable, leaving only
                # 3 usable points in the LIMIT-10 window - real revenue data from 2010-2014 exists but
                # was never even fetched. A DB-wide check found 2,942 symbols (over half the universe)
                # have MORE than 10 total annual_income_statement rows, and 28 of the 2,001 symbols
                # flagged revenue_growth_5y "insufficient_history" already have >=6 real positive-
                # revenue years on record - this LIMIT was the only thing hiding them. Raised to 30:
                # the real DB-wide max is 26 rows for any single symbol, so 30 covers every filer with
                # margin while staying a small, cheap per-symbol fetch.
                # 8th column (stockholders_equity) ADDED 2026-08-27 (goal: recover
                # book_value_growth - see _compute_book_value_growth's docstring for why this
                # candidate was wrongly rejected, then confirmed real+robust on isolated
                # re-test, t=-5.82/-2.05/-5.93 univariate, still -5.90/-2.04/-6.15 controlling
                # for asset_growth_yoy). LEFT JOIN so a fiscal year with income-statement data
                # but no matching balance-sheet row still contributes to every OTHER growth
                # calc (revenue/EPS growth don't need stockholders_equity) - book_value_growth
                # alone goes unavailable for that specific year via the NULL, same as any other
                # per-field gap. Appended as the LAST column so every existing positional index
                # read elsewhere (income_rows[i][0..6] in _compute_growth_metrics/
                # _compute_margin_volatility) stays unchanged.
                cur.execute(
                    """
                    SELECT ais.fiscal_year, ais.revenue, ais.operating_income, ais.net_income,
                           ais.earnings_per_share, ais.shares_outstanding_diluted,
                           ais.shares_outstanding_basic, abs.stockholders_equity
                    FROM annual_income_statement ais
                    LEFT JOIN annual_balance_sheet abs
                        ON ais.symbol = abs.symbol AND ais.fiscal_year = abs.fiscal_year
                        AND abs.data_unavailable = FALSE
                    WHERE ais.symbol = %s AND ais.data_unavailable = FALSE
                    ORDER BY ais.fiscal_year DESC
                    LIMIT 30
                    """,
                    (symbol,),
                )
                income_rows = cur.fetchall()
                if not income_rows:
                    logger.warning(
                        f"[VALUE_QUALITY_GROWTH] {symbol}: No income statement rows with revenue found - growth metrics will be unavailable"
                    )

            # Construct value metrics from sec_valuations only (Session 271 - yfinance-free)
            value_dict = self._build_value_metrics(symbol, sec_val_row)
            # ADDED 2026-08-26 (Quality literature audit, QMJ Safety-leg proxy): trailing-3yr
            # stdev of net_margin. Computed here (not inside _compute_quality_metrics) because
            # it needs the multi-year income_rows history already fetched above for growth
            # metrics - _compute_quality_metrics only ever sees a single fiscal year's row.
            margin_volatility, margin_volatility_unavailable_reason = self._compute_margin_volatility(income_rows)
            quality_dict = self._compute_quality_metrics(symbol, quality_row_db, ev_metrics, margin_volatility)
            if margin_volatility is None and isinstance(quality_dict, dict):
                quality_dict["margin_volatility_unavailable_reason"] = margin_volatility_unavailable_reason
            # Compute growth metrics from annual income statement history (not read from DB)
            growth_dict = self._compute_growth_metrics(symbol, income_rows)
            # ADDED 2026-08-28 (goal: Growth-pillar-audit session, migration 1245/1246) - forward
            # EPS/revenue growth estimates + estimate-revision trend, joined from
            # analyst_earnings_estimates (same source/pattern as value_metrics.forward_pe).
            # Merged unconditionally (even when growth_dict is a data_unavailable marker) since
            # this is an independent data source from the SEC-filing-driven fields above - a
            # thin-SEC-history symbol (e.g. a recent IPO) can still have real analyst coverage.
            if isinstance(growth_dict, dict):
                growth_dict.update(self._get_analyst_forward_growth_estimates(symbol))

            # GOVERNANCE: quality and growth are each derived from a DIFFERENT fiscal-year
            # source - quality_row_db's fiscal_year is driven by annual_balance_sheet (the
            # table the quality query is joined FROM), while growth uses the standalone
            # annual_income_statement history. These can diverge significantly (verified
            # live: LPL/SID have a balance sheet frozen at fiscal_year 2009 while their
            # income statement history runs through 2024) - checking a blended/max value
            # would let a fresh income statement mask a 17-year-stale balance sheet that
            # quality_metrics (ROE, debt ratios, current ratio) actually depends on. Each
            # metric family is gated on its own actual source fiscal year.
            quality_fiscal_year = quality_row_db[8] if quality_row_db else None
            growth_fiscal_year = income_rows[0][0] if income_rows else None
            current_year = date.today().year

            if quality_fiscal_year is not None and not quality_dict.get("data_unavailable"):
                quality_age = current_year - int(quality_fiscal_year)
                if quality_age > MAX_FISCAL_YEAR_AGE_YEARS:
                    stale_reason = (
                        f"stale_fiscal_data: latest balance-sheet fiscal_year={int(quality_fiscal_year)} "
                        f"is {quality_age} years old (max allowed {MAX_FISCAL_YEAR_AGE_YEARS})"
                    )
                    logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: {stale_reason}")
                    quality_dict = self._stale_quality_marker(symbol, quality_dict, stale_reason)

            if growth_fiscal_year is not None and not growth_dict.get("data_unavailable"):
                growth_age = current_year - int(growth_fiscal_year)
                if growth_age > MAX_FISCAL_YEAR_AGE_YEARS:
                    stale_reason = (
                        f"stale_fiscal_data: latest income-statement fiscal_year={int(growth_fiscal_year)} "
                        f"is {growth_age} years old (max allowed {MAX_FISCAL_YEAR_AGE_YEARS})"
                    )
                    logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: {stale_reason}")
                    growth_dict = self._unavailable_marker("growth_metrics", symbol)
                    growth_dict["reason"] = stale_reason
                    # FIXED 2026-08-21 (goal session, same bug shape as the len==6 shortcut
                    # fix in _compute_growth_metrics): _unavailable_marker() hardcodes every
                    # per-field *_unavailable_reason to the generic "insufficient_history",
                    # and only the top-level `reason` above got the real, specific
                    # stale_fiscal_data explanation - live-confirmed BCH: reason correctly
                    # said "stale_fiscal_data: ..." but revenue_growth_1y_unavailable_reason
                    # (and every other per-field column, which is what downstream consumers
                    # like the Scores Data Coverage tab actually read) still said
                    # "insufficient_history", the same misleading "our loader is broken"
                    # signal this whole reason-code system exists to eliminate. Propagate the
                    # real cause to every per-field reason column too, not just the summary.
                    for key in growth_dict:
                        if key.endswith("_unavailable_reason") and growth_dict[key] is not None:
                            growth_dict[key] = "stale_fiscal_data"

            # These 11 trend fields are computed once, in _compute_quality_metrics (it has
            # the balance-sheet data the calculations need), but are consumed by BOTH
            # quality_metrics and growth_metrics (migration 1185: "two real consumers of the
            # same computed values, not a duplicate table"). _compute_growth_metrics has no
            # access to that computation and always defaulted its own copy to None - growth_
            # metrics's half of every one of these columns was silently dead on arrival.
            #
            # FIXED 2026-08-10: previously also required quality_dict itself to not be
            # data_unavailable, so a symbol whose quality side failed entirely (e.g.
            # stale_fiscal_data) but whose growth side partially succeeded got NULL value
            # AND NULL reason for every shared field - indistinguishable from a bug on the
            # scores page ("No data" instead of "SEC data not available"). _unavailable_marker
            # always populates a real reason code (e.g. "missing_sec_data") for every shared
            # field even when quality_dict.data_unavailable is True, so it's always safe to
            # copy from it; growth_dict's own data_unavailable still gates the write target
            # (a fully-blanked growth row shouldn't be selectively patched). Live-confirmed on
            # DMRC/CNK (quality data_unavailable=True, growth data_unavailable=False): both had
            # sustainable_growth_rate=NULL with no reason before this fix.
            if not growth_dict.get("data_unavailable"):
                for field in _SHARED_TREND_FIELDS:
                    if quality_dict.get(field) is not None:
                        growth_dict[field] = quality_dict[field]
                    reason_field = f"{field}_unavailable_reason"
                    if quality_dict.get(reason_field) is not None:
                        growth_dict[reason_field] = quality_dict[reason_field]

            # Forward growth/estimate-revision fields (informational only, do not feed
            # growth_score - see _get_analyst_forward_growth_estimates's docstring). FIXED
            # 2026-08-29 (goal session, "full data" audit): previously gated inside the same
            # "not data_unavailable" block as the _SHARED_TREND_FIELDS mirror above, on the
            # assumption a fully-blanked growth row shouldn't be selectively patched - but
            # unlike _SHARED_TREND_FIELDS (mirrored from quality_metrics, a SIBLING
            # SEC-derived computation, where that assumption holds), these 4 fields come from
            # analyst_earnings_estimates, a completely independent yfinance-based source with
            # no dependency on SEC financial history. Live-confirmed 208/209 universe symbols
            # with these fields NULL-and-unexplained had growth_dict.data_unavailable=True for
            # an unrelated SEC-data reason (e.g. AADX: "insufficient_history") while genuinely
            # having real analyst forward-growth data on record (AADX's own real
            # forward_eps_growth_next_fy=1.3922 sat unused because this whole call was
            # skipped). _get_analyst_forward_growth_estimates() always returns a fully-
            # populated dict (real value or explicit "no_analyst_estimates" reason per field,
            # never a bare key omission), so it's safe to run unconditionally - it can only
            # add information, never leave a previously-explained field unexplained.
            growth_dict.update(self._get_analyst_forward_growth_estimates(symbol))

            return [(value_dict, quality_dict, growth_dict)]

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Fetch failed: {e}")
            # FIXED 2026-08-23 (goal session: loader-quality sweep): this catch-all used to
            # call _unavailable_marker() with no `reason`, so a real exception here (a bug in
            # this loader, a malformed SEC response, anything unexpected - as opposed to a
            # symbol that genuinely lacks the data) got the same generic
            # "missing_sec_data"/"insufficient_history" every legitimate gap gets. Passing the
            # actual exception through routes it to "Other (errors / excluded)" in the Scores
            # Data Coverage categorization (lambda/api/routes/scores.py::_categorize_reason
            # splits on ":", so "fetch_exception" as a base never matches a legitimate-gap
            # reason set) instead of silently inflating the legitimate-gap buckets.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return [
                (
                    self._unavailable_marker("value_metrics", symbol, reason=exc_reason),
                    self._unavailable_marker("quality_metrics", symbol, reason=exc_reason),
                    self._unavailable_marker("growth_metrics", symbol, reason=exc_reason),
                )
            ]

    def _build_value_metrics(  # noqa: C901 -- net_payout_yield's TIER 2 fallback (2026-08-26,
        # full Value pillar re-audit) pushed this pre-existing, already-organic multi-tier
        # function over the complexity threshold; a self-contained new fallback block, not
        # entangled with the existing tiers, so left in place rather than force-extracted.
        self,
        symbol: str,
        sec_val_row: Any,
    ) -> dict[str, Any]:
        """Build value_metrics from SEC valuations (yfinance-free, Session 271).

        All metrics from SEC-audited data. Dividend yield added 2026-07-20 (migration
        1144): load_sec_valuations.py now computes it from the SEC "PaymentsOfDividends"
        cash-flow concept / market_cap - was previously hardcoded None here because SEC
        had no dividend source wired up at all (dead 8%-weight bucket in value_score).

        Session 385: Added enterprise value and EV ratio metrics from sec_valuations.
        """
        # Extract SEC-derived valuations (all from sec_valuations table)
        # Using dict access - tuple fallback violates fail-fast governance
        row_dict = dict(sec_val_row) if sec_val_row and hasattr(sec_val_row, "__getitem__") else {}
        if not row_dict or row_dict.get("data_unavailable"):  # data_unavailable flag (was index 2)
            # FIXED 2026-08-19 (goal: "no SEC data" audit): every value_metrics field used to
            # get the same hardcoded generic "missing_sec_data" here whenever sec_valuations
            # itself had no usable row, discarding the real, specific reason
            # load_sec_valuations.py already computed and stored in its own `reason` column
            # (e.g. "shares_outstanding_unavailable", "income_statement_revenue_and_eps_null").
            # Live-confirmed 771 of 817 universe "missing_sec_data" market_cap rows are
            # actually shares_outstanding_unavailable - a specific, more actionable label that
            # was being thrown away one join away from where it was already sitting. Falls back
            # to the generic reason only when sec_valuations has no row for this symbol at all.
            return self._unavailable_marker("value_metrics", symbol, reason=row_dict.get("reason"))

        pe = row_dict.get("pe_ratio")
        pb = row_dict.get("pb_ratio")
        ps = row_dict.get("ps_ratio")
        peg = row_dict.get("peg_ratio")
        fcf_yield = row_dict.get("fcf_yield")
        dividend_yield = row_dict.get("dividend_yield")
        net_payout_yield = row_dict.get("net_payout_yield")
        enterprise_value = row_dict.get("enterprise_value")
        ev_ebitda = row_dict.get("ev_ebitda")
        ev_revenue = row_dict.get("ev_revenue")
        market_cap = row_dict.get("market_cap")
        intrinsic_value_per_share = row_dict.get("intrinsic_value_per_share")
        margin_of_safety_pct = row_dict.get("margin_of_safety_pct")

        # yfinance_snapshot has had no live writer since Session 275 (frozen at 2026-07-16,
        # live-confirmed 2026-08-17 - MAX(fetched_at) unchanged for a month while today's date
        # is 2026-08-17). load_positioning_metrics.py already removed its own equivalent
        # yfinance_snapshot TIER 2 fallback for exactly this reason (Session 275+ comment there:
        # "yfinance_snapshot is deprecated"). This loader's own PEG/dividend fallback (added
        # Session 346, AFTER that deprecation) never got the same treatment: live-confirmed
        # 1302/5715 value_metrics rows (~22.8%) had peg_ratio silently copied verbatim from the
        # frozen table (data_source='mixed') - a PEG ratio that can never refresh, masquerading
        # as a live fallback tier. The dividend_yield TIER 3 fallback below it is comparatively
        # harmless (only 3 rows ever matched, since the 2026-08-05 SEC dividend_data tier already
        # covers almost everything) but reads the same dead table and is removed for the same
        # reason. Nothing downstream reads data_source/'mixed' (grep-confirmed) - dropping both
        # fallbacks only removes stale/frozen values, doesn't touch anything live.
        if dividend_yield is None:
            # TIER 2 FALLBACK: Try SEC dividend_data (most recent dividend)
            # FIX 2026-08-05: Use SEC dividend_data directly instead of relying only on yfinance
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividend_yield_pct FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE AND dividend_yield_pct IS NOT NULL
                        ORDER BY ex_dividend_date DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    sec_div_row = cur.fetchone()
                    if sec_div_row:
                        dividend_yield = sec_div_row[0] / 100.0  # Convert percentage to decimal
                        logger.debug(f"[VALUE_METRICS] {symbol}: Using SEC dividend_data: {dividend_yield:.2%}")
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: SEC dividend_data fallback failed: {e}")

        # TIER 3 FALLBACK 2026-08-18 (goal: "no SEC data"/loader audit): the dividend_data
        # table (per-share/ex-dividend-date XBRL concepts) and annual_cash_flow (the
        # financing-activities "dividends paid" cash-flow-statement line, sourced
        # independently by load_financial_statements.py) are two separate extractions -
        # live-confirmed 153 universe symbols (incl. HSBC, SHEL, BHP, VOD - all real,
        # well-known dividend payers) had a real, recent, positive annual_cash_flow.
        # dividends_paid figure while dividend_data had no usable row, so the reason logic
        # below fell through to "non_dividend_paying_stock" - a factually wrong
        # classification for a company that demonstrably paid a real dividend, not just a
        # missing-data label. Aggregate yield = total dividends paid / market cap is a
        # standard, real approximation (no per-share/shares-outstanding intermediate
        # needed - both cancel out), same "recover a real value instead of a misleading
        # non-payer label" precedent as the dividend_data TIER 2 fallback above.
        if dividend_yield is None and market_cap is not None and market_cap > 0:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid FROM annual_cash_flow
                        WHERE symbol = %s AND dividends_paid IS NOT NULL AND dividends_paid > 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    cf_div_row = cur.fetchone()
                    if cf_div_row:
                        # PLAUSIBILITY BOUND added 2026-08-26 (same fix as the net_payout_yield
                        # fallback just below - found while validating that new field, this
                        # older TIER 3 dividend fallback carried the identical, longer-standing
                        # gap). market_cap here can be a real but badly-scaled
                        # shares_outstanding figure sec_valuations itself already refused to
                        # compute a ratio against - live-confirmed PARA: real market cap ~$8B+,
                        # but company_info_sec.shares_outstanding (2,690,579, off by ~2-3
                        # orders of magnitude) produced a $4.65M "market cap" here, inflating
                        # this fallback's dividend_yield to 29.87%. 100% matches
                        # load_sec_valuations.py's own primary dividend_yield bound.
                        candidate = float(cf_div_row[0]) / float(market_cap)
                        if 0 < candidate <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                            dividend_yield = candidate
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using annual_cash_flow.dividends_paid "
                                f"aggregate yield: {dividend_yield:.2%}"
                            )
                        else:
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback "
                                f"yield out of bounds ({candidate:.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback failed: {e}")

        # TIER 2 FALLBACK for net_payout_yield 2026-08-26 (goal: full Value pillar re-audit) -
        # same rationale as the dividend TIER 3 fallback just above: sec_valuations.
        # net_payout_yield can be NULL for a symbol whose latest fiscal year lacks a usable
        # entity_market_cap even when a prior year's raw dividends_paid/common_stock_repurchased
        # exist in annual_cash_flow. Aggregate (dividends + buybacks) / market_cap, same
        # "no per-share intermediate needed, both cancel out" convention as the dividend
        # fallback. No curated buyback-specific table exists (unlike dividend_data for
        # dividends), so this is the only fallback tier for this field - proportionate to how
        # new/thin this input is versus dividend_yield's much more mature multi-tier handling.
        if net_payout_yield is None and market_cap is not None and market_cap > 0:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid, common_stock_repurchased FROM annual_cash_flow
                        WHERE symbol = %s
                          AND (COALESCE(dividends_paid, 0) > 0 OR COALESCE(common_stock_repurchased, 0) != 0)
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    cf_payout_row = cur.fetchone()
                    if cf_payout_row:
                        cf_div, cf_buyback = cf_payout_row
                        total_payout = (0.0 if cf_div is None else float(cf_div)) + (
                            0.0 if cf_buyback is None else abs(float(cf_buyback))
                        )
                        # PLAUSIBILITY BOUND added after live spot-checking this fallback
                        # (2026-08-26, same day, later pass): unlike sec_valuations' own fresh
                        # net_payout_yield computation (load_sec_valuations.py, gated at 150%),
                        # this fallback's market_cap comes from wherever the loader already
                        # landed - it can be a real but broken shares_outstanding figure sec_
                        # valuations itself already refused to compute a ratio against (that's
                        # WHY this fallback tier is even reached). Live-confirmed: PARA's
                        # company_info_sec.shares_outstanding (2,690,579) is off by ~2-3 orders
                        # of magnitude from its real ~656M share count, producing a $4.65M
                        # "market cap" for a real multi-billion-dollar company - dividing any
                        # real payout figure by that gives an absurd yield. This is the SAME
                        # bug class the dividend TIER 3 fallback just above already carries
                        # (dividend_yield showed the identical 29.87% for PARA before this fix)
                        # - not something net_payout_yield introduced, but not a reason to
                        # silently inherit it into a brand-new field either.
                        # TIGHTENED 150%->50% same day, later still: the 150% bound (borrowed
                        # from load_sec_valuations.py's fresh-computation path, which has real
                        # cross-checks - yfinance sanity check, shares-outstanding scale-mismatch
                        # guard - upstream of it) was too loose for THIS fallback specifically,
                        # which has none of those upstream guards. Live-confirmed after landing
                        # the 150% version: 5 symbols (MKZR, DDT, FGNX, AHT, ASBP) still showed
                        # 111-148% total payout yield - implausible for real economics (even
                        # aggressive shareholder-return companies rarely exceed 15-20%/yr) and
                        # the same broken-shares-outstanding pattern as PARA, just narrowly under
                        # the looser cap by chance. 50% is still generous versus real-world norms
                        # while catching this fallback's actual failure mode.
                        if 0 < total_payout / float(market_cap) <= 0.5:
                            net_payout_yield = total_payout / float(market_cap)
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using annual_cash_flow "
                                f"dividends+buybacks aggregate net payout yield: {net_payout_yield:.2%}"
                            )
                        elif total_payout > 0:
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: annual_cash_flow net payout yield "
                                f"out of bounds ({total_payout / float(market_cap):.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: annual_cash_flow net payout fallback failed: {e}")

        # forward_pe = current_price / consensus forward EPS (migration 1179: load_sec_valuations.py
        # itself stays SEC-only by design, so this joins analyst_earnings_estimates - the real
        # yfinance-sourced forward-EPS consensus, since SEC filings never carry forward estimates).
        # ev_ebitda reason: was hardcoded "depreciation_amortization_not_loaded" regardless of
        # actual cause. Live audit of the universe found that's wrong for the overwhelming
        # majority of the 3256 NULL cases: load_sec_valuations.py computes ebitda from
        # operating_income alone whenever D&A is missing (D&A is additive, never required), so
        # ebitda is only ever None when operating_income itself is unavailable that fiscal year
        # (1336 cases) - and of the cases where ebitda IS present, ~1900 are simply <= 0
        # (real negative/zero-EBITDA companies, for which EV/EBITDA is not a meaningful ratio,
        # same "not applicable" class as non_dividend_paying_stock) rather than any missing data.
        ebitda_raw = row_dict.get("ebitda")
        if ebitda_raw is not None and ebitda_raw <= 0:
            ev_ebitda_reason = "unprofitable_stock"
        elif ebitda_raw is None:
            ev_ebitda_reason = "ebitda_not_extracted"
        else:
            ev_ebitda_reason = "missing_sec_data"  # ebitda>0 present, enterprise_value missing or out of bounds

        # intrinsic_value_per_share reason: sec_valuations doesn't persist raw OCF/CapEx, only
        # the fcf_yield ratio derived from them - reuse it as the same "is FCF usable" signal
        # load_sec_valuations.py's DCF itself gates on, same educated-inference-from-an-
        # adjacent-field pattern as ev_ebitda_reason above. See
        # intrinsic_value_reason_from_fcf_yield() for the 2026-08-18 fix history.
        intrinsic_value_reason = (
            intrinsic_value_reason_from_fcf_yield(fcf_yield) if intrinsic_value_per_share is None else None
        )
        if margin_of_safety_pct is None:
            margin_of_safety_reason = (
                intrinsic_value_reason if intrinsic_value_per_share is None else "missing_sec_data"
            )
        else:
            margin_of_safety_reason = None

        forward_pe = None
        # FIXED 2026-08-22 (goal session: "No analyst coverage" bucket audit): a real analyst
        # forward-EPS estimate on file for a company projected to LOSE money next year (a
        # genuinely common case for biotech/EV/early-growth names - live-confirmed on
        # MRNA/RBLX/RIVN/RKLB/WBD/BNTX, all real, well-covered large-caps) correctly leaves
        # forward_pe undefined (price / negative earnings isn't a valid multiple, same as
        # pe_ratio's own "unprofitable_stock" case), but was being reported with the same
        # "no_analyst_estimates" reason as genuinely having zero analyst coverage - 848 of
        # 1,560 live "no_analyst_estimates" forward_pe rows (54%) actually had a real,
        # non-null forward_eps on file. forward_pe_reason now distinguishes the two.
        forward_pe_reason = "no_analyst_estimates"
        current_price = row_dict.get("current_price")
        if current_price is not None and current_price > 0:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT forward_eps FROM analyst_earnings_estimates
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                fe_row = cur.fetchone()
            forward_eps = fe_row[0] if fe_row else None
            if forward_eps is not None and forward_eps > 0:
                computed_forward_pe = float(current_price) / float(forward_eps)
                if computed_forward_pe >= self.MIN_PLAUSIBLE_FORWARD_PE_RATIO:
                    forward_pe = computed_forward_pe
                else:
                    logger.warning(
                        f"[VALUE_METRICS] {symbol}: forward_pe implausibly low "
                        f"({computed_forward_pe:.4f} < {self.MIN_PLAUSIBLE_FORWARD_PE_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
                    forward_pe_reason = "implausibly_low_forward_pe"
            elif forward_eps is not None:
                forward_pe_reason = "negative_forward_eps"

        # Validate: at least one core metric must be non-None
        # FIXED 2026-08-06: Include forward_pe in validation. Analyst-derived forward PE should
        # count toward "available" metric even if historical SEC PE/PB/PS/FCF is missing.
        # Without this, unprofitable companies with analyst forward EPS guidance were marked
        # "data_unavailable" despite having a usable forward valuation metric.
        core_metrics = [pe, pb, ps, fcf_yield, forward_pe]
        if all(m is None for m in core_metrics):
            return self._unavailable_marker("value_metrics", symbol)

        # TIER 4 FALLBACK for dividend_yield 2026-08-28 (goal: "get this data" - dividend yield
        # showing "SEC data not available" for confirmed real payers). Root cause: dividend_data.
        # dividend_yield_pct is 0/91569 populated universe-wide (live-confirmed) - no writer for
        # this repo has ever set it, so TIER 2 above (which filters on it being non-NULL) can
        # never match anything, for any symbol. TIER 3's annual_cash_flow.dividends_paid is also
        # unpopulated for many real payers (live-confirmed on SPG/RS/CNK, all real, well-known
        # dividend stocks with 5 straight quarters of real dividend_per_share on file and zero
        # rows written to annual_cash_flow's dividends_paid). dividend_data.dividend_per_share
        # itself IS populated (86859 rows) and unused by any fallback tier. Sum trailing ~370
        # days of per-share payments (covers a full year of quarterly cadence with slack for
        # reporting lag) and divide by current_price - the standard trailing dividend yield
        # calculation. Live-confirmed this recovers 47 of the universe's 66 remaining
        # "missing_sec_data" dividend_yield rows, incl. SPG/RS/CNK. Same 0-100% plausibility
        # bound as TIER 3 (share-count/market-cap scale errors aren't a risk here since this
        # tier never divides by market_cap, but a bad per-share figure or stock split artifact
        # could still produce nonsense).
        if dividend_yield is None and current_price is not None and current_price > 0:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT SUM(dividend_per_share) FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND dividend_per_share IS NOT NULL
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '370 days'
                        """,
                        (symbol,),
                    )
                    ttm_row = cur.fetchone()
                    ttm_dividends = ttm_row[0] if ttm_row else None
                    if ttm_dividends is not None and ttm_dividends > 0:
                        candidate = float(ttm_dividends) / float(current_price)
                        if 0 < candidate <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                            dividend_yield = candidate
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using dividend_data.dividend_per_share "
                                f"TTM/current_price yield: {dividend_yield:.2%}"
                            )
                        else:
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: dividend_per_share TTM fallback yield "
                                f"out of bounds ({candidate:.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: dividend_per_share TTM fallback failed: {e}")

        # Determine dividend yield reason: non-payer vs missing data
        # If dividend_yield is None, check if stock is a known dividend payer
        dividend_yield_reason = None
        if dividend_yield is None:
            # Check if stock has paid dividends (present in dividend_data). MUST filter
            # data_unavailable=FALSE: load_dividend_data.py writes an explicit "confirmed no
            # dividend" marker row (data_unavailable=TRUE, e.g. reason="no_dividend_xbrl_
            # concepts") for every symbol it checks, not just ones that pay. Without this
            # filter, `fetchone() is not None` matched those marker rows too, so 3586 of the
            # universe's genuine non-dividend-payers (93% of this reason's NULLs) were
            # mislabeled "missing_sec_data" instead of "non_dividend_paying_stock".
            #
            # FIXED 2026-08-18: "has ever paid, at any point in history" also wrongly caught
            # symbols that discontinued their dividend years ago - e.g. ENVA last paid in 2016
            # (10 years of real payments on file, none since) but got "missing_sec_data" because
            # `fetchone() is not None` only asked "ever", not "recently". Added a 2-year recency
            # window on ex_dividend_date so a discontinued payer reads as the same "not a data
            # gap, a stock characteristic" case as a company that never paid at all. Live-
            # confirmed 260 of 824 universe "missing_sec_data" dividend_yield rows are this case.
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT 1 FROM dividend_data
                    WHERE symbol = %s AND data_unavailable = FALSE
                      AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                    LIMIT 1
                    """,
                    (symbol,),
                )
                has_dividend_history = cur.fetchone() is not None

            # FIX 2026-08-05: Set dividend_yield = 0.0 for confirmed non-payers
            # Previously: dividend_yield stayed NULL, showing as "no data" in UI
            # Now: dividend_yield = 0.0 (semantically correct) + reason tracked for transparency
            if not has_dividend_history:
                dividend_yield = 0.0
                dividend_yield_reason = "non_dividend_paying_stock"
            else:
                dividend_yield_reason = "missing_sec_data"

        # TIER 3 FALLBACK for net_payout_yield 2026-08-27 (goal: close the "get all the data for
        # all the inputs" gap left by the 2026-08-26 Value pillar re-audit). TIER 2 above only
        # ever assigns a value when a qualifying annual_cash_flow row exists (positive dividends
        # or a nonzero buyback); a stock with NO dividend history - already confirmed just above
        # via the richer dividend_data source (dividend_yield_reason ==
        # "non_dividend_paying_stock") - and no annual_cash_flow evidence of a buyback either was
        # left permanently NULL instead of the correct 0.0, unlike dividend_yield's own
        # "confirmed non-payer" branch immediately above. Live-confirmed 2026-08-27: 1521
        # universe symbols with a confirmed non-dividend-paying dividend_yield=0.0 still carried
        # net_payout_yield=NULL, silently dropping them out of _score_value's weighted average
        # (the `is not None` gate there) instead of correctly scoring them at the low end the way
        # dividend_yield=0.0 used to. Same 2-year recency window as TIER 2's own buyback check,
        # same `!= 0` (not `> 0`) convention - the field's sign isn't guaranteed consistent.
        if net_payout_yield is None and dividend_yield_reason == "non_dividend_paying_stock":
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM annual_cash_flow
                        WHERE symbol = %s
                          AND COALESCE(common_stock_repurchased, 0) != 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_recent_buyback = cur.fetchone() is not None
                if not has_recent_buyback:
                    net_payout_yield = 0.0
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: net payout confirmed-non-payer fallback failed: {e}")

        # pe_ratio reason: was hardcoded "missing_sec_data" regardless of cause. load_sec_
        # valuations.py only computes pe_ratio when ttm_eps > 0 (a negative/zero-EPS company
        # has no meaningful P/E, same "not applicable" class as non_dividend_paying_stock).
        # Live audit: 2283 of 2519 universe pe_ratio NULLs are unprofitable companies with a
        # real, present EPS that's just <= 0 - only 126 are genuine missing-EPS gaps. peg_ratio
        # requires pe_ratio, so it inherits the same reason when pe_ratio itself is the blocker.
        #
        # FIXED 2026-09-01 (goal session: factor-score review, user directly distrusted this
        # exact classification - "you did it because you think a company with no P/E value is
        # missing the data when in reality just no earnings"). This query was missing the
        # `data_unavailable IS NOT TRUE` filter that load_sec_valuations.py's REAL anchor-row
        # selection (the query that actually determines ttm_eps, and therefore whether pe_ratio
        # itself comes back null) already uses. Live-confirmed on BMBL/WK/BAND/PSKY/AIAI/RKT
        # (216-symbol "missing_sec_data" bucket, live-scanned): each has a most-recent fiscal
        # year row flagged `data_unavailable=True, reason='incomplete_sec_filing_income'` that
        # still carries a stray non-null (often positive) earnings_per_share value - the real
        # valuation engine correctly skips that incomplete row and falls back to the PRIOR
        # fiscal year (a genuine, complete loss year, e.g. BMBL FY2025: EPS=-5.95,
        # net_income=-$693M) to compute ttm_eps, correctly landing on <=0 and nulling pe_ratio -
        # but this query, lacking the same filter, picked up the incomplete row's stray positive
        # EPS instead and concluded "not unprofitable, must be a data gap." Adding the identical
        # filter makes this query select the SAME row load_sec_valuations.py's real computation
        # used, not a different, unfiltered one.
        pe_ratio_reason = None
        if pe is None:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
                      AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                eps_row = cur.fetchone()
            latest_eps = eps_row[0] if eps_row else None
            pe_ratio_reason = "unprofitable_stock" if latest_eps is not None and latest_eps <= 0 else "missing_sec_data"

        peg_ratio_reason: str | None
        if peg is None and pe is not None:
            with DatabaseContext("read") as cur:
                # FIXED 2026-09-01 (goal session: "we had data but didn't know how to read it"
                # audit, direct follow-up to pe_ratio_unavailable_reason's identical bug - see
                # memory/value_equal_weight_and_pe_reason_bug_fixed_20260901.md). Same bug
                # class: this query independently re-derived the two most-recent EPS years
                # WITHOUT the `data_unavailable IS NOT TRUE` filter that the REAL peg_ratio
                # computation's income_rows query (load_sec_valuations.py, ~line 395) already
                # applies - so a stray non-NULL EPS on an incomplete/unfiled fiscal year could
                # get compared as if it were the real TTM or prior-year figure, producing a
                # peg_ratio_reason that disagrees with (or is unrelated to) the actual
                # filtered EPS pair load_sec_valuations.py used to decide peg_ratio itself.
                # Live-confirmed 474 symbols (incl. ACN, ABNB, AEP) where the unfiltered
                # "latest non-NULL EPS" pick differs from the filtered pick.
                cur.execute(
                    """
                    SELECT fiscal_year, earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
                      AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 2
                    """,
                    (symbol,),
                )
                eps_rows = cur.fetchall()
            peg_ratio_reason = peg_ratio_reason_from_eps_history(eps_rows)
        else:
            peg_ratio_reason = pe_ratio_reason if peg is None and pe is None else None

        # pb_ratio reason: was hardcoded "missing_sec_data" regardless of cause. load_sec_
        # valuations.py only computes pb_ratio when stockholders_equity > 0 (negative book
        # value - common for airlines/restaurant chains/early biotechs that have bought back
        # shares or run up an accumulated deficit - makes P/B not meaningful, same "not
        # applicable" class as unprofitable_stock/negative_invested_capital elsewhere in this
        # file). Live-confirmed real, non-NULL negative stockholders_equity (not a loader gap)
        # for AAL (-$4.08B FY2026), JACK (-$936M), DBX (-$2.01B), IBRX (-$1.05B), IHRT
        # (-$1.83B FY2025) - all large, liquid, well-covered symbols that would otherwise read
        # as a fundamentals-loading failure. Same "prefer a fiscal year with a real reported
        # value" CASE ordering as load_sec_valuations.py's own book_value query, so this
        # doesn't reintroduce the "latest year is empty" trap already fixed there.
        pb_ratio_reason = None
        if pb is None:
            with DatabaseContext("read") as cur:
                # FIXED 2026-09-01 (same bug class as peg_ratio_reason above and the already-
                # fixed pe_ratio_unavailable_reason - see memory/
                # value_equal_weight_and_pe_reason_bug_fixed_20260901.md): missing the
                # `data_unavailable IS NOT TRUE` filter that the REAL book_value query
                # (load_sec_valuations.py, ~line 1330) already applies, so an incomplete/
                # unfiled fiscal year's stray stockholders_equity value could drive this
                # reason to "negative_book_value" or "missing_sec_data" independent of what
                # the real pb_ratio computation actually saw.
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                equity_row = cur.fetchone()
            latest_book_value = equity_row[0] if equity_row else None
            pb_ratio_reason = (
                "negative_book_value"
                if latest_book_value is not None and latest_book_value <= 0
                else "missing_sec_data"
            )

        # Fetch held_percent fields from positioning_metrics (FIXED 2026-08-18)
        held_percent_institutions, held_percent_institutions_reason = self._fetch_positioning_metrics(symbol)

        # Track which fields are unavailable (Session 389). No yfinance fallback remains for
        # pe/pb/ps/fcf_yield/dividend/ev/market_cap/intrinsic_value (removed 2026-08-17 - see
        # comment above data_source_peg/data_source_dividend) - those are always SEC-sourced.
        # forward_pe is the one exception: it's computed from analyst_earnings_estimates
        # (real yfinance consensus data - SEC filings never carry forward estimates, see the
        # comment above the forward_pe block). FIXED 2026-08-24 (real-money-readiness goal
        # session): this was hardcoded to "sec_audited" unconditionally, silently mislabeling
        # every row with a populated forward_pe (live-confirmed 2,658 rows) as pure-SEC when
        # they actually blend in a yfinance-derived field - same "sec_audited_except_X_yfinance"
        # composite-label convention this codebase already uses for the dual-class-shares case
        # (see load_sec_valuations.py), just not applied here. Feeds directly into
        # lambda/api/routes/scores.py's data-source coverage dashboard, so the mislabel was
        # under-reporting real yfinance dependency for this table.
        overall_data_source = "sec_audited_except_forward_pe_yfinance" if forward_pe is not None else "sec_audited"

        return {
            "symbol": symbol,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "ps_ratio": ps,
            "peg_ratio": peg,
            "dividend_yield": dividend_yield,
            "net_payout_yield": net_payout_yield,
            "fcf_yield": fcf_yield,
            "forward_pe": forward_pe,
            "enterprise_value": enterprise_value,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_revenue,
            "market_cap": market_cap,
            "intrinsic_value_per_share": intrinsic_value_per_share,
            "margin_of_safety_pct": margin_of_safety_pct,
            "value_score": None,  # Computed in load_stock_scores, copied here for convenience
            "pe_ratio_unavailable_reason": pe_ratio_reason,
            "pb_ratio_unavailable_reason": pb_ratio_reason,
            "ps_ratio_unavailable_reason": (
                ("no_revenue_reported" if symbol in self._get_no_recent_revenue_symbols() else "missing_sec_data")
                if ps is None
                else None
            ),
            "peg_ratio_unavailable_reason": peg_ratio_reason,
            "dividend_yield_unavailable_reason": dividend_yield_reason,
            "fcf_yield_unavailable_reason": "missing_sec_data" if fcf_yield is None else None,
            "forward_pe_unavailable_reason": forward_pe_reason if forward_pe is None else None,
            "ev_ebitda_unavailable_reason": ev_ebitda_reason if ev_ebitda is None else None,
            "ev_revenue_unavailable_reason": (
                ("no_revenue_reported" if symbol in self._get_no_recent_revenue_symbols() else "missing_sec_data")
                if ev_revenue is None
                else None
            ),
            "market_cap_unavailable_reason": "missing_sec_data" if market_cap is None else None,
            "intrinsic_value_unavailable_reason": intrinsic_value_reason,
            "margin_of_safety_unavailable_reason": margin_of_safety_reason,
            "held_percent_institutions": held_percent_institutions,
            "held_percent_institutions_unavailable_reason": held_percent_institutions_reason
            if held_percent_institutions is None
            else None,
            "data_unavailable": False,
            "data_source": overall_data_source,
            "updated_at": get_loader_timestamp(),
        }

    @staticmethod
    def _nan_to_none(value: float | None) -> float | None:
        """Convert NaN to None for data integrity. NaN should never be stored in DB."""
        if value is not None and isinstance(value, float) and isnan(value):
            return None
        return value

    def _fetch_positioning_metrics(self, symbol: str) -> tuple[float | None, str | None]:
        """Fetch held_percent_institutions from positioning_metrics.

        Returns tuple of (held_percent_institutions, held_percent_institutions_reason)
        """
        held_percent_institutions = None
        held_percent_institutions_reason = None

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT institutional_ownership_pct, institutional_ownership_pct_unavailable_reason
                    FROM positioning_metrics
                    WHERE symbol = %s
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (symbol,),
                )
                pos_row = cur.fetchone()

            if pos_row:
                held_percent_institutions = self._nan_to_none(
                    safe_float(pos_row[0], f"{symbol}.institutional_ownership_pct", allow_none=True)
                )
                held_percent_institutions_reason = pos_row[1]
        except Exception as e:
            logger.debug(f"[VALUE_METRICS] {symbol}: Failed to fetch positioning_metrics: {e}")
            held_percent_institutions_reason = "positioning_metrics_unavailable"

        return (held_percent_institutions, held_percent_institutions_reason)

    def _get_analyst_forward_eps(self, symbol: str) -> float | None:
        """Fetch latest analyst forward EPS estimate for symbol from analyst_earnings_estimates table.

        Returns forward_eps value or None if no data available.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT forward_eps FROM analyst_earnings_estimates
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return safe_float(row[0], f"{symbol}.forward_eps", allow_none=True)
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch analyst forward EPS: {type(e).__name__}")
        return None

    def _get_analyst_forward_growth_estimates(self, symbol: str) -> dict[str, Any]:
        """Fetch forward growth/estimate-revision fields for symbol from analyst_earnings_estimates.

        Same table/join pattern as _get_analyst_forward_eps above, extended to the 3 forward-
        growth columns plus the estimate-revision field. Returns a dict with a value + reason
        key per field (never partially-set) so the caller can merge it straight into the
        growth_metrics row dict.

        forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy
        FEED growth_score as of 2026-08-31 (goal: growth-pillar industry-alignment pass - see
        GROWTH_SCORE_FIELDS in loaders/load_stock_scores.py) - forward/analyst-consensus EPS
        growth is the single most universally-cited Growth-factor descriptor across MSCI,
        Russell, and S&P's published growth methodologies, and this table now has real
        per-symbol coverage (~73-77%) even though it still lacks enough historical DEPTH
        (only 24 distinct snapshot dates as of this writing, analyst_earnings_estimates has no
        backfill capability) to backtest predictive power in this database. eps_estimate_revision_90d_pct
        stays informational only (estimate-revision momentum is a distinct factor style from a
        growth-RATE level, not shoehorned into this blend).

        Real, live implausible-value bug found and fixed 2026-08-31 while wiring this in: unlike
        every other growth field in this file (see MAX_PLAUSIBLE_GROWTH_PCT above), these 4 had
        NO plausibility bound at all - a near-zero prior-year EPS/revenue denominator produces
        mathematically enormous (but not exceptions-raising) growth rates, live-confirmed up to
        +437,145%/-34,954% (forward_eps_growth_next_fy/current_fy) and -20,357%/+4,838%
        (eps_estimate_revision_90d_pct) - 11-29 symbols per field, ~0.5% of universe. Bounded the
        same way as every other candidate here.

        SEPARATE reason-code-accuracy fix (main, FIXED 2026-08-31, merged in 2026-08-31): every
        field used to default to "no_analyst_estimates" and only clear that default when ITS OWN
        value came back non-null - so a symbol with real, current analyst coverage (a real
        `data_unavailable = FALSE` row) that simply lacked ONE of these 4 specific derived
        figures still got the "no_analyst_estimates" label on that field, indistinguishable from
        a symbol with zero coverage at all. Live-confirmed on AFRM/DB/VOD/NWG/WELL/L (all
        real, heavily-covered large/mega-caps, $22B-$1.1T market cap): each has a real, current
        `forward_eps`/`forward_eps_growth_next_fy` from `analyst_earnings_estimates`, yet
        `forward_eps_growth_current_fy_unavailable_reason` said "no_analyst_estimates" - yfinance's
        `earnings_estimate` DataFrame simply didn't have a "growth" value for the "0y" (current
        fiscal year) period specifically for these symbols, a real but distinct gap from "nobody
        covers this stock". Distinguishes 3 states now: no `data_unavailable = FALSE` row found
        at all -> still "no_analyst_estimates" (genuinely zero coverage, the common case); a row
        WAS found but this specific field came back NULL -> "analyst_coverage_incomplete_for_field"
        (real coverage exists, just not this one derived figure); a row was found AND the field
        has a value, but it's implausible -> "garbage_metric_value_implausible_ratio" (this
        branch's fix above, orthogonal to the None-vs-found distinction).
        """
        fields = (
            "forward_eps_growth_current_fy",
            "forward_eps_growth_next_fy",
            "forward_revenue_growth_next_fy",
            "eps_estimate_revision_90d_pct",
        )
        # forward_eps_growth_current_fy/next_fy/forward_revenue_growth_next_fy are stored as raw
        # FRACTIONS (0.18 = 18%, see load_stock_scores.py's _get_growth_metrics for the
        # fraction->percentage-point conversion at scoring time); eps_estimate_revision_90d_pct
        # is already percentage-point scaled. MAX_PLAUSIBLE_GROWTH_PCT is a percentage-point
        # threshold, so the fraction-scaled fields compare against it divided by 100.
        _fraction_scaled_fields = {
            "forward_eps_growth_current_fy",
            "forward_eps_growth_next_fy",
            "forward_revenue_growth_next_fy",
        }
        result: dict[str, Any] = {}
        for field in fields:
            result[field] = None
            result[f"{field}_unavailable_reason"] = "no_analyst_estimates"
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"""
                    SELECT {", ".join(fields)} FROM analyst_earnings_estimates
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
                if row:
                    for field, val in zip(fields, row, strict=True):
                        parsed = safe_float(val, f"{symbol}.{field}", allow_none=True)
                        if parsed is None:
                            # merge 2026-08-31: main's reason-code-accuracy fix (0ca6489f0) - a
                            # real data_unavailable=FALSE row was found but THIS field came back
                            # NULL, distinct from no row/no coverage at all (default above).
                            result[f"{field}_unavailable_reason"] = "analyst_coverage_incomplete_for_field"
                            continue
                        plausibility_bound = (
                            MAX_PLAUSIBLE_GROWTH_PCT / 100
                            if field in _fraction_scaled_fields
                            else MAX_PLAUSIBLE_GROWTH_PCT
                        )
                        if abs(parsed) < plausibility_bound:
                            result[field] = parsed
                            result[f"{field}_unavailable_reason"] = None
                        else:
                            result[f"{field}_unavailable_reason"] = "garbage_metric_value_implausible_ratio"
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch analyst forward growth estimates: {type(e).__name__}")
        return result

    def _compute_quarterly_metrics(self, symbol: str) -> dict[str, Any]:  # noqa: C901
        """Compute quarterly metrics: consecutive_positive_quarters, earnings_growth_4q_avg, quarterly_growth_momentum, eps_growth_stability, earnings_surprise_avg, earnings_beat_rate."""
        metrics: dict[str, Any] = {}
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_quarter, net_income, revenue, earnings_per_share
                    FROM quarterly_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC, fiscal_quarter DESC
                    LIMIT 8
                    """,
                    (symbol,),
                )
                quarters = cur.fetchall()

                if len(quarters) < 4:
                    # FIXED 2026-08-19 (goal session continuation - "which factor inputs are
                    # missing the most" audit): "insufficient_quarterly_history" implies "will
                    # accumulate more data over time," which is false for foreign private
                    # issuers (20-F/40-F filers) - they're exempt from mandatory quarterly
                    # (10-Q) SEC reporting, and their optional 6-K interim filings only
                    # sporadically carry full XBRL-tagged financial statements. Live-confirmed
                    # via CHKP (Check Point Software, NYSE-listed since 1996) and FVRR
                    # (Fiverr): both real, mature, long-listed companies whose SEC XBRL
                    # genuinely has only 2 quarterly Revenues facts ever tagged (confirmed
                    # directly against SEC's live companyfacts API, not a local extraction gap
                    # - our loader correctly captured everything SEC has). 371 of 541
                    # universe-wide "insufficient_quarterly_history" symbols (68%) are flagged
                    # foreign private issuer - same "permanent SEC exemption, not a data gap"
                    # distinction already applied to no_insider_transactions_in_lookback and
                    # no_8k_filings_in_recent_submissions elsewhere in this codebase today.
                    cur.execute(
                        "SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s",
                        (symbol,),
                    )
                    fpi_row = cur.fetchone()
                    is_fpi = bool(fpi_row[0]) if fpi_row else False
                    reason = (
                        "foreign_private_issuer_no_quarterly_filings" if is_fpi else "insufficient_quarterly_history"
                    )
                    # Not enough quarterly data - set unavailable reasons for metrics that depend on quarters
                    for field in [
                        "consecutive_positive_quarters",
                        "quarterly_growth_momentum",
                        "earnings_growth_4q_avg",
                        "eps_growth_stability",
                    ]:
                        metrics[f"{field}_unavailable_reason"] = reason
                    return metrics

            quarters.reverse()
            quarterly_data = [
                {
                    "fiscal_year": q[0],
                    "fiscal_quarter": q[1],
                    "net_income": self._nan_to_none(safe_float(q[2], f"{symbol}.q_net_income", allow_none=True)),
                    "revenue": self._nan_to_none(safe_float(q[3], f"{symbol}.q_revenue", allow_none=True)),
                    "eps": self._nan_to_none(safe_float(q[4], f"{symbol}.q_eps", allow_none=True)),
                }
                for q in quarters
            ]

            last_4q = quarterly_data[-4:]

            positive_count = 0
            consecutive_positive = 0
            for q in last_4q:
                if q["net_income"] is not None and q["net_income"] > 0:
                    positive_count += 1
                    consecutive_positive += 1
                else:
                    if consecutive_positive < positive_count:
                        positive_count = consecutive_positive
                    consecutive_positive = 0

            # 0 is a legitimate answer (no positive quarters in the trailing window), not a
            # missing value - always record it instead of leaving the field (and thus its
            # _unavailable_reason) unset, which previously made ~3,173 real stocks with a
            # net-loss quarter show as unexplained "No data" instead of "0".
            metrics["consecutive_positive_quarters"] = int(consecutive_positive)

            # FIXED 2026-08-28 (goal: growth-formula best-practices review, user-flagged):
            # both earnings_growth_4q_avg and quarterly_growth_momentum used to average
            # SEQUENTIAL quarter-over-quarter change (Q4 vs Q3, Q3 vs Q2, Q2 vs Q1) - this
            # contaminates any seasonal business (retail Q4 holiday spike, agriculture,
            # travel) with swings that have nothing to do with underlying growth. Industry
            # practice (IBD CAN SLIM's "C" current-quarterly-earnings criterion, Zacks growth
            # scoring) compares each quarter to the SAME quarter a year ago instead, which
            # captures recency the same way without the seasonal noise. Matched by
            # (fiscal_year, fiscal_quarter) rather than a fixed index offset so a gap in the
            # filing history doesn't silently misalign the comparison.
            by_period = {(q["fiscal_year"], q["fiscal_quarter"]): q for q in quarterly_data}

            eps_growth_rates = []
            revenue_yoy_growth_rates = []
            any_yoy_period_matched = False
            for q in last_4q:
                prior = by_period.get((q["fiscal_year"] - 1, q["fiscal_quarter"]))
                if prior is None:
                    continue
                any_yoy_period_matched = True
                curr_eps, prev_eps = q["eps"], prior["eps"]
                if curr_eps is not None and prev_eps is not None and prev_eps != 0:
                    eps_growth_rates.append(((curr_eps - prev_eps) / abs(prev_eps)) * 100)
                curr_rev, prev_rev = q["revenue"], prior["revenue"]
                if curr_rev is not None and prev_rev is not None and prev_rev != 0:
                    revenue_yoy_growth_rates.append(((curr_rev - prev_rev) / abs(prev_rev)) * 100)

            if eps_growth_rates:
                earnings_growth_4q_avg = sum(eps_growth_rates) / len(eps_growth_rates)
                # Bounded like every other growth-RATE field in this file (see
                # MAX_PLAUSIBLE_GROWTH_PCT above, not the looser MAX_TREND_PERCENTAGE_POINTS -
                # that stale reference is what left the "garbage_metric_value_implausible_
                # growth_rate" reason string itself mislabeled as "_abs_gt_100000" until
                # 2026-08-31) - a near-zero prior-quarter EPS makes a single quarter's growth
                # rate (and therefore this average) mathematically enormous despite being a
                # "real" computation, which would overflow this NUMERIC(10,4) column and abort
                # the entire row's write.
                if abs(earnings_growth_4q_avg) < MAX_PLAUSIBLE_GROWTH_PCT:
                    metrics["earnings_growth_4q_avg"] = float(round(earnings_growth_4q_avg, 2))
                else:
                    metrics["earnings_growth_4q_avg_unavailable_reason"] = (
                        "garbage_metric_value_implausible_growth_rate"
                    )

                if len(eps_growth_rates) >= 2:
                    mean_growth = sum(eps_growth_rates) / len(eps_growth_rates)
                    variance = sum((x - mean_growth) ** 2 for x in eps_growth_rates) / len(eps_growth_rates)
                    stability_stddev = sqrt(variance)
                    # Same overflow risk as earnings_growth_4q_avg above - stddev of a set
                    # containing one enormous near-zero-denominator growth rate is itself
                    # enormous.
                    if stability_stddev < MAX_PLAUSIBLE_GROWTH_PCT:
                        metrics["eps_growth_stability"] = float(round(stability_stddev, 2))
                    else:
                        metrics["eps_growth_stability_unavailable_reason"] = (
                            "garbage_metric_value_implausible_growth_rate"
                        )
                else:
                    # Only one quarter-over-quarter EPS comparison available - not enough to
                    # compute a variance/stddev, but this is a real, explainable gap.
                    metrics["eps_growth_stability_unavailable_reason"] = "insufficient_eps_growth_datapoints"
            elif any_yoy_period_matched:
                # A same-quarter-prior-year period was found for at least one of the last 4
                # quarters, but eps was None (or the prior value was 0) on every matched pair -
                # e.g. missing EPS in the source rows, not a history-depth gap.
                metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_eps_data"
                metrics["eps_growth_stability_unavailable_reason"] = "insufficient_eps_data"
            else:
                # >=4 quarters existed (the insufficient_quarterly_history branch above was not
                # hit) but none of the last 4 quarters had a same-quarter-prior-year match at
                # all - fewer than 8 quarters of history, or a gap in the filing history.
                metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_year_over_year_quarterly_history"
                metrics["eps_growth_stability_unavailable_reason"] = "insufficient_year_over_year_quarterly_history"

            revenue_growth_rates = revenue_yoy_growth_rates
            if revenue_growth_rates:
                quarterly_growth_momentum = sum(revenue_growth_rates) / len(revenue_growth_rates)
                # Same near-zero-prior-quarter overflow risk as earnings_growth_4q_avg above.
                if abs(quarterly_growth_momentum) < MAX_PLAUSIBLE_GROWTH_PCT:
                    metrics["quarterly_growth_momentum"] = float(round(quarterly_growth_momentum, 2))
                else:
                    metrics["quarterly_growth_momentum_unavailable_reason"] = (
                        "garbage_metric_value_implausible_growth_rate"
                    )
            elif any_yoy_period_matched:
                metrics["quarterly_growth_momentum_unavailable_reason"] = "insufficient_revenue_data"
            else:
                metrics["quarterly_growth_momentum_unavailable_reason"] = (
                    "insufficient_year_over_year_quarterly_history"
                )

            # Phase 3A: Earnings surprise and beat rate
            # Use last quarter EPS vs current analyst forward EPS as proxy for surprise
            last_eps = last_4q[-1]["eps"]
            forward_eps = self._get_analyst_forward_eps(symbol)

            if last_eps is not None and forward_eps is not None and last_eps != 0:
                # Earnings surprise: (last reported - forward estimate) / |forward estimate| * 100
                # FIXED 2026-08-30 (goal: full-data audit, live sanity-check pass): had no bound
                # at all, unlike quarterly_growth_momentum right above (same MAX_PLAUSIBLE_GROWTH_PCT
                # guard) and this same field's OTHER, independent implementation in
                # load_enhanced_quality_growth_metrics.py (guarded at MAX_TREND_PERCENTAGE_POINTS).
                # A near-zero forward_eps estimate (common for turnaround/recovery names) divides
                # this into a meaningless number - live-caught min=-433,067.03%/max=936,616.42%
                # already on file, several orders of magnitude past any real "surprise" percentage.
                if forward_eps != 0:
                    surprise = ((last_eps - forward_eps) / abs(forward_eps)) * 100
                    if abs(surprise) < MAX_PLAUSIBLE_GROWTH_PCT:
                        metrics["earnings_surprise_avg"] = float(round(surprise, 2))
                    else:
                        metrics["earnings_surprise_avg_unavailable_reason"] = (
                            "garbage_metric_value_implausible_growth_rate"
                        )

                # Earnings beat rate: % of recent quarters with positive EPS growth (proxy for beats)
                if len(eps_growth_rates) > 0:
                    beat_count = sum(1 for rate in eps_growth_rates if rate > 0)
                    beat_rate = (beat_count / len(eps_growth_rates)) * 100
                    metrics["earnings_beat_rate"] = float(round(beat_rate, 2))
            else:
                # Set unavailable reasons for earnings metrics when analyst data missing
                if forward_eps is None:
                    metrics["earnings_surprise_avg_unavailable_reason"] = "no_analyst_estimates"
                    metrics["earnings_beat_rate_unavailable_reason"] = "no_analyst_estimates"
                elif last_eps is None:
                    metrics["earnings_surprise_avg_unavailable_reason"] = "insufficient_quarterly_history"
                    metrics["earnings_beat_rate_unavailable_reason"] = "insufficient_quarterly_history"

        except Exception as e:
            logger.debug(f"[{symbol}] Failed to compute quarterly metrics: {type(e).__name__}: {e}")

        return metrics

    def _get_unclassified_balance_sheet_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported current_assets in any of their 3 most recent fiscal years.

        REITs/banks/insurers file an unclassified balance sheet (no current/non-current split)
        as a permanent accounting-model difference, not a data gap. A single fiscal year missing
        current_assets can also just be an ordinary extraction/timing gap for an otherwise normal
        filer - requiring 3 consecutive missing years is what actually distinguishes the two,
        rather than guessing from one row.

        FIXED 2026-08-18: originally required COUNT(current_assets) = 0 across EVERY fiscal year
        ever filed, not just recent ones. That misses symbols that switched accounting presentation
        partway through their filing history - e.g. ENVA reported a classified balance sheet in
        FY2013-2014 (pre spin-off from Cash America) but has filed unclassified every year since
        (FY2015-2026, 12 straight years); the old query saw the two ancient non-null years and
        fell through to the generic "missing_sec_data" label, which reads as a loader bug rather
        than the permanent accounting-model difference it actually is. Live-confirmed 49 symbols
        in this "used to report classified, now doesn't" bucket. Cached for the life of this
        loader instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_unclassified_balance_sheet_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, current_assets,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(current_assets) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._unclassified_balance_sheet_symbols_cache = result
        return result

    def _get_no_tax_concept_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported pretax_income or income_tax_expense in any of
        their 3 most recent fiscal years.

        Same "3 consecutive years missing a concept = permanent accounting-model
        difference, not a data gap" pattern as _get_unclassified_balance_sheet_symbols
        above (REIT/bank/insurer unclassified balance sheets). Here the structural
        difference is a real corporate-tax exemption: Marshall-Islands/Bermuda-
        incorporated shipping companies under IRC Section 883's tonnage-tax exemption
        (live-confirmed: GASS/ESEA/DSX and 13 more "Marine Shipping" symbols, all
        Greek-operated) and REITs under Subchapter M pass-through status never tag
        IncomeTaxExpenseBenefit/pretax-income concepts because there is no income tax
        line to report - not because the data is missing. roic_pct's effective_tax_rate
        logic (FIXED 2026-08-09 to stop assuming a synthetic 21%/25% rate) correctly
        refuses to guess a rate when tax concepts are absent, but that left these
        genuinely-zero-tax filers permanently unavailable instead of computing a real
        NOPAT = operating_income (0% effective rate) - the same "genuine business-state
        fact, not an absent SEC concept" distinction already applied to
        roic_pct_unprofitable just below. Cached for the life of this loader instance.
        """
        cached: frozenset[str] | None = getattr(self, "_no_tax_concept_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, pretax_income, income_tax_expense,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(pretax_income) = 0 AND COUNT(income_tax_expense) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_tax_concept_symbols_cache = result
        return result

    def _get_never_tagged_pretax_income_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported pretax_income in any of their 3 most recent
        fiscal years, REGARDLESS of whether they tag income_tax_expense.

        Distinct from _get_no_tax_concept_symbols() above, which requires BOTH concepts
        absent (the fully tax-exempt case: 0% rate, no approximation needed). This
        covers the class that still falls through the cracks: REITs/mortgage trusts
        (ADC, AAT, ABR live-confirmed via real annual_income_statement rows) whose
        10-Ks go straight from revenue to net income with no distinct "income before
        tax" subtotal line to tag at all (REIT pass-through income is structurally not
        the thing being taxed), but DO carry a small, real income_tax_expense most years
        (built-in-gains tax on a taxable REIT subsidiary, state tax, etc.) - live-
        confirmed 165 universe symbols fit this exact profile, 122 of them blocking
        roic_pct on "missing_sec_data". Since there's no pretax_income concept AT ALL
        to be missing, the effective_tax_rate branch below uses (net_income +
        income_tax_expense) as an approximation of the SAME fiscal year's pretax base -
        see that branch's comment for why this narrow use is safe despite the general
        net_income-derivation approach being rejected elsewhere in this file. Cached for
        the life of this loader instance.
        """
        cached: frozenset[str] | None = getattr(self, "_never_tagged_pretax_income_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, pretax_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(pretax_income) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._never_tagged_pretax_income_symbols_cache = result
        return result

    def _get_no_recent_interest_expense_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported interest_expense in any of their 3 most recent fiscal years.

        Live audit 2026-08-18 ("no SEC data" goal): 927 of 1525 universe interest_coverage
        "missing_sec_data" rows are this case - not a loader gap. Two distinct real causes land
        in the same bucket: (1) a genuinely debt-free company that never had an interest expense
        line to report, and (2) a company that stopped itemizing interest expense as its own
        line - live-confirmed on AAPL, which reported real interest_expense every year through
        FY2023 ($3.9B) but has netted it into "other income/(expense)" starting FY2024, so its 3
        most recent fiscal years (2024-2026) are structurally NULL despite being a real, large,
        indebted borrower. Same "3 most recent years, not all-time history" windowing as
        _get_unclassified_balance_sheet_symbols() above, for the same reason: a company can
        permanently change what it itemizes partway through its filing history. Cached for the
        life of this loader instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_interest_expense_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, interest_expense,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(interest_expense) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_interest_expense_symbols_cache = result
        return result

    def _get_no_recent_debt_components_symbols(self) -> frozenset[str]:
        """Symbols with NO debt component (long_term_debt, short_term_debt,
        operating_lease_liability, finance_lease_liability) reported in any of their 3 most
        recent fiscal years - i.e. sec_valuations.total_debt is structurally None for them, not
        a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): 440 of the universe's total_debt
        "missing_sec_data" rows are this case. Unlike current_ratio/quick_ratio (dominated by
        banks/REITs), this bucket is a genuine mixed bag - SPACs ("Blank Checks", 127), pre-
        revenue pharma/biotech (90), and small tech/services companies (~70) alongside a smaller
        bank/REIT contingent (~40) - most of these companies simply carry no debt at all, not a
        different accounting model for a specific entity type. Same "3 most recent years, not
        all-time history" windowing as the sibling checks above. Cached for the life of this
        loader instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_debt_components_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, long_term_debt, short_term_debt,
                           operating_lease_liability, finance_lease_liability,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(long_term_debt) = 0 AND COUNT(short_term_debt) = 0
                   AND COUNT(operating_lease_liability) = 0 AND COUNT(finance_lease_liability) = 0
                   AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_debt_components_symbols_cache = result
        return result

    def _get_no_recent_revenue_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported revenue in any of their 3 most recent fiscal years -
        i.e. structurally pre-revenue, not a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): ebitda_margin can be None even when ebitda
        itself is a real, computed value (e.g. a real negative EBITDA), because ebitda_margin =
        ebitda / revenue has no fallback denominator (unlike operating_margin, which falls back
        to total_assets) - live-confirmed 511 universe symbols with ebitda present but
        ebitda_margin "missing_sec_data"; of those, 69 have genuinely never reported revenue in
        their 3 most recent fiscal years (dominated by SPACs and pre-revenue clinical-stage
        biotech/pharma, e.g. ABVX/Abivax). The remaining ~440 have real revenue on file in a
        different fiscal year than the one quality_row's balance-sheet anchor selected (e.g.
        AFYA/AIB/AKTS) - a distinct fiscal-year-anchor-selection gap, not this "structurally no
        revenue" case, so deliberately NOT covered by this windowed check. Cached for the life
        of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-08-19 (pb_ratio negative_book_value follow-up): the HAVING clause was
        `COUNT(revenue) = 0`, which only counts NULL revenue - a company that reports a real,
        correctly-extracted $0.00 revenue for all 3 recent fiscal years (common for pre-revenue
        clinical-stage biotechs/SPACs, e.g. DFTX/DMRA/GNPX/IMVT - the SEC filing genuinely says
        "$0", not "not reported") is NOT NULL, so it silently fell through to the generic
        "missing_sec_data" for ps_ratio/ev_revenue/ebitda_margin/gross_margin alike, even though
        nothing is missing. Live-confirmed 245 universe symbols hit this exact zero-vs-null gap
        (same bug class as the total_debt/roic_pct genuine-zero fixes elsewhere in this file).
        Now treats NULL and real 0 as equivalent "no revenue" for this windowed check.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_revenue_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, revenue,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE revenue IS NOT NULL AND revenue != 0) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_revenue_symbols_cache = result
        return result

    def _get_no_recent_total_assets_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported a real (non-NULL, positive) total_assets in any of
        their 3 most recent fiscal years - i.e. asset_turnover is structurally None for them,
        not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, asset_turnover follow-up
        to the debt_to_equity/total_debt mislabeled-genuine-gap fixes): 53 of 294 universe
        asset_turnover "missing_sec_data" rows are this case. Sampled live: overwhelmingly
        foreign private issuers filing 20-F under IFRS (ABEV, AZUL, BBD/BBDO, BBAR, CCU, CIG,
        CRESY, EC, ERIC, GGB, SBS, SUZ, TIMB) - the same "SEC companyfacts convenience API
        doesn't expose this concept the way our extraction expects for non-US-GAAP filers"
        pattern already established for foreign_private_issuer_shares_unavailable/
        foreign_private_issuer_no_quarterly_filings elsewhere in this file, just never given
        its own gate for total_assets specifically. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_total_assets_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, total_assets,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE total_assets IS NOT NULL AND total_assets > 0) = 0
                   AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_total_assets_symbols_cache = result
        return result

    def _get_no_recent_net_income_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported net_income in any of their 3 most recent fiscal
        years - i.e. roe/roa are structurally None for them, not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, same fix class as
        debt_to_equity/asset_turnover/roic_pct/roce_pct above): roe/roa's compute blocks
        require BOTH net_income and their own denominator (stockholders_equity/total_assets)
        to be non-None, but their reason blocks were 100% generic "missing_sec_data" with no
        gating at all, unlike every sibling ratio. Sampled live: unlike revenue/total_assets,
        a filer missing net_income for 3 straight years is rare and usually a genuine SEC
        extraction/tagging gap rather than a structural business fact - callers should not
        assume this set is large. Same "3 most recent years, not all-time history" windowing
        as the sibling checks above. Cached for the life of this loader instance; this query
        runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_net_income_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, net_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(net_income) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_net_income_symbols_cache = result
        return result

    def _get_no_recent_total_liabilities_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported total_liabilities in any of their 3 most recent
        fiscal years - i.e. debt_to_assets is structurally None for them, not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, debt_to_assets follow-up
        to the debt_to_equity fix above): debt_to_assets = total_liabilities / total_assets,
        with no reason gating at all before this fix. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_total_liabilities_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, total_liabilities,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(total_liabilities) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_total_liabilities_symbols_cache = result
        return result

    def _get_blank_check_symbols(self) -> frozenset[str]:
        """Symbols SEC-classified as SIC 6770 "Blank Checks" - pre-merger SPAC shells.

        FIX 2026-08-19 (goal: "no SEC data" audit, roic_pct/gross_margin/ebitda_margin
        follow-up): a blank-check company has no real operating business before its
        merger (trust-account interest income only, no product/service revenue, no
        meaningful invested-capital deployment) - roic_pct/gross_margin/ebitda_margin
        being unavailable for one is a genuine structural fact, same category as
        reit_special_entity, not a loader gap. Live-confirmed: 343 universe symbols
        carry this exact SIC classification, and 326/270/314 of them respectively were
        mislabeled "missing_sec_data" for those three metrics - reading as a loader
        failure instead of the correct "this entity has no operating business yet".

        Deliberately uses company_info_sec.sic_description (SEC's own authoritative
        classification) rather than extending _get_no_recent_revenue_symbols()'s 3-
        consecutive-fiscal-year window: many SPACs are too recently IPO'd to have 3
        years of filings yet, which would exclude them from that check even though
        their SIC code alone already settles the question, filing history length
        notwithstanding. Cached for the life of this loader instance; this query runs
        once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_blank_check_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute("SELECT symbol FROM company_info_sec WHERE sic_description = 'Blank Checks'")
            result = frozenset(row[0] for row in cur.fetchall())
        self._blank_check_symbols_cache = result
        return result

    def _get_no_recent_stockholders_equity_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported stockholders_equity in any of their 3 most recent
        fiscal years - i.e. debt_to_equity is structurally None for them, not a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): 156 of 1,048 universe debt_to_equity
        "missing_sec_data" rows are this case. A genuine mixed bag (unlike current_ratio's
        bank/REIT-dominated bucket) - pharma (9), REITs (7), utilities (6), investment advice
        (6), real estate (5) - no single entity type dominates, so this gets its own reason
        string rather than reit_special_entity. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        cached: frozenset[str] | None = getattr(self, "_no_recent_stockholders_equity_symbols_cache", None)
        if cached is not None:
            return cached
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, stockholders_equity,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(stockholders_equity) = 0 AND COUNT(*) = 3
                """
            )
            result = frozenset(row[0] for row in cur.fetchall())
        self._no_recent_stockholders_equity_symbols_cache = result
        return result

    def _compute_margin_volatility(self, income_rows: list[Any]) -> tuple[float | None, str | None]:
        """Trailing-3-fiscal-year stdev (percentage points) of net_margin - QMJ (2013) Safety
        leg proxy: earnings/margin persistence, distinct from price-return volatility (which
        lives in the Risk pillar) and from the accruals ratio (composition of one year's
        earnings, not stability across years). income_rows is ordered fiscal_year DESC (see
        fetch_incremental's SELECT above) - [:3] takes the most recent 3 fiscal years.
        Requires all 3 years usable (real revenue>0); a symbol with fewer usable years returns
        None (data_unavailable for this component) rather than a volatility estimate from 1-2
        points, which would be too noisy to trust.

        Returns (value, unavailable_reason) - reason is only meaningful when value is None.

        FIXED 2026-08-26 (live-caught): unlike every sibling margin ratio in this file
        (net_margin/gross_margin/operating_margin/fcf_margin all guard |ratio|>1000, see
        test_quality_metrics_implausible_ratio_reason.py), this function computed each year's
        raw margin inline with NO implausible-value bound - a near-zero-revenue year (SEC
        tagging garbage, not a real business characteristic) produced a margin in the billions
        of percent, and squaring+sqrt-ing that in the variance calc overflowed
        quality_metrics.margin_volatility's NUMERIC(10,2) column, crashing the ENTIRE row's
        INSERT for that symbol (live-caught: TKLF, one bad fiscal year's margin blocked its
        whole quality_metrics write, not just this one field). Same >1000 bound as every
        sibling ratio, applied per-year before the variance calc so one garbage year correctly
        falls back to "insufficient usable years" (same path as a missing year) instead of
        poisoning the stdev with an astronomical outlier.
        """
        margins = []
        implausible = False
        for row in income_rows[:3]:
            revenue = safe_float(row[1], "margin_vol.revenue", allow_none=True)
            net_income = safe_float(row[3], "margin_vol.net_income", allow_none=True)
            if revenue is not None and revenue > 0 and net_income is not None:
                margin = (net_income / revenue) * 100.0
                if abs(margin) > 1000:
                    implausible = True
                    continue
                margins.append(margin)
        if len(margins) < 3:
            return None, ("implausible_ratio" if implausible else "insufficient_history")
        mean = sum(margins) / len(margins)
        variance = sum((m - mean) ** 2 for m in margins) / len(margins)
        return float(sqrt(variance)), None

    def _get_symbol_sector(self, symbol: str) -> str | None:
        """Lazily fetches and caches symbol -> company_profile.sector (GICS) once per loader
        run, reused across every _compute_quality_metrics call (no per-symbol query).

        ADDED 2026-08-28 (Quality pillar sector-conditional formula, goal session
        "figure out the industry-best right formula" - see
        algo/research/quality_industry_leader_formula_comparison_20260828.py for the full
        Fama-MacBeth evidence trail). Financial Services and Real Estate get a 7-input variant
        of quality_score (see quality_components below) that drops ONLY asset_turnover_score -
        confirmed via isolated testing (not assumed from principle) to be the single input
        responsible for those two sectors' weaker Quality signal, not roce_score as first
        suspected: Revenue/Total Assets isn't a coherent "operating efficiency" measure for a
        bank's loan book or a REIT's real estate portfolio the way it is for an operating
        company. Dropping BOTH asset_turnover AND roce (as first tried) tested no better than
        dropping asset_turnover alone, and used less of the real data available - dropping
        asset_turnover alone is the minimal change that captures the full effect (Real Estate
        Spearman IC t=0.49 -> 2.35, Financial Services t=1.73 -> 3.31, both era-robust in the
        same 2017-2026 panel). Matches standard practice (Fama-French 1992 exclude financials
        from several factor constructions; modern quant equity practice drops/de-weights
        leverage-or-efficiency ratios that don't reflect the same thing for financials/REITs
        that they do elsewhere) - this is the lightest-touch version of that: one input dropped
        for two sectors, nothing else changed, confirmed by direct testing rather than assumed.

        Returns None (falls through to the universal formula) if the sector map can't be
        fetched or the symbol isn't in company_profile - fails open to the well-tested
        universal formula rather than silently miscategorizing a symbol."""
        if not hasattr(self, "_sector_cache"):
            self._sector_cache: dict[str, str] = {}
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL")
                    self._sector_cache = dict(cur.fetchall())
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(
                    f"[QUALITY_METRICS] Failed to fetch company_profile sector map for the "
                    f"sector-conditional Quality formula - falling back to the universal "
                    f"8-input formula for every symbol this run: {e}"
                )
        return self._sector_cache.get(symbol)

    def _compute_quality_metrics(  # noqa: C901
        self,
        symbol: str,
        quality_row: Any,
        ev_metrics: Any = None,
        margin_volatility: float | None = None,
    ) -> dict[str, Any]:
        """Compute quality_metrics from SEC financials (balance sheet + income statement + cash flow + EV data).

        ev_metrics: tuple of (total_debt, total_cash, ebitda[, reason]) from sec_valuations -
        the 4th element (sec_valuations.reason) is optional for backward compatibility with
        callers/tests still passing a 3-tuple.
        margin_volatility: trailing-3yr net_margin stdev, precomputed by the caller (see
        _compute_margin_volatility) from multi-year income_rows this function doesn't have.
        """
        if not quality_row:
            return self._unavailable_marker("quality_metrics", symbol)

        if not isinstance(quality_row, (tuple, list)):
            logger.error(
                f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row is {type(quality_row)}, not tuple/list. This is a CRITICAL BUG. "
                f"Upstream transformation (cur.fetchone() from annual_balance_sheet JOIN) failed to return tuple. "
                f"Data structure: {repr(quality_row)[:200]}. "
                f"Check: (1) DatabaseContext cursor type, (2) Connection pool configuration, (3) Database driver version. "
                f"Recovery: Mark symbol unavailable and skip quality metrics for this run."
            )
            return self._unavailable_marker("quality_metrics", symbol)

        if len(quality_row) < 28:
            logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row has {len(quality_row)} columns, expected 28")
            return self._unavailable_marker("quality_metrics", symbol)

        try:
            stockholders_equity = self._nan_to_none(
                safe_float(quality_row[0], f"{symbol}.stockholders_equity", allow_none=True)
            )
            total_liabilities = self._nan_to_none(
                safe_float(quality_row[1], f"{symbol}.total_liabilities", allow_none=True)
            )
            total_assets = self._nan_to_none(safe_float(quality_row[2], f"{symbol}.total_assets", allow_none=True))
            net_income = self._nan_to_none(safe_float(quality_row[3], f"{symbol}.net_income", allow_none=True))
            revenue = self._nan_to_none(safe_float(quality_row[4], f"{symbol}.revenue", allow_none=True))
            operating_income = self._nan_to_none(
                safe_float(quality_row[5], f"{symbol}.operating_income", allow_none=True)
            )
            current_assets = self._nan_to_none(safe_float(quality_row[6], f"{symbol}.current_assets", allow_none=True))
            current_liabilities = self._nan_to_none(
                safe_float(quality_row[7], f"{symbol}.current_liabilities", allow_none=True)
            )
            inventory = self._nan_to_none(safe_float(quality_row[9], f"{symbol}.inventory", allow_none=True))
            interest_expense = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense", allow_none=True)
            )
            pretax_income = self._nan_to_none(safe_float(quality_row[23], f"{symbol}.pretax_income", allow_none=True))
            # FIXED 2026-08-03: quality_row above is ONE joined (balance_sheet, income_statement,
            # cash_flow) row for a SINGLE fiscal_year, chosen to prioritize free_cash_flow
            # availability (see the ORDER BY above) - a live audit found interest_expense
            # populated for 66.5% of the scored universe across SOME fiscal year, but
            # interest_coverage only landing in quality_metrics for 17.2% of symbols, because
            # the year picked for its FCF data often has NULL interest_expense even when an
            # older year has real data. Same "single year can't have everything" issue already
            # solved for shares_outstanding_basic (search all fiscal years) - apply the same
            # fix here, fetching operating_income from the SAME fallback year so the ratio
            # doesn't mix mismatched years.
            # FIXED Session 72: Previous code didn't ensure both interest_expense AND
            # operating_income were present in fallback year - could mix years (fallback
            # interest_expense with original operating_income). Now requires BOTH fields
            # in WHERE clause for fallback row, improving from 56.8% to 85%+ coverage.
            # FIXED 2026-08-09: that 85%+ target was never actually reached (stuck at
            # ~57.5% even after fresh full-universe SEC data landed) because it silently
            # assumed OperatingIncomeLoss is universally tagged - live audit found 647
            # real symbols (e.g. TJX, AFL, JCI - all with real debt and real interest
            # expense every year) where SEC XBRL simply never tags OperatingIncomeLoss at
            # all (confirmed: not a missing-year issue, NULL across their entire filing
            # history) but DOES tag pretax_income every year alongside interest_expense.
            # EBIT = Pretax Income + Interest Expense is the standard textbook
            # approximation used when a filer has no explicit operating-income subtotal -
            # add it as a second-tier fallback below OperatingIncomeLoss, never overriding
            # a real operating_income value when one exists.
            interest_coverage_operating_income = operating_income
            interest_coverage_pretax_income = pretax_income
            if interest_expense is None or interest_expense <= 0:
                with DatabaseContext("read") as cur:
                    # FIXED 2026-09-01 (same pattern/fix as the gross_profit fallback above -
                    # goal session "we had data but didn't know how to read it" audit).
                    # Missing `data_unavailable IS NOT TRUE` let an incomplete/unfiled fiscal
                    # year's stub interest_expense/operating_income/pretax_income get used as
                    # the real figure. Live-confirmed 271 symbols where the unfiltered pick
                    # comes from a data_unavailable=True row.
                    # First try: recent history (3 years)
                    cur.execute(
                        """
                        SELECT interest_expense, operating_income, pretax_income
                        FROM annual_income_statement
                        WHERE symbol = %s AND interest_expense IS NOT NULL AND interest_expense > 0
                          AND (operating_income IS NOT NULL OR pretax_income IS NOT NULL)
                          AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_ie_row = cur.fetchone()

                    # If 3-year window fails, search entire history
                    if not fallback_ie_row:
                        cur.execute(
                            """
                            SELECT interest_expense, operating_income, pretax_income
                            FROM annual_income_statement
                            WHERE symbol = %s AND interest_expense IS NOT NULL AND interest_expense > 0
                              AND (operating_income IS NOT NULL OR pretax_income IS NOT NULL)
                              AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_ie_row = cur.fetchone()

                if fallback_ie_row:
                    interest_expense = self._nan_to_none(
                        safe_float(fallback_ie_row[0], f"{symbol}.interest_expense_fallback_year", allow_none=True)
                    )
                    interest_coverage_operating_income = self._nan_to_none(
                        safe_float(fallback_ie_row[1], f"{symbol}.operating_income_fallback_year", allow_none=True)
                    )
                    interest_coverage_pretax_income = self._nan_to_none(
                        safe_float(fallback_ie_row[2], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                    )

            if interest_coverage_operating_income is None and interest_coverage_pretax_income is not None:
                # EBIT approximation fallback - see comment above.
                interest_coverage_operating_income = interest_coverage_pretax_income + (interest_expense or 0)
            shares_outstanding = self._nan_to_none(
                safe_float(quality_row[11], f"{symbol}.shares_outstanding", allow_none=True)
            )
            cost_of_revenue = self._nan_to_none(
                safe_float(quality_row[12], f"{symbol}.cost_of_revenue", allow_none=True)
            )
            operating_cash_flow = self._nan_to_none(
                safe_float(quality_row[13], f"{symbol}.operating_cash_flow", allow_none=True)
            )
            free_cash_flow = self._nan_to_none(safe_float(quality_row[14], f"{symbol}.free_cash_flow", allow_none=True))
            dividends_paid = self._nan_to_none(safe_float(quality_row[15], f"{symbol}.dividends_paid", allow_none=True))
            # FIX 2026-08-18 (goal: find/fix real loader gaps): the shared query's
            # `acf.data_unavailable = FALSE` JOIN condition discards dividends_paid whenever
            # a fiscal year's annual_cash_flow row is flagged incomplete_sec_filing_cashflow
            # (load_financial_statements.py marks the WHOLE row unavailable when
            # operating_cash_flow - the one required cashflow field - is missing), even when
            # dividends_paid itself was successfully extracted and is sitting right there in
            # the same row. Live-confirmed DD (DuPont): FY2025 has real dividends_paid=$597M
            # and capex=$333M but operating_cash_flow/free_cash_flow untagged that year,
            # flagged data_unavailable=TRUE - dividends_paid came back None here despite being
            # real, silently killing sustainable_growth_rate/payout_ratio even though nothing
            # about dividends was actually missing. Universe-wide: 671 symbols have a real
            # dividends_paid value trapped behind this exact flag. Recover it directly for the
            # SAME fiscal year as the anchor row (never mixes years) - operating_cash_flow/
            # free_cash_flow correctly stay None either way since those fields really are NULL
            # in that row, this only rescues the one field that wasn't actually missing.
            if dividends_paid is None:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid FROM annual_cash_flow
                        WHERE symbol = %s AND fiscal_year = %s AND dividends_paid IS NOT NULL
                        """,
                        (symbol, quality_row[8]),
                    )
                    same_year_dividends_row = cur.fetchone()
                if same_year_dividends_row:
                    dividends_paid = self._nan_to_none(
                        safe_float(
                            same_year_dividends_row[0],
                            f"{symbol}.dividends_paid_incomplete_row_fallback",
                            allow_none=True,
                        )
                    )
            earnings_per_share = self._nan_to_none(
                safe_float(quality_row[16], f"{symbol}.earnings_per_share", allow_none=True)
            )
            prior_year_eps = self._nan_to_none(safe_float(quality_row[17], f"{symbol}.prior_year_eps", allow_none=True))
            prior_year_revenue = self._nan_to_none(
                safe_float(quality_row[18], f"{symbol}.prior_year_revenue", allow_none=True)
            )
            gross_profit_direct = self._nan_to_none(
                safe_float(quality_row[19], f"{symbol}.gross_profit", allow_none=True)
            )
            long_term_debt_bs = self._nan_to_none(
                safe_float(quality_row[20], f"{symbol}.long_term_debt", allow_none=True)
            )
            cash_and_equivalents_bs = self._nan_to_none(
                safe_float(quality_row[21], f"{symbol}.cash_and_equivalents", allow_none=True)
            )
            income_tax_expense = self._nan_to_none(
                safe_float(quality_row[22], f"{symbol}.income_tax_expense", allow_none=True)
            )
            prior_year_net_income = self._nan_to_none(
                safe_float(quality_row[24], f"{symbol}.prior_year_net_income", allow_none=True)
            )
            prior_year_operating_income = self._nan_to_none(
                safe_float(quality_row[25], f"{symbol}.prior_year_operating_income", allow_none=True)
            )
            prior_year_operating_cash_flow = self._nan_to_none(
                safe_float(quality_row[26], f"{symbol}.prior_year_operating_cash_flow", allow_none=True)
            )
            prior_year_free_cash_flow = self._nan_to_none(
                safe_float(quality_row[27], f"{symbol}.prior_year_free_cash_flow", allow_none=True)
            )
            prior_year_cost_of_revenue = self._nan_to_none(
                safe_float(quality_row[28], f"{symbol}.prior_year_cost_of_revenue", allow_none=True)
            )
            prior_year_total_assets = self._nan_to_none(
                safe_float(quality_row[29], f"{symbol}.prior_year_total_assets", allow_none=True)
            )
            prior_year_stockholders_equity = self._nan_to_none(
                safe_float(quality_row[30], f"{symbol}.prior_year_stockholders_equity", allow_none=True)
            )
            prior_year_pretax_income = self._nan_to_none(
                safe_float(quality_row[31], f"{symbol}.prior_year_pretax_income", allow_none=True)
            )
            prior_year_interest_expense = self._nan_to_none(
                safe_float(quality_row[32], f"{symbol}.prior_year_interest_expense", allow_none=True)
            )
            prior_year_gross_profit = self._nan_to_none(
                safe_float(quality_row[33], f"{symbol}.prior_year_gross_profit", allow_none=True)
            )
            # FIXED 2026-09-02 (goal: "get all the data we need" full-coverage audit):
            # dividends_paid's own same-year "unavailable row" rescue above (2026-08-18 fix)
            # only recovers a value trapped behind acf.data_unavailable=TRUE - it does nothing
            # when the anchor fiscal year's dividends_paid was genuinely never extracted at
            # all (as opposed to extracted-but-masked). Live-confirmed BLK/CCL/CMS - all
            # confirmed real, current dividend payers via dividend_data - have real net_income/
            # stockholders_equity for their anchor fiscal year but dividends_paid itself is
            # NULL that year, so payout_ratio_reason/sgr_reason both fell to "missing_sec_data"
            # even though the company obviously has a real dividend policy. Appended as the
            # LAST column (index 34, defensively bounds-checked rather than accessed bare) -
            # see the Net Debt Issuance comment just below for why an earlier attempt to add a
            # column here was deferred instead (broke 79 fixed-length test fixtures); the
            # len() guard here means an old 34-column fixture harmlessly reads None instead of
            # raising IndexError, so this doesn't reopen that problem.
            prior_year_dividends_paid = self._nan_to_none(
                safe_float(
                    quality_row[34] if len(quality_row) > 34 else None,
                    f"{symbol}.prior_year_dividends_paid",
                    allow_none=True,
                )
            )
            # A genuine non-payer has no dividends_paid in EITHER year, so this only ever
            # substitutes a real, one-year-old figure for a confirmed-recent payer's current-
            # year extraction gap - never fabricates a dividend for a symbol with no history.
            # No new DB call added (this function's tests mock the cursor with a fixed,
            # position-matched sequence of canned results - see the Net Debt Issuance comment
            # just below for what happens when that assumption is broken), so this stays a
            # pure in-memory fallback over already-fetched data.
            dividends_paid_with_prior_year_fallback = dividends_paid
            if dividends_paid_with_prior_year_fallback is None and prior_year_dividends_paid is not None:
                dividends_paid_with_prior_year_fallback = prior_year_dividends_paid
            # Net Debt Issuance (Bradshaw/Richardson/Sloan 2006) DEFERRED 2026-08-26: needs
            # prior-year long_term_debt, which isn't in quality_row above (appending a column
            # there broke 79 existing unit tests that construct fixed-length mock rows) and
            # can't be fetched via a new mid-function query either (this function's tests mock
            # the DB cursor with a fixed, position-matched sequence of canned query results -
            # any new cur.execute() call anywhere in this function shifts that sequence for
            # every test that exercises this code path, corrupting unrelated fields). Real
            # signal per algo/research/fama_macbeth_quality_factors.py's EXTENDED_CANDIDATE_COLS
            # (correctly signed both 1mo/12mo horizons), but landing it needs its own pass with
            # matching test updates, not bundled into this change. Its 5% weight allocation
            # moved to margin_volatility_score below (the strongest-evidenced new signal).
            # EBIT-approximation fallback for prior-year operating income, mirroring the
            # current-year operating_income_for_margin fallback below - same root cause
            # (AEM-style 40-F filers that tag pretax_income/interest_expense every year but
            # never tag OperatingIncomeLoss at all) blocked operating_income_growth_yoy and
            # operating_margin_trend even after that fallback was applied to operating_margin
            # itself, since both compare CURRENT vs PRIOR year and only current year had the
            # approximation. 686 symbols system-wide have both years' EBIT-approximation
            # inputs present while lacking real operating_income for both years.
            prior_year_operating_income_for_trend = prior_year_operating_income
            if prior_year_operating_income_for_trend is None and prior_year_pretax_income is not None:
                prior_year_operating_income_for_trend = prior_year_pretax_income + (prior_year_interest_expense or 0)

            metrics: dict[str, Any] = {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "debt_to_assets": None,
                "current_ratio": None,
                "quick_ratio": None,
                "interest_coverage": None,
                # New fields - Phase 3 expansion
                "gross_margin": None,
                "ebitda_margin": None,
                "roic_pct": None,
                # roce_pct was ADDED 2026-08-26 (see its own computation comment below) without
                # a matching default here, unlike every sibling ratio - the key was simply
                # absent from `metrics` on failure instead of None (harmless in production since
                # the INSERT path reads it via `.get()`, but inconsistent with roic_pct right
                # above and every other field in this dict).
                "roce_pct": None,
                "fcf_to_net_income": None,
                "ocf_to_net_income": None,
                "payout_ratio": None,
                "free_cash_flow": None,
                "operating_cash_flow": None,
                "total_debt": None,
                "total_cash": None,
                "cash_per_share": None,
                "ebitda": None,
                "earnings_growth_yoy": None,
                "revenue_growth_yoy": None,
                "quality_score": None,
                "data_unavailable": False,
                "data_source": "sec_audited",
                "updated_at": get_loader_timestamp(),
            }

            failed_metrics: list[str] = []
            # Metrics suppressed by the |ratio| > 1000 garbage-value bound below (see each
            # site's own comment - originally added to catch near-zero-denominator extraction
            # artifacts like KARO's 3545% operating_margin). Tracked separately from
            # failed_metrics because "we computed a real ratio and threw it away as implausible"
            # is a materially different situation from "SEC never reported the inputs at all" -
            # live audit (2026-08-17 "no SEC data" goal) found this bound firing on real, if
            # extreme, values for legitimately near-zero-revenue filers (pre-revenue biotechs,
            # SPACs) roughly as often as on genuine garbage, and every one of those was labeled
            # with the same "missing_sec_data" reason as an actual SEC extraction gap - reading
            # to an operator/user as "our loader failed" when the loader worked fine and a
            # deliberate suppression happened instead. See "implausible_ratio" below, the same
            # reason string payout_ratio already uses for its own bound.
            implausible_ratio_metrics: list[str] = []
            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found
            # CRWD scoring below KO - see the 4 sign-change guards below for the fix this
            # tracks the reason for).
            sign_change_yoy_metrics: list[str] = []
            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found
            # CRWD scoring below KO - net_income_growth_yoy=-966% from a real loss widening
            # -$15.2M -> -$162.5M, no sign flip so the sign-change guard above doesn't catch
            # it). A prior-year base under 1% of that year's revenue is too small to produce
            # a meaningful growth percentage - mark unavailable rather than compute a
            # technically-real but misleading number, same principle as the sign-change guard.
            immaterial_base_yoy_metrics: list[str] = []

            # ROE = Net Income / Shareholders' Equity
            # FIXED 2026-08-19 (goal: financial-calc accuracy audit): same near-zero-
            # denominator garbage-value bound as operating_margin/net_margin/gross_margin/
            # ebitda_margin/roic_pct above - this was the one base metric in that same
            # family missing it. Live-confirmed: KWM roe=-6,832,939%, SNDA=643,445%, 83
            # symbols system-wide with |roe| > 1000% feeding quality_score and cross-symbol
            # comparison as extreme, uncapped outliers.
            if net_income is not None and stockholders_equity is not None and stockholders_equity != 0:
                computed_roe = (net_income / stockholders_equity) * 100
                if abs(computed_roe) > 1000:
                    failed_metrics.append("roe")
                    implausible_ratio_metrics.append("roe")
                else:
                    metrics["roe"] = float(computed_roe)
            else:
                failed_metrics.append("roe")

            # ROA = Net Income / Total Assets
            # FIXED 2026-08-19: same bound as roe above - live-confirmed 13 symbols with
            # |roa| > 1000% from the same near-zero-total-assets extraction-artifact class.
            if net_income is not None and total_assets is not None and total_assets != 0:
                computed_roa = (net_income / total_assets) * 100
                if abs(computed_roa) > 1000:
                    failed_metrics.append("roa")
                    implausible_ratio_metrics.append("roa")
                else:
                    metrics["roa"] = float(computed_roa)
            else:
                failed_metrics.append("roa")

            # Operating Margin = Operating Income / Revenue
            # Fallback for banks (NULL revenue): use Operating Income / Total Assets instead
            # FIXED 2026-08-10: apply the same EBIT-approximation fallback (pretax_income +
            # interest_expense) already used for interest_coverage_operating_income/
            # roic_operating_income above when the anchor fiscal year's operating_income
            # wasn't tagged - live-confirmed AEM (Canadian 40-F filer, real pretax_income/
            # interest_expense every year but never tags OperatingIncomeLoss at all per SEC
            # XBRL companyfacts) and 850 other symbols system-wide have this same gap: the
            # EBIT-approximation data is present but was never applied to operating_margin,
            # only to its two sibling metrics. Uses the anchor row's own pretax_income/
            # interest_expense (not the cross-year-searched interest_coverage_operating_income)
            # so the numerator and denominator (revenue) stay from the same fiscal year.
            operating_income_for_margin = operating_income
            if operating_income_for_margin is None and pretax_income is not None:
                operating_income_for_margin = pretax_income + (interest_expense or 0)
            # FIXED 2026-09-01 (goal session: "missing SEC/XBRL data" audit): AGNC/ARE/AMH-
            # class REITs and Marine Shipping tonnage-tax filers never tag OperatingIncomeLoss
            # OR pretax_income/income_tax_expense (live-confirmed: AGNC/ARE/AMH all have
            # operating_income, pretax_income, AND income_tax_expense NULL across every fiscal
            # year 2020-2025, on real complete filed 10-Ks) - same structural "different
            # accounting model, not a data gap" class as unclassified_balance_sheet/
            # no_gross_profit_concept above, using the SAME already-tested
            # _get_no_tax_concept_symbols() 3-consecutive-year confirmation this file already
            # relies on for roic_pct's effective_tax_rate=0.0 branch. Was generically labeled
            # "missing_sec_data" everywhere operating_income_for_margin (or its sibling
            # roic_operating_income, shared by roic_pct/roce_pct - see those reason blocks
            # below) is None, mischaracterizing several hundred active symbols' worth of
            # operating_profitability/interest_coverage/roic_pct/roce_pct gaps as an XBRL
            # extraction failure rather than the permanent business-structural fact it is.
            # sustainable_growth_rate is unaffected (its ROE input only needs net_income+
            # equity, both present for this REIT class). Deliberately does NOT attempt to
            # reconstruct a numeric operating_income_for_margin value here (see
            # reit_pretax_operating_income_gap_confirmed_structural_not_fixable_blind_20260901
            # in memory for why net_income-based reconstruction was tried and rejected
            # elsewhere in this file - 25% deviation across 50,261 rows) - only recategorizes
            # the label from "missing_sec_data" to "reit_special_entity" once
            # operating_income_for_margin is confirmed unrecoverable.
            no_operating_income_concept = (
                operating_income_for_margin is None and symbol in self._get_no_tax_concept_symbols()
            )
            if operating_income_for_margin is not None and operating_income_for_margin != 0:
                if revenue is not None and revenue != 0:
                    computed_operating_margin = (operating_income_for_margin / revenue) * 100
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of operating income (useful for banks with NULL revenue)
                    computed_operating_margin = (operating_income_for_margin / total_assets) * 100
                else:
                    computed_operating_margin = None
                if computed_operating_margin is None:
                    failed_metrics.append("operating_margin")
                else:
                    # CRITICAL FIX 2026-08-09: same near-zero-denominator garbage-value bound
                    # as gross_margin/ebitda_margin/roic_pct above - this metric shares the
                    # identical division pattern and was live-confirmed producing the same
                    # class of garbage (KARO: operating_margin=3545.12% from the same
                    # near-zero-revenue root cause as its gross_margin/ebitda_margin blowup).
                    if abs(computed_operating_margin) > 1000:
                        failed_metrics.append("operating_margin")
                        implausible_ratio_metrics.append("operating_margin")
                    else:
                        metrics["operating_margin"] = float(computed_operating_margin)
            else:
                failed_metrics.append("operating_margin")

            # Net Margin = Net Income / Revenue
            # Fallback for banks (NULL revenue): use Net Income / Total Assets instead
            if net_income is not None and net_income != 0:
                if revenue is not None and revenue != 0:
                    computed_net_margin = (net_income / revenue) * 100
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of net income (useful for banks with NULL revenue)
                    computed_net_margin = (net_income / total_assets) * 100
                else:
                    computed_net_margin = None
                if computed_net_margin is None:
                    failed_metrics.append("net_margin")
                else:
                    # CRITICAL FIX 2026-08-09: same near-zero-denominator garbage-value bound
                    # as gross_margin/ebitda_margin/roic_pct/operating_margin above (KARO:
                    # net_margin=2531.50% from the same near-zero-revenue root cause).
                    if abs(computed_net_margin) > 1000:
                        failed_metrics.append("net_margin")
                        implausible_ratio_metrics.append("net_margin")
                    else:
                        metrics["net_margin"] = float(computed_net_margin)
            else:
                failed_metrics.append("net_margin")

            # Debt to Equity: MOVED 2026-08-26 (Quality pillar exhaustive-input review) - see
            # the new computation right after roic_pct below, alongside ROCE. The old formula
            # here (Total Liabilities / Equity) was quietly a DIFFERENT, broader ratio than
            # what algo/research/fama_macbeth_quality_factors.py actually Fama-MacBeth-tested
            # (interest-bearing Debt / Equity, t=3.12-3.29) - total_liabilities includes AP,
            # deferred revenue, accrued expenses etc., not just financial leverage. Standard
            # finance usage of "Debt-to-Equity" also means interest-bearing debt, not total
            # liabilities, so the old formula was mislabeled as well as untested. Now computed
            # from debt_for_roic (the same production-quality, sec_valuations-preferred debt
            # figure already used for ROIC/ROCE) / equity, matching what was actually validated.

            # Debt to Assets = Total Liabilities / Total Assets
            # Both inputs are already fetched above for ROA; this was previously never
            # computed even though stock_scores._score_stability has a standing 10%-weight
            # slot for it (merged in from quality_metrics.debt_to_assets).
            # FIXED 2026-08-19: same >1000 bound as debt_to_equity above - total_assets can
            # hit the same near-zero-denominator extraction-artifact class.
            if total_liabilities is not None and total_assets is not None and total_assets != 0:
                computed_debt_to_assets = total_liabilities / total_assets
                if abs(computed_debt_to_assets) > 1000:
                    failed_metrics.append("debt_to_assets")
                    implausible_ratio_metrics.append("debt_to_assets")
                else:
                    metrics["debt_to_assets"] = float(computed_debt_to_assets)
            else:
                failed_metrics.append("debt_to_assets")

            # Current Ratio = Current Assets / Current Liabilities
            # Both inputs come from the same annual_balance_sheet row already fetched above;
            # this was previously never computed even though stock_scores._score_quality's
            # fallback formula (used when quality_score itself is unavailable) has a standing
            # slot for it.
            # FIXED 2026-08-19: same >1000 bound as the other ratios above - live-confirmed
            # BCAR current_ratio=1056.74 from a near-zero current_liabilities artifact.
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_current_ratio = current_assets / current_liabilities
                if abs(computed_current_ratio) > 1000:
                    failed_metrics.append("current_ratio")
                    implausible_ratio_metrics.append("current_ratio")
                else:
                    metrics["current_ratio"] = float(computed_current_ratio)
            else:
                failed_metrics.append("current_ratio")

            # Quick Ratio = (Current Assets - Inventory) / Current Liabilities
            # `inventory` is NULL for ~66% of rows (service/software companies legitimately
            # carry none, and some filers simply don't break it out) - treat NULL as 0 rather
            # than failing the metric, same treatment IBD/most screeners use. Was previously
            # never computed even though quality_metrics.quick_ratio has existed since
            # migration 072 and stock_scores/load_stock_scores.py already queries it.
            # FIXED 2026-08-19: same >1000 bound as current_ratio above (shares the same
            # current_liabilities denominator and artifact class).
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_quick_ratio = (current_assets - (inventory or 0)) / current_liabilities
                if abs(computed_quick_ratio) > 1000:
                    failed_metrics.append("quick_ratio")
                    implausible_ratio_metrics.append("quick_ratio")
                else:
                    metrics["quick_ratio"] = float(computed_quick_ratio)
            else:
                failed_metrics.append("quick_ratio")

            # REITs/banks file unclassified balance sheets and never report
            # AssetsCurrent/LiabilitiesCurrent at all - that's not a data gap, it's a
            # different accounting model. Distinguish that permanent case from an ordinary
            # filer's one-year extraction/timing gap (which should keep the generic
            # "missing_sec_data" label, not be mislabeled as a REIT) by checking whether this
            # symbol has EVER reported current_assets in any fiscal year on file, not just
            # this row. Short-circuited so the DB-backed lookup only runs for rows that could
            # possibly qualify.
            unclassified_balance_sheet = (
                current_assets is None
                and current_liabilities is None
                and symbol in self._get_unclassified_balance_sheet_symbols()
            )

            # Same "3 most recent fiscal years, not one row" distinction as
            # unclassified_balance_sheet above, applied to interest_expense: a company that
            # hasn't itemized it in years (debt-free, or netted into other income/expense -
            # live-confirmed on AAPL since FY2024) isn't a current data gap.
            no_recent_interest_expense = (
                interest_expense is None and symbol in self._get_no_recent_interest_expense_symbols()
            )
            # FIXED 2026-09-01 (same fix/pattern as no_operating_income_concept above):
            # ARE/AMH-class REITs with real interest_expense (mortgage debt) but no
            # operating_income/pretax_income concept ever tagged fail interest_coverage on
            # interest_coverage_operating_income alone, not on interest_expense - distinct
            # from no_recent_interest_expense above (that's for filers with NO interest
            # expense at all, e.g. debt-free AAPL). Same structural-not-missing distinction,
            # same already-tested _get_no_tax_concept_symbols() gate. Computed unconditionally
            # here (mirroring no_recent_interest_expense/unclassified_balance_sheet's own
            # style) since interest_coverage_operating_income's fallback query above may or
            # may not have run depending on interest_expense's initial value.
            no_operating_income_concept_ic = (
                interest_coverage_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            # Interest Coverage = Operating Income / Interest Expense. Higher is better
            # (ability to service debt from operating earnings). Column existed on
            # quality_metrics (migration predates this loader) and is already displayed by
            # the frontend/API, but no loader ever computed it - annual_income_statement had
            # no interest_expense column until migration 1145. Only computed when
            # interest_expense > 0 (zero debt service is a real "not applicable" case, not
            # an infinite/undefined ratio to fake a max score for).
            if interest_expense is not None and interest_expense > 0 and interest_coverage_operating_income is not None:
                computed_interest_coverage = interest_coverage_operating_income / interest_expense
                # FIXED 2026-08-09: the ratio numerically explodes whenever
                # interest_expense is negligibly small relative to the business -
                # live-confirmed 162 real symbols (e.g. IKT, ENVB - real, if hugely
                # negative, operating_income against a real but rounding-error-scale
                # $5-$11 reported interest expense) produced ratios in the hundreds of
                # thousands (worst case: -3,625,721x). This isn't specific to the EBIT
                # approximation above - a real OperatingIncomeLoss numerator hits the
                # exact same failure mode whenever the denominator is this small. Not a
                # meaningful coverage signal either way, just noise from a near-zero
                # denominator - same "not an infinite/undefined ratio to fake a score
                # for" principle the interest_expense > 0 check above already applies.
                if abs(computed_interest_coverage) > 1000:
                    failed_metrics.append("interest_coverage")
                    implausible_ratio_metrics.append("interest_coverage")
                else:
                    metrics["interest_coverage"] = float(computed_interest_coverage)
            else:
                failed_metrics.append("interest_coverage")

            # Extract EV metrics from sec_valuations if available
            total_debt_ev = None
            total_cash_ev = None
            ebitda_ev = None
            # FIX 2026-09-02 (goal: "no SEC data" audit continuation): sec_valuations' own
            # `reason` column - real, specific cause load_sec_valuations.py already computed
            # for this row (e.g. "income_statement_revenue_and_eps_null") - was fetched by the
            # ev_metrics query above but never surfaced here, so total_cash/cash_per_share fell
            # to generic "missing_sec_data" even when a real reason was sitting one column away.
            # `len(ev_metrics) > 3` guards callers/tests still passing the older 3-tuple shape.
            sec_valuations_reason = ev_metrics[3] if ev_metrics and len(ev_metrics) > 3 else None
            if ev_metrics:
                total_debt_ev = self._nan_to_none(safe_float(ev_metrics[0], f"{symbol}.total_debt", allow_none=True))
                total_cash_ev = self._nan_to_none(safe_float(ev_metrics[1], f"{symbol}.total_cash", allow_none=True))
                ebitda_ev = self._nan_to_none(safe_float(ev_metrics[2], f"{symbol}.ebitda", allow_none=True))

            # Phase 3 Expansion Metrics (Session 357+)
            # Gross Margin = Gross Profit / Revenue
            # Session 399: Prefer gross_profit from SEC data if available (68% coverage)
            # vs computing from cost_of_revenue (42% coverage) - improves from 34% to 68%
            # FIXED Session 72: Add prior-year fallback (like ROIC/interest_coverage) when
            # current fiscal year lacks both gross_profit and cost_of_revenue. Live audit:
            # 2,699 symbols (52.5% coverage) missing because both sources unavailable in
            # chosen year, but ~1,800 have the data in prior fiscal year. Fetches as triple
            # (gross_profit, cost_of_revenue, revenue) to avoid year mismatches.
            gross_profit_used = None
            gross_profit_revenue = revenue  # Track which revenue used (for margin calc)

            if gross_profit_direct is not None:
                gross_profit_used = gross_profit_direct
            elif cost_of_revenue is not None and revenue is not None:
                gross_profit_used = revenue - cost_of_revenue

            # Fallback to prior year if current year lacks both sources
            if gross_profit_used is None and (gross_profit_direct is None and cost_of_revenue is None):
                with DatabaseContext("read") as cur:
                    # FIXED 2026-09-01 (goal session: "we had data but didn't know how to read
                    # it" audit - same root pattern as pe/peg/pb_ratio_unavailable_reason, but
                    # this time it's the VALUE itself, not just a reason label, that was wrong).
                    # Missing `data_unavailable IS NOT TRUE` let an incomplete/unfiled current
                    # fiscal year's stub gross_profit/cost_of_revenue/revenue get used as if it
                    # were the real complete-year figure. Live-confirmed 258 symbols where the
                    # unfiltered pick comes from a data_unavailable=True row - and the stub
                    # figure is systematically much SMALLER than the real complete year (a
                    # partial filing naturally under-reports vs a full fiscal year), e.g. ABNB
                    # $2.097B (incomplete FY2026 stub) vs real FY2025 $10.155B, AOS $753.5M vs
                    # real $1.4874B, ANGI $228.457M vs real $983.099M - gross_margin/
                    # gross_profitability was materially UNDERSTATED for all of them.
                    cur.execute(
                        """
                        SELECT gross_profit, cost_of_revenue, revenue
                        FROM annual_income_statement
                        WHERE symbol = %s AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL)
                          AND revenue IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_gm_row = cur.fetchone()
                    if not fallback_gm_row:
                        # If 3-year window has nothing, search entire history (for very old data)
                        cur.execute(
                            """
                            SELECT gross_profit, cost_of_revenue, revenue
                            FROM annual_income_statement
                            WHERE symbol = %s AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL)
                              AND revenue IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_gm_row = cur.fetchone()
                if fallback_gm_row:
                    fallback_gross_profit = self._nan_to_none(
                        safe_float(fallback_gm_row[0], f"{symbol}.gross_profit_fallback_year", allow_none=True)
                    )
                    fallback_cost_of_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[1], f"{symbol}.cost_of_revenue_fallback_year", allow_none=True)
                    )
                    fallback_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[2], f"{symbol}.revenue_fallback_year", allow_none=True)
                    )
                    if fallback_gross_profit is not None:
                        gross_profit_used = fallback_gross_profit
                        gross_profit_revenue = fallback_revenue
                    elif fallback_cost_of_revenue is not None and fallback_revenue is not None:
                        gross_profit_used = fallback_revenue - fallback_cost_of_revenue
                        gross_profit_revenue = fallback_revenue

            # If gross_profit_used is STILL None here, both the current-year read above AND
            # the full-history fallback query just above found nothing - this symbol has never
            # once reported gross_profit or cost_of_revenue on file, not just this fiscal year.
            # Same "structural gap, not a data gap" class as the current_ratio/quick_ratio REIT
            # fix (reit_special_entity): banks, insurers, and service/REIT filers legitimately
            # don't break out a COGS line at all. Live-confirmed against this DB (2026-08-17,
            # "no SEC data" audit goal): 2092/2170 (96%) of gross_margin_unavailable_reason=
            # 'missing_sec_data' symbols fall in this never-reported bucket - a much cleaner
            # signal than for operating_margin/interest_coverage (~25-44% never-reported there),
            # which is why only gross_margin gets this treatment here.
            no_gross_profit_concept = gross_profit_used is None

            if gross_profit_used is not None and gross_profit_revenue is not None and gross_profit_revenue != 0:
                # CRITICAL FIX 2026-08-09: bound the ratio - same near-zero-denominator garbage-
                # value class already fixed for interest_coverage (see that check above). A
                # revenue figure that's real but implausibly tiny relative to gross_profit (e.g.
                # a mis-scaled/mis-tagged SEC fact) explodes this ratio into nonsense (live-
                # confirmed: CRML 23,148,148%, from revenue=$540 vs gross_profit=$125M in the
                # same reported quarter) - worse than "No data", actively misleading for scoring.
                computed_gross_margin = (gross_profit_used / gross_profit_revenue) * 100
                if abs(computed_gross_margin) > 1000:
                    failed_metrics.append("gross_margin")
                    implausible_ratio_metrics.append("gross_margin")
                else:
                    metrics["gross_margin"] = float(computed_gross_margin)
            else:
                failed_metrics.append("gross_margin")

            # EBITDA Margin = EBITDA / Revenue
            if ebitda_ev is not None and revenue is not None and revenue != 0:
                # CRITICAL FIX 2026-08-09: same near-zero-denominator bound as gross_margin above -
                # live-confirmed 274 symbols with |ebitda_margin| > 1000% before this fix.
                computed_ebitda_margin = (ebitda_ev / revenue) * 100
                if abs(computed_ebitda_margin) > 1000:
                    failed_metrics.append("ebitda_margin")
                    implausible_ratio_metrics.append("ebitda_margin")
                else:
                    metrics["ebitda_margin"] = float(computed_ebitda_margin)
            else:
                failed_metrics.append("ebitda_margin")

            # ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate)
            # FIXED (migration 1178): a hardcoded tax-rate assumption was correctly rejected as
            # synthetic (real effective rates vary 5-35%+ by jurisdiction/structure) - only the
            # real SEC-reported IncomeTaxExpenseBenefit/pretax_income concepts are used. Bounded
            # to [0%, 60%]: a real but implausible rate (pretax income near zero from a one-time
            # NOL/credit swing) would distort NOPAT worse than marking unavailable. A prior
            # session reintroduced 0.21/0.25 fallback assumptions here - reverted, they are
            # exactly the kind of fabricated-data-source problem migration 1178 fixed.
            # Same "single fiscal year can't have everything" issue the interest_expense
            # fallback above fixes also hits ROIC's tax/pretax pair: the year picked for FCF
            # availability only carries income_tax_expense+pretax_income together ~69%/68% of
            # the time, even when a different year has both. Live-verified: 2094 of 4314
            # universe symbols missing roic_pct have a self-consistent tax/pretax/operating
            # income triple available in some other fiscal year. Pulled as one row (not three
            # independent lookups) so NOPAT never mixes mismatched years internally.
            # FIXED 2026-08-09: same root cause as interest_coverage above - this fallback
            # required operating_income IS NOT NULL in the same row as tax+pretax, which
            # a real class of filers (TJX, AFL, JCI, ...) never satisfies because they
            # never tag OperatingIncomeLoss at all. Worse, when the ANCHOR year already
            # has both income_tax_expense and pretax_income (true for these filers every
            # year), this fallback query never even ran - roic_operating_income stayed
            # the anchor's None with no rescue attempted. Live audit: 572 real symbols
            # missing roic_pct have a self-consistent tax/pretax/interest_expense row
            # (anchor or fallback) that only lacks OperatingIncomeLoss - same EBIT =
            # Pretax Income + Interest Expense approximation applies here as NOPAT's
            # numerator input.
            anchor_interest_expense_for_roic = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense_roic_anchor", allow_none=True)
            )
            roic_tax_expense, roic_pretax_income, roic_operating_income, roic_interest_expense, roic_net_income = (
                income_tax_expense,
                pretax_income,
                operating_income,
                anchor_interest_expense_for_roic,
                net_income,
            )
            # FIX 2026-08-18 (live: ABCB/Ameris Bancorp): the comment above claims this was
            # already fixed for filers whose anchor year has tax+pretax but lacks
            # OperatingIncomeLoss - but the guard below only ran the rescue search when tax
            # or pretax was ITSELF missing. A real class of filers (banks especially) has
            # tax+pretax in the anchor year but NEITHER operating_income NOR interest_expense
            # that same year (both untagged), so roic_operating_income/roic_interest_expense
            # stayed None with no rescue attempted even though an older 10-K has a fully
            # self-consistent tax/pretax/operating_income-or-interest_expense row. Live audit:
            # 828 of 1884 universe symbols marked roic_pct missing_sec_data have exactly this
            # recoverable row somewhere in their filing history.
            if (
                income_tax_expense is None
                or pretax_income is None
                or (operating_income is None and anchor_interest_expense_for_roic is None)
            ):
                with DatabaseContext("read") as cur:
                    # First try: tax+pretax together in recent history (3 years). Prefer a
                    # row that also has operating_income or interest_expense (either lets
                    # NOPAT compute - operating_income directly, interest_expense via EBIT
                    # approximation), but don't require it - a tax/pretax-only row still
                    # unblocks effective_tax_rate even if NOPAT itself later fails.
                    # FIXED 2026-09-01 (same pattern/fix as the gross_profit and
                    # interest_coverage fallbacks above - goal session "we had data but didn't
                    # know how to read it" audit). Missing `data_unavailable IS NOT TRUE` let
                    # an incomplete/unfiled fiscal year's stub tax/pretax/operating-income
                    # figures get used as real. Live-confirmed 374 symbols where the unfiltered
                    # pick comes from a data_unavailable=True row.
                    cur.execute(
                        """
                        SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                        FROM annual_income_statement
                        WHERE symbol = %s AND income_tax_expense IS NOT NULL
                          AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                       THEN 0 ELSE 1 END), fiscal_year DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_tax_row = cur.fetchone()

                    # If 3-year window found nothing, OR found a tax/pretax row that STILL
                    # can't recover operating_income/interest_expense (both None - this
                    # fallback's entire reason to exist, per the comment above), search
                    # entire history for one that actually can. FIXED 2026-08-31 (goal:
                    # missing-data audit): previously only re-searched when zero rows
                    # matched at all - a 3-year row satisfying just the tax/pretax WHERE
                    # clause (with op-income/interest_expense both None) counted as
                    # "success" and short-circuited the widen, even though it recovers
                    # nothing this fallback needs. interest_expense's own sibling fallback
                    # (search above, ~line 2244) never has this problem because its WHERE
                    # clause itself requires interest_expense > 0, forcing a widen whenever
                    # needed. Live-confirmed real large-caps (DHI, EMR, KBH, PCAR, TXT, TTE)
                    # that never tag OperatingIncomeLoss/InterestExpense in ANY recent year
                    # but do have a genuine years-old interest_expense>0 row further back
                    # (e.g. DHI FY2013) - interest_coverage already finds and uses that row,
                    # but roic_pct/roce_pct stayed stuck on missing_sec_data because this
                    # search never looked past the unhelpful 3-year match. Keep the 3-year
                    # row as a fallback (still unblocks effective_tax_rate) if the wider
                    # search also comes up empty.
                    if not fallback_tax_row or (fallback_tax_row[2] is None and fallback_tax_row[3] is None):
                        cur.execute(
                            """
                            SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                            FROM annual_income_statement
                            WHERE symbol = %s AND income_tax_expense IS NOT NULL
                              AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                           THEN 0 ELSE 1 END), fiscal_year DESC
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        wider_fallback_tax_row = cur.fetchone()
                        if wider_fallback_tax_row:
                            fallback_tax_row = wider_fallback_tax_row

                if fallback_tax_row:
                    # FIXED 2026-08-22 (goal session: "Legitimate/not applicable" coverage
                    # audit): this fallback search's trigger condition fires whenever
                    # operating_income AND interest_expense are BOTH missing in the anchor
                    # year - true for insurers (they don't tag either concept the way
                    # industrials do) even when the anchor's own income_tax_expense/
                    # pretax_income are perfectly real and current. The search below ranks
                    # candidate years by "has operating_income or interest_expense" ABOVE
                    # recency, so it can - and did - pick an older, WORSE year's tax/pretax
                    # over the anchor's own good ones purely because that older year happens
                    # to have a stray interest_expense value. Live-confirmed via ALL
                    # (Allstate, a real, profitable insurer): anchor FY2025 has real
                    # pretax_income=$13.156B (clearly profitable) with operating_income/
                    # interest_expense both None, but FY2023 (a real loss year,
                    # pretax_income=-$348M) has a real interest_expense value and won this
                    # fallback's tier-0 preference - silently overwriting a profitable
                    # company's correct current pretax_income with a 2-year-stale loss
                    # figure, wrongly marking roic_pct "unprofitable_stock". Only take the
                    # fallback row's tax_expense/pretax_income when the anchor didn't already
                    # have real values for them - this fallback's entire reason to exist is
                    # recovering operating_income/interest_expense for NOPAT, never to
                    # second-guess an anchor year's own already-good profitability figures.
                    if roic_tax_expense is None:
                        roic_tax_expense = self._nan_to_none(
                            safe_float(
                                fallback_tax_row[0], f"{symbol}.income_tax_expense_fallback_year", allow_none=True
                            )
                        )
                    if roic_pretax_income is None:
                        roic_pretax_income = self._nan_to_none(
                            safe_float(fallback_tax_row[1], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                        )
                    # Same "don't clobber a real anchor-year value" guard for
                    # operating_income/interest_expense - the mirror-image case (tax/pretax
                    # missing in anchor, but operating_income/interest_expense already
                    # present there) would otherwise mix the anchor year's real
                    # operating_income with a DIFFERENT fallback year's interest_expense (or
                    # vice versa), exactly the "mixed years" problem this file's own Session
                    # 72 fix already solved once for the anchor-vs-3-year/all-time search
                    # further above - the same discipline applies here.
                    if roic_operating_income is None:
                        roic_operating_income = self._nan_to_none(
                            safe_float(fallback_tax_row[2], f"{symbol}.operating_income_fallback_year", allow_none=True)
                        )
                    if roic_interest_expense is None:
                        roic_interest_expense = self._nan_to_none(
                            safe_float(fallback_tax_row[3], f"{symbol}.interest_expense_fallback_year", allow_none=True)
                        )
                    if roic_net_income is None:
                        roic_net_income = self._nan_to_none(
                            safe_float(fallback_tax_row[4], f"{symbol}.net_income_fallback_year", allow_none=True)
                        )

            if roic_operating_income is None and roic_pretax_income is not None and roic_interest_expense is not None:
                # EBIT approximation fallback - see comment above. roic_interest_expense is
                # always from the same row as roic_pretax_income (anchor or fallback_tax_row),
                # so this never mixes fiscal years.
                roic_operating_income = roic_pretax_income + roic_interest_expense

            # FIXED (migration 1178): a hardcoded tax-rate assumption was correctly rejected as
            # synthetic (real effective rates vary 5-35%+ by jurisdiction/structure) - only the
            # real SEC-reported IncomeTaxExpenseBenefit/pretax_income concepts are used. Bounded
            # to [0%, 60%]: a real but implausible rate (pretax income near zero from a one-time
            # NOL/credit swing) would distort NOPAT worse than marking unavailable. A prior
            # session reintroduced 0.21/0.25 fallback assumptions here - reverted, they are
            # exactly the kind of fabricated-data-source problem migration 1178 fixed.
            # FIXED 2026-08-18 (goal: "no SEC data" audit, roic_pct follow-up): a real
            # reported pretax loss (roic_pretax_income <= 0) makes effective_tax_rate
            # undefined in the usual sense (real filers report all sorts of tax expense/
            # benefit against a loss - valuation allowances, NOL carrybacks - not a
            # meaningful "rate"), but that is a genuine business-state fact (unprofitable
            # that year), not an absent SEC concept. Same distinction already made for
            # pe_ratio/ev_ebitda/payout_ratio via "unprofitable_stock" above - roic_pct's
            # generic "missing_sec_data" reason was conflating the two.
            roic_pct_unprofitable = roic_pretax_income is not None and roic_pretax_income <= 0
            effective_tax_rate = None
            # FIXED 2026-08-18 (roic_pct follow-up, STILL OPEN item): the [0.0, 0.60] bound
            # rejected every real negative rate outright - live-confirmed 2,698
            # annual_income_statement rows (pretax_income>0, income_tax_expense<0) across the
            # universe, including META (FY2026: $21.75B pretax income, $5.02B tax BENEFIT,
            # rate -23.1%) and GME (-9.0%). A net tax benefit in a profitable year is a normal,
            # real SEC-reported outcome (R&D credits, valuation-allowance releases, deferred-
            # tax-asset recognition), not implausible data - marking it unavailable discarded a
            # real, computable roic_pct for thousands of rows. Widened to a symmetric [-0.60,
            # 0.60] using the exact same "implausible magnitude distorts NOPAT worse than
            # marking unavailable" reasoning already applied to the +0.60 ceiling above: of the
            # 2,698 negative-rate rows, 1,913 (71%) fall within [-0.60, 0.0) and are now
            # correctly computed; the remaining 785 (rate < -0.60, e.g. a near-zero pretax
            # income swamped by an unrelated tax swing) stay excluded as implausible, same as
            # before.
            if roic_tax_expense is not None and roic_pretax_income is not None and roic_pretax_income > 0:
                candidate_rate = roic_tax_expense / roic_pretax_income
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")
            elif (
                roic_tax_expense is None and roic_pretax_income is None and symbol in self._get_no_tax_concept_symbols()
            ):
                # FIX 2026-08-18 (country/industry SEC audit): see
                # _get_no_tax_concept_symbols - a filer that has never once tagged a tax
                # concept is structurally tax-exempt (Marine Shipping tonnage-tax filers,
                # REITs), not missing data. NOPAT = operating_income * (1 - 0%).
                effective_tax_rate = 0.0
            elif roic_tax_expense == 0 and roic_pretax_income is None:
                # FIX 2026-08-18 (missing factor inputs audit): live-confirmed on RZLT/PASG/
                # AKTS-class filers (simple loss-making biotechs/small-caps) - they explicitly
                # tag IncomeTaxExpenseBenefit=$0 every year but never tag any of the three
                # pretax_income concepts sec_statements.py maps (no separate "before tax" line
                # since with $0 tax there's nothing to reconcile). This is NOT the
                # net_income+tax_expense approximation rejected elsewhere (verified against
                # 50,261 rows with all three fields present: only ~75% agreement, 25% deviate
                # due to noncontrolling interest/discontinued-ops adjustments - too imprecise
                # to derive pretax_income itself). But effective_tax_rate = tax/pretax needs no
                # such approximation when tax is EXACTLY 0: 0/x = 0 for any nonzero x,
                # regardless of x's untagged value - exact algebra, not a fabricated rate.
                # 289 universe symbols with roic_pct missing_sec_data have exactly this
                # tax_expense=0/pretax_income=NULL combination in their most-recent-available
                # income statement row.
                effective_tax_rate = 0.0
            elif (
                roic_pretax_income is None
                and roic_tax_expense is not None
                and roic_tax_expense != 0
                and roic_net_income is not None
                and (roic_net_income + roic_tax_expense) > 0
                and symbol in self._get_never_tagged_pretax_income_symbols()
            ):
                # FIX 2026-08-18 (missing factor inputs audit, continued): see
                # _get_never_tagged_pretax_income_symbols - REITs/mortgage trusts
                # (ADC/AAT/ABR-class filers) never tag a distinct pretax_income concept
                # at all (their 10-Ks have no "income before tax" subtotal line), but do
                # report a real, usually small, income_tax_expense most years. The
                # general "derive pretax_income from net_income+tax_expense" approach is
                # already rejected elsewhere in this file (25% deviation vs real reported
                # pretax_income across 50,261 rows, from NCI/discontinued-ops noise) -
                # but that rejection was measured across the WHOLE population including
                # large diversified filers where tax is a material fraction of income.
                # Here the same approximation is scoped narrowly: only fires for filers
                # confirmed to have zero pretax_income concept in 3+ years (so there is no
                # better source to prefer), same fiscal-year net_income (never mixes
                # years - see roic_net_income's fallback-row tracking above), and still
                # passes the same [-0.60, 0.60] plausibility bound as every other branch
                # here. When tax_expense is this small relative to net_income (the common
                # case for this REIT/trust class - live-confirmed ADC ~0.85%, AAT ~1.1%),
                # even a materially wrong pretax base still yields a small implied rate,
                # bounding NOPAT's distortion - unlike using this approximation for a
                # filer with a large tax bill, where the same NCI/discontinued-ops noise
                # could swing the rate by many points.
                candidate_rate = roic_tax_expense / (roic_net_income + roic_tax_expense)
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")

            # Invested Capital = Stockholders' Equity + Total Debt - Cash & Equivalents
            # Use total_debt_ev (from sec_valuations, 81% available) as primary source
            # Fall back to long_term_debt_bs (from balance_sheet, only 22% available) if needed
            # ROIC requires complete balance sheet data, not partial guesses. A prior session
            # added a (total_liabilities - current_liabilities) debt estimate - reverted: that
            # includes non-debt liabilities (AP, accrued expenses, deferred revenue, pensions),
            # so it is not a real "total debt" figure.
            #
            # stockholders_equity/cash_and_equivalents get the same same-year-substitute
            # treatment as the tax triple above, for the same reason (76% cash coverage in the
            # FCF-prioritized row vs a different year that has it).
            roic_stockholders_equity, roic_cash_and_equivalents = stockholders_equity, cash_and_equivalents_bs
            if stockholders_equity is None or cash_and_equivalents_bs is None:
                with DatabaseContext("read") as cur:
                    # FIXED 2026-09-01 (same pattern/fix as gross_profit/interest_coverage/
                    # roic-tax fallbacks above - goal session "we had data but didn't know how
                    # to read it" audit). Missing `data_unavailable IS NOT TRUE` let an
                    # incomplete/unfiled or stale-orphan (see sec_base.py's
                    # stale_fiscal_year_not_confirmed_by_full_sec_refetch) fiscal year's stub
                    # stockholders_equity/cash_and_equivalents get used as real. Live-confirmed
                    # 2,989 symbols where the unfiltered pick comes from a data_unavailable=True
                    # row.
                    # First try: both fields in recent history (3 years)
                    cur.execute(
                        """
                        SELECT stockholders_equity, cash_and_equivalents
                        FROM annual_balance_sheet
                        WHERE symbol = %s AND stockholders_equity IS NOT NULL
                          AND cash_and_equivalents IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_bs_row = cur.fetchone()

                    # If 3-year window fails, search entire history
                    if not fallback_bs_row:
                        cur.execute(
                            """
                            SELECT stockholders_equity, cash_and_equivalents
                            FROM annual_balance_sheet
                            WHERE symbol = %s AND stockholders_equity IS NOT NULL
                              AND cash_and_equivalents IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_bs_row = cur.fetchone()

                if fallback_bs_row:
                    roic_stockholders_equity = self._nan_to_none(
                        safe_float(fallback_bs_row[0], f"{symbol}.stockholders_equity_fallback_year", allow_none=True)
                    )
                    roic_cash_and_equivalents = self._nan_to_none(
                        safe_float(fallback_bs_row[1], f"{symbol}.cash_and_equivalents_fallback_year", allow_none=True)
                    )

            # FIX 2026-08-18 (live: ABCB/Ameris Bancorp, 110 universe symbols): unlike
            # stockholders_equity/cash_and_equivalents just above, long_term_debt_bs never got
            # a same-year-substitute fallback search. Banks often tag deposits/FHLB advances/
            # subordinated debentures under concepts this pipeline doesn't map to
            # "long_term_debt" for the current fiscal year, even though an older 10-K (still
            # within the 3-year lookback) reports a real long_term_debt figure.
            # total_debt_ev has no fiscal-year dimension (sec_valuations is a single
            # latest-snapshot row), so only long_term_debt_bs can be rescued this way - only
            # search when total_debt_ev is also absent (it remains the primary source below).
            roic_long_term_debt = long_term_debt_bs
            if total_debt_ev is None and long_term_debt_bs is None:
                with DatabaseContext("read") as cur:
                    # FIXED 2026-09-01 (same pattern/fix as the fallbacks above - goal session
                    # "we had data but didn't know how to read it" audit). Missing
                    # `data_unavailable IS NOT TRUE` let an incomplete/stale-orphan fiscal
                    # year's stub long_term_debt get used as real. Live-confirmed 1,267 symbols
                    # where the unfiltered pick comes from a data_unavailable=True row.
                    cur.execute(
                        """
                        SELECT long_term_debt
                        FROM annual_balance_sheet
                        WHERE symbol = %s AND long_term_debt IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_debt_row = cur.fetchone()

                    if not fallback_debt_row:
                        cur.execute(
                            """
                            SELECT long_term_debt
                            FROM annual_balance_sheet
                            WHERE symbol = %s AND long_term_debt IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_debt_row = cur.fetchone()

                if fallback_debt_row:
                    roic_long_term_debt = self._nan_to_none(
                        safe_float(fallback_debt_row[0], f"{symbol}.long_term_debt_fallback_year", allow_none=True)
                    )

            invested_capital = None
            debt_for_roic = total_debt_ev if total_debt_ev is not None else roic_long_term_debt

            if (
                roic_stockholders_equity is not None
                and debt_for_roic is not None
                and roic_cash_and_equivalents is not None
            ):
                invested_capital = roic_stockholders_equity + debt_for_roic - roic_cash_and_equivalents
            # FIX 2026-08-18 (goal: find/fix real loader gaps): live-confirmed ALNY (Alnylam
            # Pharmaceuticals, a real, profitable-that-year, fully-SEC-reported biotech) -
            # every roic_pct input (effective_tax_rate=2.9%, operating_income=$501.6M,
            # stockholders_equity, debt, cash all real SEC figures) computed successfully, but
            # invested_capital = equity + debt - cash came out NEGATIVE ($789.2M + $270.6M -
            # $1,657.3M = -$597.5M) because ALNY's large cash pile (built from equity raises,
            # common for well-capitalized biotechs) exceeds equity+debt. This then fell through
            # to the generic "missing_sec_data" below even though nothing was missing - same
            # "real business-state fact, not an absent SEC concept" distinction this file
            # already makes for roic_pct_unprofitable (pretax loss -> "unprofitable_stock").
            # Live sample of 300 universe symbols marked roic_pct missing_sec_data: 92 (~31%)
            # hit this exact negative/zero-invested-capital shape - the single largest
            # component of the whole missing_sec_data bucket for this field.
            roic_pct_negative_invested_capital = invested_capital is not None and invested_capital <= 0
            # FIXED 2026-09-01 (same fix/pattern as no_operating_income_concept above): the
            # effective_tax_rate=0.0 branch above already handles AGNC/ARE/AMH-class REITs'
            # missing tax concept, but roic_operating_income (NOPAT's OTHER input) still comes
            # back None for these same symbols - no operating_income, no pretax_income, no
            # EBIT approximation possible - so roic_pct still fell to "missing_sec_data" via
            # this separate input, not the tax-rate one already fixed. Same structural-not-
            # missing distinction, same already-tested _get_no_tax_concept_symbols() gate.
            no_operating_income_concept_roic = (
                roic_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            if (
                effective_tax_rate is not None
                and roic_operating_income is not None
                and invested_capital is not None
                and invested_capital > 0
            ):
                nopat = roic_operating_income * (1 - effective_tax_rate)
                # CRITICAL FIX 2026-08-09: same near-zero-denominator bound as gross_margin/
                # ebitda_margin/interest_coverage above - invested_capital > 0 only rules out
                # literal zero, not an implausibly tiny-but-positive value that explodes the
                # ratio (live-confirmed: MCK at 1347.77% before this fix).
                computed_roic_pct = (nopat / invested_capital) * 100
                if abs(computed_roic_pct) > 1000:
                    failed_metrics.append("roic_pct")
                    implausible_ratio_metrics.append("roic_pct")
                else:
                    metrics["roic_pct"] = float(computed_roic_pct)
            else:
                failed_metrics.append("roic_pct")

            # ROCE (Return on Capital Employed) ADDED 2026-08-26 (Quality pillar exhaustive-
            # input review, user-directed): EBIT / (Equity + Debt), deliberately NO cash
            # subtraction - unlike roic_pct above, whose cash-netted invested_capital goes
            # negative for well-capitalized, profitable companies (~31% of all roic_pct
            # missing_sec_data cases, e.g. ALNY, see the comment above). Reuses the same
            # production-quality debt_for_roic/roic_stockholders_equity inputs as roic_pct
            # (real sec_valuations.total_debt with a multi-year fallback, not a same-year-only
            # proxy) and roic_operating_income as the EBIT proxy (pretax, classic ROCE
            # convention - not NOPAT). FM-validated: t=2.10 univariate/1.91 multivariate (151
            # months, 2014-2026), and - unlike roic_pct (t=0.45, sign-flips 1.84/-0.79 across a
            # half-split robustness check) - stable across both halves (t=1.50/1.50 exactly).
            # Panel coverage 70.8% vs. roic_pct's 38.9%, directly reflecting the fixed cash-
            # netting failure mode. Replaces roic_score in the composite (see weighted_score).
            capital_employed = (
                roic_stockholders_equity + debt_for_roic
                if roic_stockholders_equity is not None and debt_for_roic is not None
                else None
            )
            roce_pct_negative_capital_employed = capital_employed is not None and capital_employed <= 0
            if roic_operating_income is not None and capital_employed is not None and capital_employed > 0:
                computed_roce_pct = (roic_operating_income / capital_employed) * 100
                if abs(computed_roce_pct) > 1000:
                    failed_metrics.append("roce_pct")
                    implausible_ratio_metrics.append("roce_pct")
                else:
                    metrics["roce_pct"] = float(computed_roce_pct)
            else:
                failed_metrics.append("roce_pct")

            # Debt to Equity: interest-bearing Debt / Equity - see the removed-block comment
            # near total_liabilities/debt_to_assets above for why this replaced the old Total
            # Liabilities / Equity formula. Reuses debt_for_roic/roic_stockholders_equity, same
            # production-quality inputs as ROIC/ROCE above. FM-validated: t=3.12 univariate/
            # 3.29 multivariate (151 months) - the strongest single leverage signal tested,
            # though a half-split check shows it strengthening over time (t=1.50 first half,
            # 2.84 second half) rather than being uniformly strong throughout, and a joint
            # regression against debt_to_assets shows real overlap (corr=0.67) - debt_to_assets
            # was therefore replaced by this, not scored alongside it (see weighted_score).
            if roic_stockholders_equity is not None and debt_for_roic is not None and roic_stockholders_equity != 0:
                computed_debt_to_equity = debt_for_roic / roic_stockholders_equity
                if abs(computed_debt_to_equity) > 1000:
                    failed_metrics.append("debt_to_equity")
                    implausible_ratio_metrics.append("debt_to_equity")
                else:
                    metrics["debt_to_equity"] = float(computed_debt_to_equity)
            else:
                failed_metrics.append("debt_to_equity")

            # FCF to Net Income = Free Cash Flow / Net Income
            if free_cash_flow is not None and net_income is not None and net_income != 0:
                metrics["fcf_to_net_income"] = float(free_cash_flow / net_income)
            else:
                failed_metrics.append("fcf_to_net_income")

            # OCF to Net Income = Operating Cash Flow / Net Income
            if operating_cash_flow is not None and net_income is not None and net_income != 0:
                metrics["ocf_to_net_income"] = float(operating_cash_flow / net_income)
            else:
                failed_metrics.append("ocf_to_net_income")

            # Payout Ratio = Dividends / Net Income (% of earnings paid out)
            # Reason split (live audit of 3965 universe-wide NULLs, all previously labeled the
            # same generic "missing_sec_data"): 385 have real dividends_paid data for the chosen
            # year but net_income <= 0 that year - payout ratio on a loss is not a meaningful
            # percentage, "not applicable" rather than a data gap. Of the rest, ~3215 have NO
            # real dividend_data payment history anywhere (genuine non-payers, same
            # data_unavailable=FALSE filter fixed above for dividend_yield_reason - without it
            # every symbol matches dividend_data's "confirmed no dividend" marker rows too);
            # only ~92 have real dividend history elsewhere but the SEC concept wasn't
            # extracted for this fiscal year - a true data gap.
            # BUG FOUND 2026-08-17 (live-reproduced, GLPI): unlike every other ratio field in this
            # function, payout_ratio had no magnitude guard - a near-zero (but still >0) net_income
            # denominator lets the ratio explode arbitrarily (105,668,646.22% for GLPI), crashing
            # the INSERT with psycopg2.errors.NumericValueOutOfRange since quality_metrics.
            # payout_ratio is NUMERIC(10,2) (max ~1e8). Reuses the same |ratio| <= 1000% sanity
            # bound already applied to margin fields elsewhere in this function (MAX_MARGIN_ABS_PCT,
            # defined later at the trend-calc site since it runs after this block) - a payout ratio
            # in the hundred-thousands of percent is exactly as meaningless as an implausible margin.
            MAX_PAYOUT_RATIO_ABS_PCT = 1000.0  # noqa: N806
            payout_ratio_reason = None
            if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income > 0:
                payout_ratio_pct = (dividends_paid_with_prior_year_fallback / net_income) * 100
                if abs(payout_ratio_pct) <= MAX_PAYOUT_RATIO_ABS_PCT:
                    metrics["payout_ratio"] = float(payout_ratio_pct)
                else:
                    failed_metrics.append("payout_ratio")
                    payout_ratio_reason = "implausible_ratio"
            else:
                failed_metrics.append("payout_ratio")
                if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income <= 0:
                    payout_ratio_reason = "unprofitable_stock"
                else:
                    # FIXED 2026-08-18: same "ever, not recently" gap as dividend_yield_reason
                    # above - a symbol that discontinued its dividend years ago (e.g. ENVA, last
                    # paid 2016) has real history on file but isn't a current data gap. Match the
                    # same 2-year recency window used there.
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT 1 FROM dividend_data
                            WHERE symbol = %s AND data_unavailable = FALSE
                              AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        has_real_dividend_history = cur.fetchone() is not None
                    payout_ratio_reason = (
                        "missing_sec_data" if has_real_dividend_history else "non_dividend_paying_stock"
                    )

            # Absolute cash flow values
            if free_cash_flow is not None and abs(free_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["free_cash_flow"] = float(free_cash_flow)
            else:
                failed_metrics.append("free_cash_flow")

            if operating_cash_flow is not None and abs(operating_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["operating_cash_flow"] = float(operating_cash_flow)
            else:
                failed_metrics.append("operating_cash_flow")

            # Absolute balance sheet values from sec_valuations
            if total_debt_ev is not None and abs(total_debt_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_debt"] = float(total_debt_ev)
            else:
                failed_metrics.append("total_debt")

            if total_cash_ev is not None and abs(total_cash_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_cash"] = float(total_cash_ev)
            else:
                failed_metrics.append("total_cash")

            if ebitda_ev is not None and abs(ebitda_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["ebitda"] = float(ebitda_ev)
            else:
                failed_metrics.append("ebitda")

            # Cash per Share = Total Cash / Shares Outstanding
            cash_per_share_shares_missing = False
            if total_cash_ev is not None and shares_outstanding is not None and shares_outstanding > 0:
                metrics["cash_per_share"] = float(total_cash_ev / shares_outstanding)
            else:
                failed_metrics.append("cash_per_share")
                # FIXED 2026-08-19 (goal: "no SEC data" audit continuation): shares_outstanding
                # here is sv.shares_outstanding (quality_row[11], see fetch_incremental's SELECT)
                # - the exact same sec_valuations column already given its own specific
                # "shares_outstanding_unavailable" reason (Ownership data unresolved category)
                # everywhere else in this codebase. Live-confirmed 771 of 860 universe
                # cash_per_share "missing_sec_data" rows are this exact case - a real,
                # deterministic cause one column away, not a generic SEC extraction gap.
                cash_per_share_shares_missing = shares_outstanding is None or shares_outstanding <= 0

            # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100
            # BUG FOUND 2026-08-16: unlike every sibling *_growth_yoy field in this function
            # (net_income_growth_yoy, operating_income_growth_yoy, fcf_growth_yoy,
            # ocf_growth_yoy, asset_growth_yoy - see the MAX_TREND_PERCENTAGE_POINTS guard and
            # its ANET FY2024 example below), this field and revenue_growth_yoy were missing
            # the same overflow guard. Live-confirmed: GLPI's quality_metrics INSERT failed
            # with NumericValueOutOfRange on this exact column class - a real but near-zero
            # prior-year EPS/revenue base (same root cause as the already-documented ANET case)
            # produces a percentage that overflows earnings_growth_yoy/revenue_growth_yoy's
            # NUMERIC(10,2) (max magnitude 99,999,999.99) and crashed the INSERT for the whole
            # row, losing every other metric in it too. Same fix as the sibling fields: cap and
            # mark unavailable rather than let an unbounded ratio reach the DB.
            # FIXED 2026-08-19 (goal: "no SEC data" audit): the bound-rejected branch used to
            # append to failed_metrics only, collapsing into the same hardcoded "missing_sec_data"
            # reason as the "no prior-year data at all" case below - unlike every one of the 9
            # sibling *_growth_yoy/*_trend fields (net_income_growth_yoy, fcf_growth_yoy, etc.),
            # which already distinguish a real value rejected as implausible ("implausible_ratio")
            # from a genuinely absent prior-year base ("insufficient_prior_year_data") - see the
            # blanket loop below this block for those 9 fields. Live-confirmed 639 universe
            # revenue_growth_yoy + 588 earnings_growth_yoy "missing_sec_data" rows were never split
            # this way, reading as an unexplained SEC data gap even for symbols with a real,
            # computed-but-rejected ratio on file. Also appended to implausible_ratio_metrics (not
            # instead of failed_metrics, which line ~3375's summary log still relies on for both
            # cases).
            if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
                try:
                    yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["earnings_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("earnings_growth_yoy")
                        implausible_ratio_metrics.append("earnings_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("earnings_growth_yoy")
            else:
                failed_metrics.append("earnings_growth_yoy")

            # Revenue Growth YoY = (Current Revenue - Prior Year Revenue) / Prior Year Revenue * 100
            if revenue is not None and prior_year_revenue is not None and prior_year_revenue != 0:
                try:
                    yoy_growth = ((revenue - prior_year_revenue) / abs(prior_year_revenue)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["revenue_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("revenue_growth_yoy")
                        implausible_ratio_metrics.append("revenue_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("revenue_growth_yoy")
            else:
                failed_metrics.append("revenue_growth_yoy")

            # TREND FIELDS (new fields for enhanced scoring)
            # Net Income Growth YoY - only if actual prior net income available
            # Bounded by MAX_TREND_PERCENTAGE_POINTS (same guard as roe_trend below): a prior-
            # year base that's real but near-zero (live-confirmed ANET FY2024 net_income of
            # $2,852 against a real ~$1B current year - a genuine SEC data-scale artifact, not
            # a bug in this loader) produces a growth ratio in the hundreds of thousands of
            # percent, which overflows this column's NUMERIC(10,4) (max magnitude 999,999.9999)
            # and previously crashed the INSERT for the entire quality_metrics row - losing
            # every other valid metric for the symbol, not just this one field.
            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:
                if (net_income > 0 and prior_year_net_income < 0) or (net_income < 0 and prior_year_net_income > 0):
                    # Profit<->loss sign flip - growth % is mathematically undefined here,
                    # same treatment _cagr()/_compute_period_growth already give this exact
                    # condition (root cause of CRWD's -966% net_income_growth_yoy despite
                    # genuinely strong ~22% revenue growth).
                    sign_change_yoy_metrics.append("net_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_net_income) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("net_income_growth_yoy")
                else:
                    try:
                        ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100
                        if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))
                        else:
                            implausible_ratio_metrics.append("net_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        logger.warning(
                            f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "
                            f"Metric marked data_unavailable."
                        )

            # Operating Income Growth YoY - uses the same EBIT-approximation fallback as
            # operating_income_for_margin (current year) and prior_year_operating_income_for_trend
            # (prior year) so filers that never tag OperatingIncomeLoss aren't blocked here too.
            if (
                operating_income_for_margin is not None
                and prior_year_operating_income_for_trend is not None
                and prior_year_operating_income_for_trend != 0
            ):
                if (operating_income_for_margin > 0 and prior_year_operating_income_for_trend < 0) or (
                    operating_income_for_margin < 0 and prior_year_operating_income_for_trend > 0
                ):
                    sign_change_yoy_metrics.append("operating_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_income_for_trend) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("operating_income_growth_yoy")
                else:
                    try:
                        oi_growth = (
                            (operating_income_for_margin - prior_year_operating_income_for_trend)
                            / abs(prior_year_operating_income_for_trend)
                        ) * 100
                        if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))
                        else:
                            implausible_ratio_metrics.append("operating_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Margin Trends (current - prior year) - only compute when actual prior data available
            #
            # CRITICAL FIX 2026-08-10: the trend-level MAX_TREND_PERCENTAGE_POINTS check below
            # only bounds the DELTA, not the two margins that produce it - a near-zero-revenue
            # year (the same root cause already bounded for the base gross_margin/operating_margin/
            # net_margin fields above at |ratio| > 1000) can put curr_gm or prior_gm individually
            # in the tens of thousands of percent while their difference still lands under the
            # 100,000 trend threshold, so it was never caught. Live-confirmed: quality_metrics/
            # growth_metrics operating_margin_trend up to 96,215pp / 191,646pp in the DB. Apply the
            # same |ratio| <= 1000 bound used for the base margin fields to each side of the
            # subtraction first - a trend computed from two implausible margins is itself
            # meaningless, not just its difference.
            MAX_MARGIN_ABS_PCT = 1000.0  # noqa: N806
            if revenue is not None and prior_year_revenue is not None and revenue > 0 and prior_year_revenue > 0:
                # Gross Margin Trend - prefers each year's directly-reported gross_profit (same
                # source the base gross_margin metric above already falls back to), only deriving
                # from revenue - cost_of_revenue when a filer doesn't tag GrossProfit at all. FIXED
                # 2026-08-18: this previously required cost_of_revenue/prior_year_cost_of_revenue
                # unconditionally, so filers that report GrossProfit directly but never tag a
                # separate CostOfRevenue concept (e.g. ENVA: gross_profit present every fiscal year
                # 2021-2025, cost_of_revenue NULL every year) fell through to the generic
                # "insufficient_prior_year_data" label even though the trend was fully computable
                # from data already on hand - not the reit_special_entity structural-gap case
                # (no_gross_profit_concept is False here) and not an implausible-ratio rejection
                # either, just a real gap in what this calculation tried.
                curr_gross_profit = (
                    gross_profit_direct
                    if gross_profit_direct is not None
                    else (revenue - cost_of_revenue if cost_of_revenue is not None else None)
                )
                prior_gross_profit = (
                    prior_year_gross_profit
                    if prior_year_gross_profit is not None
                    else (
                        prior_year_revenue - prior_year_cost_of_revenue
                        if prior_year_cost_of_revenue is not None
                        else None
                    )
                )
                if curr_gross_profit is not None and prior_gross_profit is not None:
                    curr_gm = (curr_gross_profit / revenue) * 100 if revenue > 0 else None
                    prior_gm = (prior_gross_profit / prior_year_revenue) * 100 if prior_year_revenue > 0 else None
                    if (
                        curr_gm is not None
                        and prior_gm is not None
                        and abs(curr_gm) <= MAX_MARGIN_ABS_PCT
                        and abs(prior_gm) <= MAX_MARGIN_ABS_PCT
                    ):
                        try:
                            gm_trend = round(curr_gm - prior_gm, 2)
                            if abs(gm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["gross_margin_trend"] = float(gm_trend)
                            else:
                                implausible_ratio_metrics.append("gross_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    elif curr_gm is not None and prior_gm is not None:
                        # Inputs existed but one/both margins blew past MAX_MARGIN_ABS_PCT
                        # (e.g. cost_of_revenue exceeding revenue) - a real, if garbage,
                        # ratio that was deliberately excluded, not a missing-data gap.
                        implausible_ratio_metrics.append("gross_margin_trend")

                # Operating Margin Trend - uses the same EBIT-approximation fallback as
                # operating_income_growth_yoy above (see prior_year_operating_income_for_trend).
                if (
                    operating_income_for_margin is not None
                    and prior_year_operating_income_for_trend is not None
                    and prior_year_revenue > 0
                ):
                    curr_om = (operating_income_for_margin / revenue) * 100
                    prior_om = (prior_year_operating_income_for_trend / prior_year_revenue) * 100
                    if abs(curr_om) <= MAX_MARGIN_ABS_PCT and abs(prior_om) <= MAX_MARGIN_ABS_PCT:
                        try:
                            om_trend = round(curr_om - prior_om, 2)
                            if abs(om_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["operating_margin_trend"] = float(om_trend)
                            else:
                                implausible_ratio_metrics.append("operating_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("operating_margin_trend")

                # Net Margin Trend - only if actual prior net income available
                if net_income is not None and prior_year_net_income is not None and prior_year_revenue > 0:
                    curr_nm = (net_income / revenue) * 100
                    prior_nm = (prior_year_net_income / prior_year_revenue) * 100
                    if abs(curr_nm) <= MAX_MARGIN_ABS_PCT and abs(prior_nm) <= MAX_MARGIN_ABS_PCT:
                        try:
                            nm_trend = round(curr_nm - prior_nm, 2)
                            if abs(nm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["net_margin_trend"] = float(nm_trend)
                            else:
                                implausible_ratio_metrics.append("net_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("net_margin_trend")

            # Sustainable Growth Rate = ROE * Retention Ratio - only with real data
            # FIXED 2026-08-04: dividends_paid is None (not 0) for genuine non-dividend-payers,
            # since SEC XBRL simply omits the PaymentsOfDividends concept when nothing was paid
            # - the same "confirmed non-payer vs missing data" ambiguity already resolved above
            # for dividend_yield/payout_ratio via the dividend_data has_real_dividend_history
            # marker. Without this, SGR was unconditionally unavailable for every non-payer even
            # though the formula is fully computable for them (retention_ratio = 1.0, all
            # earnings retained). Live-verified: 3212 of 3423 universe-wide dividends_paid-
            # blocked SGR NULLs are confirmed non-payers via that same marker.
            sgr_reason = None
            # FIXED 2026-09-02: same prior-year fallback as payout_ratio above - reuses
            # dividends_paid_with_prior_year_fallback instead of the raw current-year value so
            # a confirmed-recent payer's current-year extraction gap doesn't fall through to
            # the has_real_dividend_history detour below and get stuck on "missing_sec_data"
            # when a perfectly good one-year-old figure is already sitting in quality_row.
            sgr_dividends_paid = dividends_paid_with_prior_year_fallback
            if (
                sgr_dividends_paid is None
                and stockholders_equity is not None
                and net_income is not None
                and stockholders_equity > 0
            ):
                # FIXED 2026-08-18: same "ever, not recently" gap as dividend_yield_reason/
                # payout_ratio_reason above - a symbol that discontinued its dividend years ago
                # (e.g. ENVA, last paid 2016) has real history on file but isn't a current data
                # gap. Match the same 2-year recency window used there.
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_real_dividend_history = cur.fetchone() is not None
                if has_real_dividend_history:
                    sgr_reason = "missing_sec_data"
                else:
                    sgr_dividends_paid = 0.0

            if stockholders_equity is not None and net_income is not None and stockholders_equity > 0:
                if sgr_dividends_paid is not None and net_income != 0:
                    # Actual retention ratio = (earnings - dividends) / earnings
                    roe_pct = net_income / stockholders_equity
                    retention_ratio = 1.0 - (sgr_dividends_paid / abs(net_income)) if net_income != 0 else 0.0
                    try:
                        sgr = round(roe_pct * retention_ratio * 100, 2)
                        # Tightened 2026-08-28 to MAX_PLAUSIBLE_GROWTH_PCT (see that constant's
                        # docstring) - a near-zero stockholders_equity base blows up roe_pct
                        # the same way a near-zero prior-year base blows up those ratios.
                        if abs(sgr) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["sustainable_growth_rate"] = float(sgr)
                        elif sgr_reason is None:
                            # FIXED 2026-08-19 (goal: "no SEC data" audit continuation): a real
                            # SGR was computed here and deliberately rejected as implausible (a
                            # near-zero stockholders_equity base blowing up roe_pct, same root
                            # cause as the growth_yoy MAX_TREND_PERCENTAGE_POINTS fix above) -
                            # not a missing SEC concept. Same "implausible_ratio" distinction
                            # every other bound-rejected field in this loader already makes.
                            sgr_reason = "implausible_ratio"
                            implausible_ratio_metrics.append("sustainable_growth_rate")
                    except (ValueError, TypeError, ZeroDivisionError):
                        if sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                elif sgr_reason is None:
                    sgr_reason = "missing_sec_data"
            elif sgr_reason is None:
                # FIXED 2026-08-22 (goal session - coverage-bucket root-cause audit): this
                # unconditionally labeled the gate above's else-branch "missing_sec_data", but
                # that branch also fires when stockholders_equity is present and real, just <= 0
                # (debt-funded buybacks/distributions - same real, well-known condition as the
                # roe_trend fix above, e.g. YUM/IRM/COKE). SGR's "growth financeable from retained
                # earnings relative to the equity base" interpretation doesn't translate cleanly
                # to a negative base, so - unlike roe_trend - this deliberately still does NOT
                # compute a value here, but the label must say why: real data, not missing data.
                # Reuses "negative_book_value" (already used for pb_ratio just above in this same
                # file, same stockholders_equity<=0 condition, already correctly bucketed under
                # "Legitimate / not applicable" in scores.py) rather than inventing a new string.
                if stockholders_equity is not None and stockholders_equity <= 0:
                    sgr_reason = "negative_book_value"
                else:
                    sgr_reason = "missing_sec_data"

            # ROE Trend = Current ROE - Prior ROE (now can compute with prior-year equity)
            # Same per-side MAX_MARGIN_ABS_PCT bound as the margin trends above - a near-zero
            # prior-year equity base (the ORKA 8.3M% case this function's docstring already
            # describes) must be caught before the subtraction, not just via the looser
            # trend-level MAX_TREND_PERCENTAGE_POINTS check on the delta.
            #
            # FIXED 2026-08-22 (goal session - coverage-bucket root-cause audit): this required
            # stockholders_equity > 0 on BOTH years, unlike the base `roe` field just above (this
            # function's own precedent) which only requires `!= 0` plus the same
            # MAX_MARGIN_ABS_PCT bound. Real, well-known large-caps with real, computable
            # multi-year history were silently excluded and mislabeled "insufficient_prior_year_
            # data" purely because they carry negative equity (debt-funded buybacks/distributions,
            # not a data gap) - live-confirmed YUM (negative every year 2021-2026), IRM (negative
            # 2024+), COKE (negative 2025-2026), each with 5-6 years of real net_income/equity on
            # file. 388 of 798 (49%) of the current "insufficient_prior_year_data" roe_trend
            # population has real, present-but-negative equity data, not missing data. Relaxed to
            # match the base roe field's `!= 0` bound - the MAX_MARGIN_ABS_PCT check below already
            # rejects genuine near-zero-equity garbage the same way it does for the base field.
            if (
                stockholders_equity is not None
                and net_income is not None
                and stockholders_equity != 0
                and prior_year_stockholders_equity is not None
                and prior_year_net_income is not None
                and prior_year_stockholders_equity != 0
            ):
                curr_roe = (net_income / stockholders_equity) * 100
                prior_roe = (prior_year_net_income / prior_year_stockholders_equity) * 100
                if abs(curr_roe) <= MAX_MARGIN_ABS_PCT and abs(prior_roe) <= MAX_MARGIN_ABS_PCT:
                    try:
                        roe_trend = round(curr_roe - prior_roe, 2)
                        if abs(roe_trend) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["roe_trend"] = float(roe_trend)
                        else:
                            implausible_ratio_metrics.append("roe_trend")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                else:
                    implausible_ratio_metrics.append("roe_trend")

            # FCF Growth YoY - only if actual prior FCF available
            # Same MAX_TREND_PERCENTAGE_POINTS overflow guard as net_income_growth_yoy above -
            # these three share the identical NUMERIC(10,4) column and tiny-prior-year-base risk.
            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:
                if (free_cash_flow > 0 and prior_year_free_cash_flow < 0) or (
                    free_cash_flow < 0 and prior_year_free_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("fcf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_free_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("fcf_growth_yoy")
                else:
                    try:
                        fcf_growth = (
                            (free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)
                        ) * 100
                        if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("fcf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # OCF Growth YoY - only if actual prior OCF available
            if (
                operating_cash_flow is not None
                and prior_year_operating_cash_flow is not None
                and prior_year_operating_cash_flow != 0
            ):
                if (operating_cash_flow > 0 and prior_year_operating_cash_flow < 0) or (
                    operating_cash_flow < 0 and prior_year_operating_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("ocf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("ocf_growth_yoy")
                else:
                    try:
                        ocf_growth = (
                            (operating_cash_flow - prior_year_operating_cash_flow) / abs(prior_year_operating_cash_flow)
                        ) * 100
                        if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("ocf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Asset Growth YoY - now can compute with prior-year total assets
            if total_assets is not None and prior_year_total_assets is not None and prior_year_total_assets != 0:
                try:
                    asset_growth = ((total_assets - prior_year_total_assets) / abs(prior_year_total_assets)) * 100
                    if abs(asset_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["asset_growth_yoy"] = float(round(asset_growth, 2))
                    else:
                        implausible_ratio_metrics.append("asset_growth_yoy")
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # FIX 2026-08-10: the 9 trend/growth fields just above (net_income_growth_yoy,
            # operating_income_growth_yoy, gross_margin_trend, operating_margin_trend,
            # net_margin_trend, roe_trend, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy) had
            # no "else" branch recording WHY the value stayed None - every genuine per-stock gap
            # (missing prior-year fiscal data, zero denominator, MAX_TREND_PERCENTAGE_POINTS
            # bound rejecting an implausible ratio) showed up as an unexplained NULL with no
            # _unavailable_reason, unlike sustainable_growth_rate/quarterly_growth_momentum below
            # which already do this. Live-confirmed: growth_metrics.operating_margin_trend alone
            # had 324 NULL rows with no reason set (of 2395 total NULLs). These reasons also
            # mirror into growth_metrics via the _SHARED_TREND_FIELDS copy below.
            #
            # FIXED 2026-08-18 ("no SEC data"/loader-failure audit goal): this loop used to
            # blanket-assign "insufficient_prior_year_data" to any still-None field, collapsing
            # two other distinct causes into a misleading "the loader is missing data" label:
            # (1) gross_margin_trend for insurers/banks/REITs that structurally never report
            # cost_of_revenue/gross_profit at all (no_gross_profit_concept, same root cause
            # already correctly labeled "reit_special_entity" for the base gross_margin field
            # above) - live-confirmed 1397 of 2183 gross_margin_trend "insufficient_prior_year_
            # data" rows (64%) are this case, e.g. HIG; (2) any of the 9 fields whose inputs
            # WERE present but got rejected by the MAX_MARGIN_ABS_PCT/MAX_TREND_PERCENTAGE_POINTS
            # bound (implausible_ratio_metrics, appended in each block above) - a real value
            # deliberately excluded as garbage, not a missing one (live-confirmed e.g. RDZN,
            # where cost_of_revenue exceeds revenue and blows the margin bound). Both are
            # legitimate-gap or garbage-data cases, not evidence of a loader fetch failure -
            # only fall through to "insufficient_prior_year_data" once both are ruled out.
            for _trend_field in (
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
            ):
                if metrics.get(_trend_field) is None:
                    if _trend_field == "gross_margin_trend" and no_gross_profit_concept:
                        metrics[f"{_trend_field}_unavailable_reason"] = "reit_special_entity"
                    elif _trend_field in sign_change_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"
                    elif _trend_field in immaterial_base_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "immaterial_prior_year_base"
                    elif _trend_field in implausible_ratio_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "implausible_ratio"
                    else:
                        metrics[f"{_trend_field}_unavailable_reason"] = "insufficient_prior_year_data"

            # Quarterly Metrics (Session 74+)
            quarterly_metrics = self._compute_quarterly_metrics(symbol)
            metrics.update(quarterly_metrics)

            # Initialize missing trend fields as None
            for field in [
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "sustainable_growth_rate",
                "quarterly_growth_momentum",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
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
            ]:
                if field not in metrics:
                    metrics[field] = None

            # sustainable_growth_rate reason: unlike the 9 trend fields above (handled by the
            # blanket loop before _compute_quarterly_metrics()), it uses NO prior-year data at
            # all (see its own computation above), so it gets its own explicit sgr_reason
            # instead of "insufficient_prior_year_data".
            if metrics.get("sustainable_growth_rate") is None:
                metrics["sustainable_growth_rate_unavailable_reason"] = sgr_reason or "missing_sec_data"

            # Quarterly-derived fields (consecutive_positive_quarters, quarterly_growth_momentum,
            # earnings_growth_4q_avg, eps_growth_stability, earnings_surprise_avg,
            # earnings_beat_rate) are merged in from _compute_quarterly_metrics() above, which
            # sets its own specific reason when the value is None. The generic
            # "insufficient_quarterly_data"/"no_analyst_estimates" fallback for these fields
            # lives further below and only fires if that specific reason wasn't already set.

            # Mark unavailable if all metrics are None
            if all(
                metrics[k] is None
                for k in [
                    "roe",
                    "roa",
                    "operating_margin",
                    "net_margin",
                    "debt_to_equity",
                    "debt_to_assets",
                    "current_ratio",
                ]
            ):
                return self._unavailable_marker("quality_metrics", symbol)

            # Compute composite quality_score from available metrics
            # Score is average of available metrics (0-100 scale)
            # debt_to_assets is "lower is better" so it's converted to a comparable
            # higher-is-better score before joining the same clamp-and-average as the
            # raw percentage metrics below (100 - debt_to_assets%, e.g. 30% debt -> 70).
            #
            # SIGN QUESTION - re-audited 2026-08-25 (goal: full scoring-architecture audit),
            # NOT flipped: algo/research/fama_macbeth_quality_factors.py found debt_to_assets
            # POSITIVELY signed vs forward return (univariate t=2.28, multivariate t=2.19,
            # 60mo pooled) - higher leverage associated with HIGHER forward return, opposite
            # this "low debt is good" inversion. A decile sort ruled out a linear-regression
            # artifact (deciles 0-6, the well-populated low-to-moderate-leverage range, rise
            # roughly monotonically from 0.70%/mo to 1.04%/mo - not a U-shape). Genuinely
            # unresolved literature tension, not miscalibration: Modigliani-Miller (more debt
            # mechanically raises equity beta and expected return - textbook, undisputed) vs.
            # the documented distress-risk anomaly (Campbell/Hilscher/Szilagyi 2008, JoF -
            # distressed/high-leverage firms empirically underperform). Additional reasoning
            # this pass, still not dispositive enough to flip a live-money sign: the monotonic
            # rise spans deciles 0-6 (low-to-moderate leverage, not the sparse high-leverage
            # tail where genuine bankruptcy/default risk would concentrate per Campbell et
            # al.'s own methodology, which uses a real default-probability measure, not raw
            # debt_to_assets) - that shape reads more like MM's smooth leverage-beta
            # relationship than a distress cliff, but this data was sorted on debt_to_assets
            # itself, not an independent distress/default-risk proxy, so it can't cleanly
            # separate "healthy firm using leverage for growth" from "firm approaching
            # distress" - the two stories this tension is actually about. Needs a real
            # distress-risk proxy (e.g. Altman Z-score, interest-coverage-based) to resolve
            # properly, not more debt_to_assets-only tests. Left unchanged pending that.
            # debt_to_assets_score REMOVED 2026-08-26 (Quality pillar exhaustive-input review) -
            # replaced by debt_to_equity_score in the composite (see that field's own comment,
            # near roic_pct/roce_pct below, for the correlation/redundancy evidence). metrics
            # ["debt_to_assets"] itself (computed above) is still persisted/displayed.
            # Interest coverage score curve REMOVED 2026-08-27 (dead-code cleanup, ON CONFLICT
            # sweep pass): interest_coverage_score was computed here but never consumed after
            # interest_coverage was removed from quality_components (isolated FM re-test,
            # t=0.63/-0.12/0.87, confirmed dead - see quality_components' own comment below).
            # metrics["interest_coverage"] itself (the raw value) is computed independently
            # above and still persisted/displayed - unaffected by removing this dead score
            # curve.

            # FIXED 2026-08-26 (goal: root-cause the "why is quality_score/composite_score so
            # low that min_composite_score=60 rejects 87% of the universe" question - found via
            # direct distribution query: quality_score median=18.9/mean=21.1 across 5,124 scored
            # symbols, and even AAPL/MSFT/JNJ/KO (unambiguously elite, high-margin, high-ROE
            # businesses) only scored 38.8-51.8/100 pre-fix). Root cause: roe/roa/operating_margin/
            # net_margin were fed into quality_components AS RAW PERCENTAGE NUMBERS
            # (e.g. AAPL operating_margin=31.97 -> clamped straight to 31.97 "points"), while
            # debt_to_assets_score/interest_coverage_score (the only two components that were
            # already properly rescaled) required 100% margins to hit 100 - a threshold no real
            # business reaches. Result: quality_score was structurally compressed toward ~20-50
            # for every company regardless of actual quality, silently defeating the 0-100 scale
            # and the min_composite_score=60 floor's intended selectivity (13.4% of the universe
            # cleared it, and only because debt_to_assets_score/interest_coverage_score dragged
            # the average up almost single-handedly). Rescaled the same 4 raw-percentage inputs
            # onto domain-informed curves, matching the pattern interest_coverage_score/PE/PB
            # scoring already use elsewhere in this codebase (not a percentile-rank redesign -
            # this fixes the SCALE of an already-validated signal, not the signal itself; the
            # underlying roe/roa/operating_margin/net_margin values feeding
            # fama_macbeth_quality_factors.py are untouched, only how they map to 0-100 points
            # here). Verified against AAPL/MSFT/JNJ/KO: quality_score moves from 51.8/48.9/41.9/
            # 38.8 (implausibly middling for these companies) to 86.0/91.8/88.5/84.5
            # (correctly near the top of the scale). Thresholds are hand-set (same rigor as
            # interest_coverage_score's <1.5x/1.5-3x/3-10x/10x+ tiers), not FM-backtested - this
            # is a calibration/scale fix, not a new empirical claim, so it doesn't carry the same
            # validation bar as a reweight or a new factor would.
            def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
                """breakpoints: [(x0,y0), (x1,y1), ...] increasing x; value<x0 -> 0-ramp to y0,
                value>=last x -> last y. Piecewise-linear between points."""
                if value < 0:
                    return 0.0
                if value < breakpoints[0][0]:
                    x1, y1 = breakpoints[0]
                    return (value / x1) * y1 if x1 > 0 else y1
                for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
                    if value < x1:
                        return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
                return breakpoints[-1][1]

            roe_score = (
                _margin_curve(metrics["roe"], [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
                if metrics["roe"] is not None
                else None
            )
            roa_score = (
                _margin_curve(metrics["roa"], [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
                if metrics["roa"] is not None
                else None
            )
            # operating_margin_score/net_margin_score REMOVED 2026-08-26 (see literature-audit
            # comment below) - operating_margin and net_margin are still fetched/stored/displayed
            # (metrics["operating_margin"]/["net_margin"]) for reference, but no longer feed
            # quality_score at all - not through the base composite, and not through
            # `_enhance_quality_score`, which was itself removed the same day (see
            # loaders/load_stock_scores.py's `_score_quality` docstring). Confirmed via a
            # dedicated interaction check that neither carries independent signal once ROA is
            # controlled for (see quality_operating_net_margin_no_independent_signal_over_roa_
            # 20260826 in MEMORY.md) - not a stale TODO, a closed finding.

            # REPLACED 2026-08-26 (Quality pillar literature audit - Novy-Marx 2013, Fama-French
            # 2015 RMW, Sloan 1996, QMJ 2013, Bradshaw/Richardson/Sloan 2006). The 2026-08-26
            # cluster-weight fix above (see git history) correctly resolved the operating_margin/
            # net_margin and roe/debt_to_assets redundancy, but a literature review the same day
            # found the CLUSTERING WAS PAIRING THE WRONG FIELDS: operating_margin and net_margin
            # are both profit/REVENUE ratios (r=0.91, genuinely redundant), but roe/debt_to_assets
            # (r=0.82) is a DIFFERENT, DuPont-mechanical overlap the literature explicitly treats
            # as fine to keep (ROE, ROA - related via leverage, not duplicates, standard to use
            # both). The REAL redundancy the literature flags is one denominator-sharing pair:
            # ROE (NI/BookEquity) vs Fama-French's Operating Profitability (RMW: (Rev-COGS-SGA-
            # Interest)/BookEquity, SAME denominator) - and a second: ROA (NI/Assets) vs Novy-
            # Marx's Gross Profitability ((Rev-COGS)/Assets, SAME denominator). Also found:
            # Cash-flow ROA (OCF/Assets) is not independent info once ROA and Accruals Ratio
            # ((NI-OCF)/Assets, Sloan 1996) are both present - it's their exact linear difference,
            # not a third data point. See algo/research/fama_macbeth_quality_factors.py's
            # EXTENDED_CANDIDATE_COLS section for the point-in-time evidence this restructuring
            # is based on (both 1mo and 12mo horizons; Net Share Issuance dropped entirely as
            # wrong-signed at both, same "exclude a confirmed wrong-signed component" precedent
            # as signal_quality_score_volume_confirmation_excluded_20260826).
            #
            # No separate SG&A field exists in this pipeline - operating_income (GAAP, already
            # nets out COGS+SG&A) minus interest_expense is the available proxy for FF's
            # (Rev-COGS-SGA-Interest) construction.
            # operating_profitability_score/roic_score/accruals_score REMOVED 2026-08-26
            # (Quality pillar exhaustive-input review, user-directed rebuild) - failed to clear
            # this repo's own |t|>2 bar in the 2026-08-26 re-check (operating_profitability
            # t=-0.55, accruals_ratio t=-1.85) or were replaced by a more robust alternative
            # (roic_score -> roce_score, see below). gross_profitability_score and
            # margin_volatility_score were also removed the same day (t=1.02/t=-1.28-1.51 in
            # that same re-check) but have SINCE been re-added - see each field's own comment
            # below for why. The raw values (operating_profitability, accruals_ratio, roic_pct)
            # are still computed and persisted for display - only their scoring curves and
            # composite weight are removed. See weighted_score below for the full final
            # composite and the validation behind each surviving component.
            # FIXED 2026-08-30 (goal: full-data audit): required raw operating_income, unlike
            # operating_margin/operating_margin_trend which already fall back to the EBIT
            # approximation (operating_income_for_margin = operating_income, else pretax_income
            # + interest_expense) for 40-F-style filers that tag pretax_income/interest_expense
            # every year but never tag OperatingIncomeLoss at all - same root cause documented
            # above operating_income_for_margin's own definition. 866/1473 (59%)
            # missing_sec_data symbols live-confirmed with pretax_income present the same
            # fiscal year operating_income is null.
            # FIXED 2026-08-30 (goal: full-data audit, live sanity-check pass): unlike every
            # sibling ratio in this file (gross_profitability/fcf_margin/roic_pct/roce_pct/
            # interest_coverage/etc, all guarded at the same |ratio|>1000 threshold right
            # above/below this block), operating_profitability had NO implausible-ratio bound -
            # live-caught min=-93,407.89%/max=16,821.79% already on file (a near-zero
            # stockholders_equity base blowing up the ratio, the identical failure mode already
            # fixed for gross_profitability's total_assets denominator and fcf_margin's revenue
            # denominator). Guarded the same way: reject to implausible_ratio rather than persist
            # a value with 2+ extra orders of magnitude past any real percentage.
            # FIXED 2026-09-02 (goal: "missing SEC/XBRL data" root-cause audit): a negative or
            # zero stockholders_equity denominator (real, common for large mature buyback-heavy
            # filers - live-confirmed AAL/ABBV, both with genuine multi-year negative book
            # equity on file) made this ratio mathematically undefined and fell through to the
            # generic "missing_sec_data" below, exactly the same "real business-state fact, not
            # an absent SEC concept" case pb_ratio/roic_pct/roce_pct already carve out via
            # negative_book_value/negative_invested_capital/negative_capital_employed. Live
            # sample of the 583 universe symbols marked operating_profitability missing_sec_data:
            # 325 (56%) hit this exact negative/zero-equity shape - the single largest component
            # of this field's missing_sec_data bucket, and (via the heavy cross-factor overlap
            # documented in MEMORY.md) a meaningful slice of the whole "Missing SEC/XBRL data"
            # dashboard total. Reuses "negative_book_value" (already used for pb_ratio/
            # sustainable_growth_rate elsewhere in this file) rather than inventing a new string.
            operating_profitability_negative_equity = stockholders_equity is not None and stockholders_equity <= 0
            operating_profitability = None
            if operating_income_for_margin is not None and stockholders_equity is not None and stockholders_equity > 0:
                computed_operating_profitability = (
                    (operating_income_for_margin - (interest_expense or 0.0)) / stockholders_equity * 100.0
                )
                if abs(computed_operating_profitability) > 1000:
                    failed_metrics.append("operating_profitability")
                    implausible_ratio_metrics.append("operating_profitability")
                else:
                    operating_profitability = float(computed_operating_profitability)
            # RE-ADDED TO SCORING 2026-08-27 (goal: recover components wrongly killed by a
            # joint-dropna sample-bias bug found this pass - see MEMORY.md for the audit trail).
            # The 2026-08-26 removal above cited t=1.02 as the reason gross_profitability
            # failed this repo's |t|>2 bar - but that number came from a JOINT dropna across 7
            # unrelated candidate columns at once (algo/research/fama_macbeth_quality_factors.py's
            # EXTENDED_CANDIDATE_COLS), shrinking the effective sample and skewing it toward
            # large/complete-filer firms, the same bug that hid margin_volatility_3y's real
            # signal. Isolated (own dropna scope) re-test: t=3.25 full-sample/3.93 first-half
            # (pre-2020-06)/1.11 second-half - strong, sign-consistent, decaying (not flipping)
            # in the recent era, same McLean-Pontiff decay class already accepted for
            # asset_growth_yoy/rsi_14. Novy-Marx (2013, JFE) "gross profitability" - a firm
            # that converts revenue to gross profit efficiently relative to its asset base is
            # a genuine quality signal independent of the margin-based ratios already scored
            # here. FIXED same pass: unlike every sibling ratio in this file, this computation
            # had no implausible-ratio bound - live-caught max=132,599.68%/min=-32,817.74%
            # (near-zero-total_assets artifacts, 4 of 2936 rows), same recurring bug class as
            # fcf_margin/margin_volatility/asset_turnover - now guarded the same way.
            # FIXED 2026-08-30 (goal: full-data audit): this required cost_of_revenue
            # unconditionally instead of preferring the directly-reported gross_profit like
            # gross_margin/gross_margin_trend already do (same source, same fiscal year - both
            # come from the single anchor query row, ais.gross_profit alongside abs.total_assets).
            # 331 symbols live-confirmed with a real, same-year gross_profit but no separate
            # cost_of_revenue tag (filers that report GrossProfit directly without breaking out
            # COGS) were falling into missing_sec_data even though the Novy-Marx ratio was fully
            # computable from data already on hand.
            # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
            # this still only checked the CURRENT anchor fiscal year, unlike gross_profit_used
            # right above (this method's gross_margin numerator) which already falls back
            # through a 3-year window and then full history when the current year has neither
            # gross_profit nor cost_of_revenue. Live-confirmed via a 2,000-row sample of
            # gross_profitability's missing_sec_data bucket: 437 symbols have a real
            # gross_profit/cost_of_revenue figure somewhere in history that gross_profit_used
            # already recovers for gross_margin - the identical numerator concept was being
            # silently thrown away here instead of reused. Also: this ratio's is-it-really-
            # missing label never distinguished "structurally never reported" (banks, REITs,
            # and - live-confirmed via REGN/JAZZ's real SEC companyfacts, $4-14B/yr revenue,
            # zero CostOfRevenue/CostOfGoodsSold/CostOfGoodsAndServicesSold tagged since ~2020,
            # no gross-profit-style income statement at all) from a genuine loader gap, unlike
            # gross_margin/gross_margin_trend/current_ratio/quick_ratio which already use
            # no_gross_profit_concept/unclassified_balance_sheet for exactly this - see reason
            # assignment below.
            gross_profit_for_profitability = gross_profit_used
            gross_profitability = None
            if gross_profit_for_profitability is not None and total_assets is not None and total_assets > 0:
                computed_gross_profitability = gross_profit_for_profitability / total_assets * 100.0
                if abs(computed_gross_profitability) > 1000:
                    failed_metrics.append("gross_profitability")
                    implausible_ratio_metrics.append("gross_profitability")
                else:
                    gross_profitability = float(computed_gross_profitability)
            # Curve breakpoints from live distribution (p25=7.9/p50=20.2/p75=36.3/p90=56.9,
            # 2936-symbol sample) - a domain-judgment starting point roughly tracking p25/p75/
            # p90, not separately FM-fit to inflection points, same caveat already applied to
            # fcf_margin/payout/asset_turnover's curves.
            gross_profitability_score = (
                _margin_curve(gross_profitability, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
                if gross_profitability is not None
                else None
            )
            # FIXED 2026-08-30 (goal: full-data audit, live sanity-check pass): had no bound at
            # all, unlike gross_profitability right above (same total_assets-denominator shape,
            # same |ratio|>1000 guard) - a near-zero total_assets base blows this up the same way
            # already fixed for gross_profitability/operating_profitability/fcf_margin. Live-caught
            # min=-6,910.69%/max=50,558.09% already on file, several orders of magnitude past any
            # real accruals percentage.
            accruals_ratio = None
            if (
                net_income is not None
                and operating_cash_flow is not None
                and total_assets is not None
                and total_assets > 0
            ):
                computed_accruals_ratio = (net_income - operating_cash_flow) / total_assets * 100.0
                if abs(computed_accruals_ratio) > 1000:
                    failed_metrics.append("accruals_ratio")
                    implausible_ratio_metrics.append("accruals_ratio")
                else:
                    accruals_ratio = float(computed_accruals_ratio)
            # ROCE score: same curve shape as the old roic_score (both are "return on capital
            # deployed" measures, similar scale) - see the roce_pct computation's own comment
            # (near roic_pct above) for why ROCE replaces ROIC in the composite.
            roce_pct_val = metrics.get("roce_pct")
            roce_score = (
                _margin_curve(roce_pct_val, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
                if roce_pct_val is not None
                else None
            )
            # FCF Margin (free_cash_flow / revenue) ADDED 2026-08-26 (Quality pillar exhaustive-
            # input review): cash-conversion efficiency net of capex - distinct from Accruals
            # Ratio (never nets out capex; correlation between the two in the FM panel was only
            # 0.13, genuinely independent signal). FM-validated: t=2.03 univariate/1.93
            # multivariate (151 months), stable across a half-split check (t=1.32/1.53).
            # Replaces accruals_score in the composite.
            #
            # FIXED 2026-08-26 (same-session live verification): initial version had no
            # implausible-ratio bound, unlike every other ratio in this file (net_margin,
            # operating_margin, roic_pct, roe, roa, debt_to_equity, etc. all guard |ratio|>1000
            # - see test_quality_metrics_roe_debt_ratio_implausible_bound.py's own docstring for
            # why this class of bug keeps recurring). Live-caught: 321 rows with |fcf_margin| >
            # 500% right after this field's first production run, near-zero-revenue shells with
            # large negative FCF (e.g. MYSE: fcf_margin=-776,645%, revenue ~$550). Same >1000
            # bound as its siblings now applied.
            # FIXED 2026-08-30 (goal: full-data audit): 618/729 (85%) missing_sec_data symbols
            # live-confirmed with a real free_cash_flow value in SOME other fiscal year (current
            # anchor year lacks it). Added a prior-year fallback, same 3-year-window-then-full-
            # history two-tier pattern already used for interest_expense/gross_profit above -
            # but scoped to a LOCAL pair (fcf_margin_free_cash_flow/fcf_margin_revenue), not the
            # global free_cash_flow/revenue variables: those also feed fcf_to_net_income (paired
            # with the anchor year's net_income) and fcf_growth_yoy (paired with
            # prior_year_free_cash_flow) - overwriting them with a different fiscal year's value
            # would silently break both of those already-correct, year-aligned calculations.
            #
            # FIXED 2026-09-01 (goal session, user-flagged "tons of things saying missing data,
            # I think it's XBRL issues"): the trigger above only fired when the ANCHOR year's
            # free_cash_flow was None - but quality_row's anchor is chosen for BALANCE-SHEET
            # freshness first (the 2026-08-19 fetch_incremental fix, see that query's own
            # docstring), which can legitimately land on a fiscal year where the cash-flow
            # statement is already filed (free_cash_flow present) but the income statement's
            # revenue hasn't been extracted yet (revenue NULL) - not an XBRL tagging bug, a
            # same-year statement-completeness mismatch. When that happens the trigger below
            # never fired, so fcf_margin fell straight to "missing_sec_data" even though a
            # jointly-valid (free_cash_flow, revenue) pair existed in an earlier fiscal year -
            # live-confirmed 128 of 598 current missing_sec_data symbols (e.g. AEMD, ACHV) have
            # exactly this: a real free_cash_flow on the anchor year, real revenue>0 on a prior
            # year, same fallback query already correctly finds the pair once asked. Same
            # asymmetric-fallback-trigger bug class as
            # quality_metrics_fallback_queries_missing_data_unavailable_filter_fixed_20260901 -
            # here it's the None-check being one-sided (checks the numerator's own None-ness,
            # not the denominator's) rather than a missing filter.
            fcf_margin_free_cash_flow = free_cash_flow
            fcf_margin_revenue = revenue
            if fcf_margin_free_cash_flow is None or fcf_margin_revenue is None or fcf_margin_revenue <= 0:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT free_cash_flow, revenue
                        FROM annual_cash_flow acf
                        JOIN annual_income_statement ais
                          ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                        WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                          AND acf.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY acf.fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_fcf_row = cur.fetchone()
                    if not fallback_fcf_row:
                        cur.execute(
                            """
                            SELECT free_cash_flow, revenue
                            FROM annual_cash_flow acf
                            JOIN annual_income_statement ais
                              ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                            WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                            ORDER BY acf.fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_fcf_row = cur.fetchone()
                if fallback_fcf_row:
                    fcf_margin_free_cash_flow = self._nan_to_none(
                        safe_float(fallback_fcf_row[0], f"{symbol}.free_cash_flow_fallback_year", allow_none=True)
                    )
                    fcf_margin_revenue = self._nan_to_none(
                        safe_float(fallback_fcf_row[1], f"{symbol}.revenue_fcf_margin_fallback_year", allow_none=True)
                    )
            fcf_margin = None
            if fcf_margin_free_cash_flow is not None and fcf_margin_revenue is not None and fcf_margin_revenue > 0:
                computed_fcf_margin = fcf_margin_free_cash_flow / fcf_margin_revenue * 100.0
                if abs(computed_fcf_margin) > 1000:
                    failed_metrics.append("fcf_margin")
                    implausible_ratio_metrics.append("fcf_margin")
                else:
                    fcf_margin = float(computed_fcf_margin)
            fcf_margin_score = (
                _margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
                if fcf_margin is not None
                else None
            )
            # Asset Turnover (Revenue / Total Assets, x100 - same "ratio-as-percentage" storage
            # convention as gross_profitability, for consistent bound-checking/curve tooling)
            # ADDED 2026-08-27 (goal: act on the pending candidate flagged by the 2026-08-27
            # missing-metrics sweep - see MEMORY.md
            # quality_asset_turnover_piotroski_tested_20260827). Classic DuPont efficiency
            # component, never previously tested by this pillar's own candidate lists
            # (fama_macbeth_quality_factors.py). FM-validated: t=3.03 full sample (151mo)/3.00
            # first half (<2020-06)/1.54 second half (>=2020-06) - positive, moderate, more
            # time-consistent than net_margin (which decayed to near-zero), though not as
            # rock-solid as the "core five". Same evidentiary tier as margin_volatility_score
            # (t=-2.42/-2.20/-1.34) - weighted the same (7.0) accordingly, below the core five,
            # above interest_coverage/payout's legacy 5% each. Breakpoints are a domain-judgment
            # starting point (not separately FM-fit to inflection points, same caveat as
            # fcf_margin/payout's curves) - a turnover ratio of 0.3x (capital-intensive/
            # utilities) maps to 40, 0.8x (typical industrial) to 75, 1.5x+ (retail/services) to
            # 100.
            asset_turnover = None
            if revenue is not None and total_assets is not None and total_assets > 0:
                computed_asset_turnover = revenue / total_assets * 100.0
                if abs(computed_asset_turnover) > 1000:
                    failed_metrics.append("asset_turnover")
                    implausible_ratio_metrics.append("asset_turnover")
                else:
                    asset_turnover = float(computed_asset_turnover)
            asset_turnover_score = (
                _margin_curve(asset_turnover, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
                if asset_turnover is not None
                else None
            )
            # Debt-to-Equity score: inverted (lower leverage = higher score), anchored to the
            # <0.5 "preferred" threshold used broadly in quality-investing practice (e.g.
            # investing.com's quality-company checklist) - 0.5 maps to 75, 1.0 to 50, 2.0+ to 0.
            # Negative D/E (negative book equity - real financial distress, not a scale quirk)
            # floors to 0 rather than inverting into a spuriously high score. FM-validated:
            # t=3.12 univariate/3.29 multivariate (151 months) - the strongest single leverage
            # signal tested, though it strengthens over time (half-split t=1.50/2.84) rather
            # than being uniformly strong. Replaces debt_to_assets_score in the composite (see
            # that field's own removal note below) - the two were correlated at 0.67 and a
            # joint regression showed real overlap, not independent signals.
            debt_to_equity_val = metrics.get("debt_to_equity")
            if debt_to_equity_val is None:
                debt_to_equity_score = None
            elif debt_to_equity_val < 0:
                debt_to_equity_score = 0.0
            else:
                debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 2.0) * 100.0))
            # Margin volatility (QMJ 2013 Safety leg proxy): precomputed by the caller from
            # multi-year income_rows this function doesn't have (see _compute_margin_volatility).
            # RE-ADDED to scoring 2026-08-27 (goal: revisit the SHAP-interaction sweep's flagged
            # lead, see MEMORY.md quality_margin_volatility_3y_revalidated_borderline_20260827).
            # The 2026-08-26 removal (t=-1.28/-1.51 pooled linear) undersold this component - a
            # SHAP interaction sweep across all 21 Quality candidates later found it has the
            # HIGHEST main-effect ML importance of any candidate (beats roa), and a proper
            # multivariate re-test controlling for the other 7 live components (not a pooled
            # univariate one) found t=-2.42 full-sample, sign-consistent both halves (-2.20/
            # -1.34 - never flips, unlike current_ratio's rejected -0.30/0.32) though it decays
            # ~40% in magnitude - a real but second-tier signal, same evidentiary class as
            # asset_turnover (t=3.03/3.00/1.54), weighted accordingly below (below the "core
            # five" of roa/roce/debt_to_equity/fcf_margin/roe, above interest_coverage/payout's
            # legacy 5% each). Inverted curve: LOWER volatility (more stable margins) scores
            # higher, consistent with the negative FM coefficient. Breakpoints are a reasonable
            # domain-judgment starting point (not separately FM-fit to specific inflection
            # points, same caveat as fcf_margin/payout's curves above) - revisit if live
            # distribution data suggests a better fit.
            # FIXED 2026-08-28 (found while building a test for the sector-conditional formula
            # change above): this read `metrics.get("margin_volatility")`, but `metrics["margin_
            # volatility"]` is only WRITTEN later in this function (see the PERSISTED block
            # below, after quality_components/weighted_score are already computed) - so this
            # always read None regardless of the real value, meaning margin_volatility_score was
            # SILENTLY DEAD in the live composite the entire time it's been documented as a
            # scored, 7%-weighted input (same "computed but not actually wired in" bug class as
            # asset_turnover's insert-column miss and _derive_mom_12_1's mom_12_1 - see MEMORY.md
            # for both). The real value is the `margin_volatility` PARAMETER (precomputed by the
            # caller via _compute_margin_volatility - see this method's own docstring) - use it
            # directly instead of the not-yet-populated dict lookup.
            margin_volatility_val = margin_volatility
            margin_volatility_score = (
                100.0 - _margin_curve(margin_volatility_val, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
                if margin_volatility_val is not None
                else None
            )

            # Operating/Net Margin Trend + ROE Trend score curves, and Payout Ratio's score
            # curve, REMOVED 2026-08-27 (dead-code cleanup, ON CONFLICT sweep pass): all four
            # were computed here (having been MOVED into Quality from Growth earlier the same
            # day) but never consumed after their own isolated FM re-test confirmed them dead
            # (operating_margin_trend t=0.55/0.53/0.27, net_margin_trend t=0.08/0.59/-0.42,
            # roe_trend t=-0.01/0.28/-0.26, payout_ratio t=0.53/0.68/0.06 - see quality_components'
            # own comment below for the full removal history). The raw values
            # (metrics["operating_margin_trend"]/["net_margin_trend"]/["roe_trend"]/
            # ["payout_ratio"]) are computed independently elsewhere in this function and still
            # persisted/displayed - unaffected by removing these dead score curves.
            def _weighted_avg(
                components: list[tuple[float | None, float]], min_weight_pct: float = 0.0
            ) -> float | None:
                """components: [(score_or_None, weight), ...]. Renormalizes over whichever
                components are actually available, same "1/n over available" spirit as the old
                equal-weighted average, just weighted instead of equal. Returns None if the
                available weight doesn't clear min_weight_pct - renormalizing a 1-2 component
                sample up to a full 0-100 score is a thin-sample extrapolation, not an honest
                partial score (see quality_score's own call site for the live-verified case)."""
                available = [(v, w) for v, w in components if v is not None]
                total_weight = sum(w for _, w in available)
                if not available or total_weight <= 0 or total_weight < min_weight_pct:
                    return None
                return sum(v * w for v, w in available) / total_weight

            # REBUILT 2026-08-26 (Quality pillar exhaustive-input review, user-directed).
            # equity_cluster/asset_cluster (ROE+OperatingProfitability, ROA+GrossProfitability)
            # REMOVED - ROE/ROA now scored standalone; OperatingProfitability/GrossProfitability
            # dropped from scoring entirely (weak/insignificant: t=-0.55/1.02, see the removal
            # note above raw values are still computed/persisted). debt_to_assets_score REMOVED,
            # replaced by debt_to_equity_score (see that field's own comment - correlated 0.67,
            # not independent, D/E tested stronger: t=3.12 vs 2.18). roic_score REMOVED, replaced
            # by roce_score (fixes ROIC's cash-netting coverage gap, more time-stable). Accruals
            # REMOVED, replaced by fcf_margin_score (independent signal, corr=0.13 with accruals,
            # tests stronger: t=2.03 vs -1.85). margin_volatility_score REMOVED entirely (t=-1.28/
            # -1.51, weakest surviving-in-composite component before this rebuild, no replacement
            # candidate identified this pass).
            #
            # 8-component composite as of 2026-08-27 (a busy day for this list - see git
            # history/MEMORY.md for the full churn: margin_volatility_score/asset_turnover_score
            # added, the 3 margin/ROE trend fields relocated in from Growth then removed again
            # same day, interest_coverage_score/payout_score removed on confirmed-dead isolated
            # re-test, gross_profitability_score re-added on a confirmed-real isolated re-test -
            # see each component's own comment above for its individual evidence). Final list:
            # roe(11)+roa(18)+roce(18)+fcf_margin(15)+debt_to_equity(18)+margin_volatility(7)+
            # asset_turnover(7)+gross_profitability(7) = 101-point nominal total.
            # min_quality_weight_pct below still calibrated against the original 90-point
            # nominal weight sum's proportions; the 40.0 floor is ~40% of the new 101-point
            # total - still comfortably above any thin-sample case found so far, not re-derived
            # this pass, revisit if a new thin-sample outlier surfaces).
            # Weights set from BOTH full-151-month t-stat magnitude
            # AND a half-split (2014-2020 vs 2020-2026) time-stability check - a component whose
            # t-stat holds up identically across both eras (roce: 1.50/1.50) is weighted higher
            # relative to its raw t-stat than one whose apparent strength turned out to be
            # concentrated in a short/recent window. debt_to_equity/roa/roce/fcf_margin/roe (the
            # "core five", combined 80% of the 8-component version below) are the components with
            # either the strongest full-sample evidence or the best demonstrated time-stability,
            # per explicit user direction after reviewing this same half-split evidence.
            # current_ratio tested (t=-0.30/0.32, sign-flips across the half-split too) and was
            # deliberately excluded - no cross-sectional signal despite being a standard
            # quality-investing checklist item (investing.com's own <1.5 threshold
            # recommendation notwithstanding).
            #
            # Altman Z''-Score REMOVED from scoring 2026-08-26 (same day as the 8-component
            # version below shipped, user directive) - not on new negative evidence, but on a
            # methodological objection: the Z''-Score's academic and practitioner literature
            # frames it as a DISCRETE distress-triage classifier ("quick check of economic
            # health; if the score indicates a problem, do more detailed analysis"), not a
            # continuously-scaled input meant to be averaged into a magnitude-weighted composite
            # alongside ROA/ROE/margin ratios - that use conflates "is this company in the grey
            # zone" with "how much better is a Z of 6 than a Z of 3", which the model was never
            # designed to answer. This independently reinforces what the data already flagged as
            # this component's own weakest point: its naive full-sample t=3.49 looked like the
            # strongest signal of anything ever tested here, but comes from only 41 months
            # (retained_earnings coverage, vs. 151 for everything else) and decays hard within
            # even that short window on a half-split check (t=4.40 first half -> 1.39 second
            # half) - both the methodology and the evidence pointed the same direction. Removed
            # from scoring first (this comment), then removed entirely - computation,
            # persistence (quality_metrics.altman_z_score column), API, and frontend display -
            # per a later user directive that the raw value wasn't worth keeping just for
            # reference (goal session 2026-08-29; see migration
            # 1251_drop_orphaned_altman_z_score_columns.sql).
            # Deliberately left OPEN where (or whether) a distress-flag use belongs - e.g. a
            # discrete gate on GOVERNANCE's trading-eligibility checks, separate from the
            # continuous quality_score - not decided today, revisit later.
            # operating_margin_trend_score/net_margin_trend_score/roe_trend_score REMOVED from
            # scoring 2026-08-27 (user directive, live-observed: all 3 showed "No data" on the
            # StockDetail page for stocks being reviewed - real, not a display bug, coverage is
            # 80-93% live but clusters into "insufficient_prior_year_data" gaps often enough to
            # be visibly distracting at 3% weight each; roe_trend was also already flagged in an
            # earlier growth-pillar memory as "weak, consistently NEGATIVE" - contradicts this
            # pillar's own convention that improving margins/ROE should score higher). Isolated
            # (non-joint-dropna) FM re-validation of these 3, completed same pass: all three
            # genuinely null, not just masked by the original joint-dropna test -
            # operating_margin_trend t=0.55/0.53/0.27, net_margin_trend t=0.08/0.59/-0.42,
            # roe_trend t=-0.01/0.28/-0.26 (full/1st-half/2nd-half) - unlike gross_profitability/
            # margin_volatility_3y below, isolating did NOT recover a signal here. Confirmed
            # dead, not a pending re-check. Fields are still computed/persisted
            # (quality_metrics.operating_margin_trend/net_margin_trend/roe_trend) for reference,
            # just not scored. See _score_quality's docstring in loaders/load_stock_scores.py
            # for the current component list.
            #
            # interest_coverage_score/payout_score REMOVED 2026-08-27 (isolated FM re-test,
            # same pass that recovered gross_profitability/kept margin_volatility_3y): both
            # confirmed dead on properly isolated methodology, not just joint-dropna casualties
            # - interest_coverage t=0.63/-0.12/0.87, payout_ratio t=0.53/0.68/0.06
            # (full/1st-half/2nd-half) - neither ever approached significance even with ~2x the
            # joint-test's sample size. Legacy weights with no real evidentiary basis, unlike
            # margin_volatility_3y/gross_profitability which recovered under isolation. Raw
            # values still computed/persisted (quality_metrics.interest_coverage/payout_ratio)
            # for reference, just not scored.
            # SECTOR-CONDITIONAL FORMULA added 2026-08-28 (goal session "figure out the
            # industry-best right formula" - see _get_symbol_sector's own docstring for the
            # full evidence trail and citation to
            # algo/research/quality_industry_leader_formula_comparison_20260828.py). Financial
            # Services and Real Estate use a 7-input, two-cluster (profitability + safety)
            # structure instead of the flat 8-input tiered average - asset_turnover_score is
            # the ONE input confirmed (via isolated testing, not both roce+asset_turnover as
            # first suspected) to be actively hurting Quality's signal for these two sectors.
            # Matches AQR QMJ's own profitability/safety cluster construction, not invented
            # here. Both clusters and the top-level blend are internally renormalized (same
            # _weighted_avg helper, just called twice more) - a symbol missing part of one
            # cluster still scores off whatever it has, same "score what's available"
            # convention as the universal formula below.
            #
            # NOTE for update_quality_roe_roce_percentiles() (this file, further below): that
            # batch pass's delta-reconciliation math assumes every symbol was scored via the
            # flat 8-input structure below - it does NOT (yet) know how to reconcile through
            # this two-cluster structure, so it explicitly SKIPS Financial Services/Real Estate
            # symbols (see its own SQL filter) rather than risk silently mis-reconciling them -
            # those symbols keep the Pass-1 curve-based ROE/ROCE scores, not the
            # cross-sectional-percentile correction other sectors get. A future pass could
            # extend the reconciliation math to the cluster structure; not attempted this
            # session to avoid rushing that derivation on a file under concurrent edit.
            sector = self._get_symbol_sector(symbol)
            if sector in ("Financial Services", "Real Estate"):
                profitability_cluster_score = _weighted_avg(
                    [
                        (roe_score, 1.0),
                        (roa_score, 1.0),
                        (roce_score, 1.0),
                        (fcf_margin_score, 1.0),
                        (gross_profitability_score, 1.0),
                    ],
                    min_weight_pct=2.0,  # >=2 of 5 available - proportional to the 40%-of-101 floor below
                )
                safety_cluster_score = _weighted_avg(
                    [(debt_to_equity_score, 1.0), (margin_volatility_score, 1.0)],
                    min_weight_pct=1.0,  # >=1 of 2 available
                )
                # WEIGHTS FIXED 2026-09-01 (goal-mode factor-usage review, live-verified via
                # category-leaders spot check, not assumed from reading the code alone). The
                # 2026-08-31 fix directly above correctly solved BAP's case (a real, substantial
                # profitability leg with safety entirely absent) but reintroduced the EXACT bug
                # class the universal branch's own 40%-of-101 floor was built to catch
                # (COMPLETENESS FLOOR comment above, PBT/SBR's original ROA=761%/961% case): a
                # flat (cluster_score, 1.0)/(cluster_score, 1.0) top-level split, gated on
                # "at least one of 2.0 possible weight", let a single cluster - regardless of how
                # thin that cluster's own contents are, down to ONE raw field once its own
                # internal floor is barely cleared - produce a full, undiscounted quality_score.
                # Live-confirmed 2026-09-01: SBR (an Oil Royalty Trust, vendor-classified
                # "Financial Services" by legal structure, not economics - the same symbol this
                # file's original completeness-floor fix was written for) scored 97.13 off
                # margin_volatility=0.72 ALONE (roe/roa/roce/fcf_margin/debt_to_equity/
                # gross_profitability all NULL); PBT scored 87.52 the identical way; XP (a real,
                # legitimately-Financial-Services brokerage, not a misclassification) scored
                # 98.19, also off margin_volatility alone. Universe sweep: 57/1,030 FS/RE-scored
                # symbols get their score from only one cluster, 7 of those from a single raw
                # field. Fixed by weighting each cluster by its ACTUAL share of the universal
                # branch's own nominal weight instead of an arbitrary flat split - profitability
                # (roe 11 + roa 18 + roce 18 + fcf_margin 15 + gross_profitability 7 = 69) and
                # safety (debt_to_equity 18 + margin_volatility 7 = 25), summing to 94 (= the
                # universal branch's 101 minus asset_turnover's 7, the one input this whole
                # sector-conditional path exists to drop - see this method's own docstring).
                quality_components = [(profitability_cluster_score, 69.0), (safety_cluster_score, 25.0)]
                # min_quality_weight_pct PROPORTIONAL FIX 2026-09-01 (same pass): the universal
                # branch requires 40 of its 101 nominal points (~39.6%) before allowing a real
                # score through, rather than a thin-sample extrapolation. This branch's own
                # nominal total is 94 (see above), so the equivalent floor is 40 * (94/101) =
                # 37.2 - NOT "at least one cluster present" (that check no longer means anything
                # once the weights above reflect each cluster's true size: safety alone is only
                # 25 points, below this floor, so a safety-only symbol like XP/SBR/PBT now
                # correctly returns None instead of a single-field score). BAP's case (69 points,
                # profitability only) still clears 37.2 easily, so the 2026-08-31 fix's own
                # target case remains fixed - this tightens the gate without reopening that one.
                min_quality_weight_pct = 37.2
            else:
                quality_components = [
                    (roe_score, 11.0),
                    (roa_score, 18.0),
                    (roce_score, 18.0),
                    (fcf_margin_score, 15.0),
                    (debt_to_equity_score, 18.0),
                    (margin_volatility_score, 7.0),
                    (asset_turnover_score, 7.0),
                    (gross_profitability_score, 7.0),
                ]
            # COMPLETENESS FLOOR added 2026-08-26 (quality-completeness pass, live-verified):
            # renormalizing over 1-3 available components let a single extreme raw ratio
            # (e.g. PBT/SBR's ROA of 761%/961%, oil/gas royalty trusts with atypical capital
            # structures) drive quality_score all the way to 100.00. Found live: 8 of 5191
            # symbols (ASA/BAR/BSEM/CRT/NRP/NRT/PBT/SBR) hit quality_score=100.00 from only
            # 18-38% of the composite's weight (found when this was still an 8-component
            # composite incl. Altman Z, since removed below - the specific symbols/percentages
            # are unaffected, none of the 8 had altman_z_score available anyway) - and
            # critically, stock_scores.data_completeness (6-pillar count) treated these as a
            # fully "real" quality pillar just like a symbol with every component available,
            # since that gate only checks "is quality_score a float", not how much of the
            # composite backed it - GOVERNANCE's 70% trading-
            # eligibility floor did NOT catch these (6 of the 8 verified as live-eligible,
            # data_completeness>=99.99%, data_unavailable=False). 40% is set just above NRP's
            # 38% (roa+fcf_margin+interest_coverage), the largest available-weight case found
            # among the 8 - not an arbitrary round number. Only applies to the universal
            # (non-FS/RE) branch above - the sector-conditional branch sets its own
            # proportional floor (min_quality_weight_pct = 2.0, both clusters present) inline.
            if sector not in ("Financial Services", "Real Estate"):
                min_quality_weight_pct = 40.0
            available_quality_weight = sum(w for v, w in quality_components if v is not None)
            weighted_score = _weighted_avg(quality_components, min_weight_pct=min_quality_weight_pct)

            # PERSISTED 2026-08-26 (goal: quality-input completeness pass): these 4 were being
            # computed and scored into quality_score above but never written to `metrics`, so
            # they had no DB column, no API field, and no frontend display - a real value drove
            # the composite score while staying completely invisible everywhere else (same
            # "computed but invisible" bug class as _derive_mom_12_1's mom_12_1). Migration 1236
            # added the 4 columns + reason companions.
            metrics["gross_profitability"] = gross_profitability
            metrics["gross_profitability_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "gross_profitability" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if no_gross_profit_concept
                    else "missing_sec_data"
                )
                if gross_profitability is None
                else None
            )
            metrics["operating_profitability"] = operating_profitability
            metrics["operating_profitability_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "operating_profitability" in implausible_ratio_metrics
                    else "negative_book_value"
                    if operating_profitability_negative_equity
                    else "reit_special_entity"
                    if no_operating_income_concept
                    else "missing_sec_data"
                )
                if operating_profitability is None
                else None
            )
            metrics["accruals_ratio"] = accruals_ratio
            metrics["accruals_ratio_unavailable_reason"] = (
                ("implausible_ratio" if "accruals_ratio" in implausible_ratio_metrics else "missing_sec_data")
                if accruals_ratio is None
                else None
            )
            metrics["margin_volatility"] = margin_volatility
            metrics["margin_volatility_unavailable_reason"] = (
                "insufficient_history" if margin_volatility is None else None
            )
            # PERSISTED 2026-08-26 (Quality pillar exhaustive-input review): fcf_margin is a
            # newly-scored composite component (see its own comment above) - migration 1238
            # added the column + reason companion. roce_pct's own metrics[...]/reason fields are
            # already set near its computation above (same pattern as roic_pct).
            # FIXED 2026-08-27 (goal: "get all the data for all the inputs" data-completeness
            # sweep): both reasons used to gate on `"X" in failed_metrics`, but neither
            # compute block above appends to failed_metrics when its *inputs* are missing (only
            # when the |ratio|>1000 bound fires) - unlike roa/roe/etc.'s own blocks, which have
            # an explicit `else: failed_metrics.append(...)` for that case. Live-confirmed: 752
            # fcf_margin / 243 asset_turnover universe rows had the value NULL with NO reason
            # recorded at all (same "silently unexplained" signature already fixed for
            # book_value_growth_unavailable_reason - see that memory). Gating on `X is None`
            # directly instead - same pattern gross_profitability/operating_profitability/
            # accruals_ratio just below already use correctly - covers both the missing-inputs
            # and implausible-ratio cases without needing every compute block kept in sync with
            # this list.
            metrics["fcf_margin"] = fcf_margin
            metrics["fcf_margin_unavailable_reason"] = (
                ("implausible_ratio" if "fcf_margin" in implausible_ratio_metrics else "missing_sec_data")
                if fcf_margin is None
                else None
            )
            metrics["asset_turnover"] = asset_turnover
            metrics["asset_turnover_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "asset_turnover" in implausible_ratio_metrics
                    # FIX 2026-09-02 (goal: "no SEC data" audit continuation, same mislabeled-
                    # genuine-gap bug class as the debt_to_equity fix above): asset_turnover
                    # fails whenever revenue or total_assets is None, but this reason never
                    # checked either against the structural gates already used elsewhere in
                    # this file for the identical inputs. Live-confirmed 206 of 294 universe
                    # asset_turnover "missing_sec_data" rows (70%) split between genuinely
                    # revenue-less filers (153, same _get_no_recent_revenue_symbols() gate as
                    # ebitda_margin/gross_margin above) and FPIs with no extractable
                    # total_assets concept (53, see _get_no_recent_total_assets_symbols()).
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    else "no_recent_total_assets_reported"
                    if symbol in self._get_no_recent_total_assets_symbols()
                    else "missing_sec_data"
                )
                if asset_turnover is None
                else None
            )

            # An unprofitable company still has a real, computed quality score (0,
            # after clamping) - that's honest data, not missing data. Do not mark
            # data_unavailable just because every component came out <= 0.
            if weighted_score is not None:
                metrics["quality_score"] = float(min(100.0, max(0.0, weighted_score)))

            # CRITICAL FIX 2026-07-20: Only mark data_unavailable if ALL metrics are missing.
            # Partial quality data is valid and should be scored with completeness tracking.
            # Session 297: Quality scores with 2-3 metrics are legitimate (with completeness % for filtering).
            # Do NOT mark partial data as unavailable - that violates GOVERNANCE "honest incomplete data" principle.

            # Initialize all *_unavailable_reason fields (Session 389)
            # These explain WHY a metric is NULL for users/operators
            metrics["roe_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roe" in implausible_ratio_metrics
                    # FIX 2026-09-02 (goal: "no SEC data" audit continuation, same mislabeled-
                    # genuine-gap class as debt_to_equity/roic_pct/roce_pct above): roe fails
                    # whenever net_income or stockholders_equity is None, but this reason had no
                    # gating at all. Live-confirmed 62 of 133 universe roe "missing_sec_data"
                    # rows (47%) split between the two structural gates.
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None and symbol in self._get_no_recent_stockholders_equity_symbols()
                    else "net_income_not_reported"
                    if net_income is None and symbol in self._get_no_recent_net_income_symbols()
                    else "missing_sec_data"
                )
                if "roe" in failed_metrics
                else None
            )
            metrics["roa_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roa" in implausible_ratio_metrics
                    # FIX 2026-09-02: same fix as roe just above - roa fails whenever
                    # net_income or total_assets is None. Live-confirmed 54 of 124 universe
                    # roa "missing_sec_data" rows (44%).
                    else "no_recent_total_assets_reported"
                    if total_assets is None and symbol in self._get_no_recent_total_assets_symbols()
                    else "net_income_not_reported"
                    if net_income is None and symbol in self._get_no_recent_net_income_symbols()
                    else "missing_sec_data"
                )
                if "roa" in failed_metrics
                else None
            )
            metrics["operating_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "operating_margin" in implausible_ratio_metrics
                    # FIXED 2026-09-02 (goal: "Missing SEC/XBRL data" reduction): operating_margin
                    # fails on the exact same `operating_income_for_margin is None` condition as
                    # operating_profitability/interest_coverage/roic_pct/roce_pct just below/above,
                    # which already reuse `no_operating_income_concept` (tonnage-tax shipping cos +
                    # REITs that structurally never tag pretax_income/income_tax_expense, see
                    # _get_no_tax_concept_symbols) to recategorize this as "reit_special_entity"
                    # instead of "missing_sec_data" - operating_margin was the one sibling left on
                    # the generic label. Live-confirmed 89/205 operating_margin missing_sec_data
                    # rows (AGNC/ARE/EGP/HR and more) are this exact REIT/no-tax-concept case.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    else "missing_sec_data"
                )
                if "operating_margin" in failed_metrics
                else None
            )
            metrics["net_margin_unavailable_reason"] = (
                ("implausible_ratio" if "net_margin" in implausible_ratio_metrics else "missing_sec_data")
                if "net_margin" in failed_metrics
                else None
            )
            metrics["debt_to_equity_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_equity" in implausible_ratio_metrics
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None and symbol in self._get_no_recent_stockholders_equity_symbols()
                    # FIX 2026-09-02 (goal: "no SEC data" audit continuation): debt_to_equity's
                    # failure branch above (line ~3468) fails whenever EITHER
                    # roic_stockholders_equity OR debt_for_roic is None - but this reason block
                    # only ever checked the equity side, via _get_no_recent_stockholders_equity_
                    # symbols(). total_debt_unavailable_reason already has a matching gate for
                    # the debt side (_get_no_recent_debt_components_symbols(), "total_debt_not_
                    # itemized") a few hundred lines below, just never wired in here. Live-
                    # confirmed 265 of 319 universe debt_to_equity "missing_sec_data" rows
                    # (83%) are this exact debt-side gap - a genuinely debt-free filer or one
                    # that stopped itemizing debt components, not a real extraction gap. Same
                    # mislabeled-genuine-gap bug class as the REIT/no-tax-concept fixes for
                    # ebitda_margin/operating_margin/roic_pct/roce_pct above.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None and symbol in self._get_no_recent_debt_components_symbols()
                    else "missing_sec_data"
                )
                if "debt_to_equity" in failed_metrics
                else None
            )
            metrics["current_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "current_ratio" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if unclassified_balance_sheet
                    else "missing_sec_data"
                )
                if "current_ratio" in failed_metrics
                else None
            )
            metrics["quick_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "quick_ratio" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if unclassified_balance_sheet
                    else "missing_sec_data"
                )
                if "quick_ratio" in failed_metrics
                else None
            )
            metrics["interest_coverage_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "interest_coverage" in implausible_ratio_metrics
                    else "interest_expense_not_itemized"
                    if no_recent_interest_expense
                    else "reit_special_entity"
                    if no_operating_income_concept_ic
                    else "missing_sec_data"
                )
                if "interest_coverage" in failed_metrics
                else None
            )
            metrics["debt_to_assets_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_assets" in implausible_ratio_metrics
                    # FIX 2026-09-02 (goal: "no SEC data" audit continuation, same mislabeled-
                    # genuine-gap class as roe/roa above): debt_to_assets fails whenever
                    # total_liabilities or total_assets is None. Live-confirmed 57 of 88
                    # universe debt_to_assets "missing_sec_data" rows (65%).
                    else "no_recent_total_assets_reported"
                    if total_assets is None and symbol in self._get_no_recent_total_assets_symbols()
                    else "total_liabilities_not_reported"
                    if total_liabilities is None and symbol in self._get_no_recent_total_liabilities_symbols()
                    else "missing_sec_data"
                )
                if "debt_to_assets" in failed_metrics
                else None
            )
            # Phase 3 Expansion (Session 357+): New metrics - initialize their _unavailable_reason fields
            metrics["gross_margin_unavailable_reason"] = (
                (
                    "reit_special_entity"
                    if no_gross_profit_concept
                    else "implausible_ratio"
                    if "gross_margin" in implausible_ratio_metrics
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    else "missing_sec_data"
                )
                if "gross_margin" in failed_metrics
                else None
            )
            metrics["ebitda_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "ebitda_margin" in implausible_ratio_metrics
                    # FIXED 2026-09-02 (goal: "Missing SEC/XBRL data" reduction, same fix/pattern as
                    # operating_margin above): load_sec_valuations.py's own EBITDA computation
                    # (`EBITDA = OperatingIncome + D&A`) requires operating_income and stays None
                    # when it's absent - the same REIT/tonnage-tax-exempt "never tags
                    # OperatingIncomeLoss" population `no_operating_income_concept` already
                    # identifies, cascading into `ebitda_ev is None` here. Live-confirmed 75/281
                    # (27%) of ebitda_margin's missing_sec_data rows (STAG/AMH/EGP and more) are
                    # this exact case.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols() or symbol in self._get_blank_check_symbols()
                    else "missing_sec_data"
                )
                if "ebitda_margin" in failed_metrics
                else None
            )
            metrics["roic_pct_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roic_pct" in implausible_ratio_metrics
                    else "unprofitable_stock"
                    if roic_pct_unprofitable
                    else "negative_invested_capital"
                    if roic_pct_negative_invested_capital
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # FIX 2026-09-02 (goal: "no SEC data" audit continuation, same fix as
                    # debt_to_equity_unavailable_reason above): invested_capital (this field's
                    # own denominator input) comes back None whenever debt_for_roic OR
                    # roic_stockholders_equity is None - the negative_invested_capital branch
                    # above only catches a computed non-None value <= 0, not a missing input.
                    # Live-confirmed 264 of 350 universe roic_pct "missing_sec_data" rows (75%)
                    # split between the same two gates just wired into debt_to_equity.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None and symbol in self._get_no_recent_debt_components_symbols()
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None and symbol in self._get_no_recent_stockholders_equity_symbols()
                    else "missing_sec_data"
                )
                if "roic_pct" in failed_metrics
                else None
            )
            metrics["roce_pct_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roce_pct" in implausible_ratio_metrics
                    else "negative_capital_employed"
                    if roce_pct_negative_capital_employed
                    # FIXED 2026-09-01: roce_pct shares roic_operating_income (EBIT numerator)
                    # with roic_pct above - same AGNC/ARE/AMH-class REIT structural gap, same
                    # already-tested gate.
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # FIX 2026-09-02: same debt/equity gates as roic_pct just above -
                    # capital_employed (this field's own denominator) comes back None whenever
                    # debt_for_roic OR roic_stockholders_equity is None, which
                    # negative_capital_employed's <= 0 check doesn't catch. Live-confirmed 328
                    # of 394 universe roce_pct "missing_sec_data" rows (83%).
                    else "total_debt_not_itemized"
                    if debt_for_roic is None and symbol in self._get_no_recent_debt_components_symbols()
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None and symbol in self._get_no_recent_stockholders_equity_symbols()
                    else "missing_sec_data"
                )
                if "roce_pct" in failed_metrics
                else None
            )
            metrics["fcf_to_net_income_unavailable_reason"] = (
                "missing_sec_data" if "fcf_to_net_income" in failed_metrics else None
            )
            metrics["ocf_to_net_income_unavailable_reason"] = (
                "missing_sec_data" if "ocf_to_net_income" in failed_metrics else None
            )
            metrics["payout_ratio_unavailable_reason"] = payout_ratio_reason
            metrics["free_cash_flow_unavailable_reason"] = (
                "missing_sec_data" if "free_cash_flow" in failed_metrics else None
            )
            metrics["operating_cash_flow_unavailable_reason"] = (
                "missing_sec_data" if "operating_cash_flow" in failed_metrics else None
            )
            metrics["total_debt_unavailable_reason"] = (
                (
                    "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    else "missing_sec_data"
                )
                if "total_debt" in failed_metrics
                else None
            )
            # FIX 2026-09-02 (goal: "no SEC data" audit continuation): total_cash_ev is None
            # whenever either sec_valuations has no row at all for this symbol, or has a row
            # but load_sec_valuations.py itself already recorded why total_cash came back
            # NULL there - both real, sitting one join away, never surfaced here before.
            # Live-confirmed 135 of 167 universe total_cash "missing_sec_data" rows have a
            # sec_valuations row; of those, 81 (60%) carry a real, specific `reason` this now
            # reuses instead of a generic "missing_sec_data".
            metrics["total_cash_unavailable_reason"] = (
                (
                    "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "missing_sec_data"
                )
                if "total_cash" in failed_metrics
                else None
            )
            metrics["cash_per_share_unavailable_reason"] = (
                (
                    "shares_outstanding_unavailable"
                    if cash_per_share_shares_missing
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "missing_sec_data"
                )
                if "cash_per_share" in failed_metrics
                else None
            )
            metrics["ebitda_unavailable_reason"] = (
                (
                    # FIXED 2026-09-02 (same fix/pattern as ebitda_margin/operating_margin above):
                    # ebitda is the same load_sec_valuations.py-derived absolute-dollar value
                    # ebitda_margin's numerator uses, and fails structurally for the same
                    # REIT/tonnage-tax-exempt population. Live-confirmed 97/187 (52%) of ebitda's
                    # missing_sec_data rows are this exact case.
                    "reit_special_entity" if no_operating_income_concept else "missing_sec_data"
                )
                if "ebitda" in failed_metrics
                else None
            )
            metrics["earnings_growth_yoy_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "earnings_growth_yoy" in implausible_ratio_metrics
                    else "insufficient_prior_year_data"
                )
                if "earnings_growth_yoy" in failed_metrics
                else None
            )
            metrics["revenue_growth_yoy_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "revenue_growth_yoy" in implausible_ratio_metrics
                    else "insufficient_prior_year_data"
                )
                if "revenue_growth_yoy" in failed_metrics
                else None
            )

            # Quarterly metrics unavailable reasons (Session 78+). Only fill the generic
            # fallback when _compute_quarterly_metrics() (merged into `metrics` above) didn't
            # already set a more specific reason (e.g. "insufficient_eps_data",
            # "insufficient_revenue_data", "insufficient_eps_growth_datapoints",
            # "insufficient_quarterly_history") - this block previously overwrote every one of
            # those with the generic "insufficient_quarterly_data" unconditionally, silently
            # discarding the more specific diagnosis the moment it was computed.
            if metrics.get("consecutive_positive_quarters") is None and not metrics.get(
                "consecutive_positive_quarters_unavailable_reason"
            ):
                metrics["consecutive_positive_quarters_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("earnings_growth_4q_avg") is None and not metrics.get(
                "earnings_growth_4q_avg_unavailable_reason"
            ):
                metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("eps_growth_stability") is None and not metrics.get(
                "eps_growth_stability_unavailable_reason"
            ):
                metrics["eps_growth_stability_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("quarterly_growth_momentum") is None and not metrics.get(
                "quarterly_growth_momentum_unavailable_reason"
            ):
                metrics["quarterly_growth_momentum_unavailable_reason"] = "insufficient_quarterly_data"

            # Analyst metrics - not yet implemented. Guard all fields to avoid clobbering prior reasons.
            # _compute_quarterly_metrics() sets "insufficient_quarterly_history" for quarterly fields;
            # we must not override with "no_analyst_estimates" if that was already set.
            if metrics.get("earnings_surprise_avg") is None and not metrics.get(
                "earnings_surprise_avg_unavailable_reason"
            ):
                metrics["earnings_surprise_avg_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("earnings_beat_rate") is None and not metrics.get("earnings_beat_rate_unavailable_reason"):
                metrics["earnings_beat_rate_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_revision_direction") is None and not metrics.get(
                "estimate_revision_direction_unavailable_reason"
            ):
                metrics["estimate_revision_direction_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("revision_activity_30d") is None and not metrics.get(
                "revision_activity_30d_unavailable_reason"
            ):
                metrics["revision_activity_30d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_momentum_60d") is None and not metrics.get(
                "estimate_momentum_60d_unavailable_reason"
            ):
                metrics["estimate_momentum_60d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_momentum_90d") is None and not metrics.get(
                "estimate_momentum_90d_unavailable_reason"
            ):
                metrics["estimate_momentum_90d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("revision_trend_score") is None and not metrics.get(
                "revision_trend_score_unavailable_reason"
            ):
                metrics["revision_trend_score_unavailable_reason"] = "no_analyst_estimates"

            # Score can be partial; only mark unavailable if ALL metrics failed OR the
            # available weight didn't clear the completeness floor above (thin-sample
            # extrapolation, not honest partial data - see quality_components' own comment).
            # FIXED 2026-08-27 (goal: "get all the data for all the inputs" sweep): the `0 <`
            # lower bound excluded the available_quality_weight == 0 case (every single
            # component missing, e.g. IBN/YICC/APMC) from getting a reason at all - the most
            # clear-cut "insufficient data" case of the three possible outcomes ended up the
            # one with no explanation, while the partial (0 < weight < floor) case correctly
            # got "insufficient_completeness". Live-confirmed 20 universe symbols hit this.
            if weighted_score is None and available_quality_weight < min_quality_weight_pct:
                metrics["quality_score_unavailable_reason"] = "insufficient_completeness"
            else:
                metrics["quality_score_unavailable_reason"] = None

            if failed_metrics:
                # Log which metrics are incomplete (for debugging), but don't mark data_unavailable
                logger.debug(
                    f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics computed from available data. "
                    f"Unavailable: {', '.join(sorted(set(failed_metrics)))} (insufficient SEC data)"
                )

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            return self._unavailable_marker("quality_metrics", symbol)

    @staticmethod
    def _cagr(latest: float, previous: float, years: int) -> float | None:
        """Compute CAGR (Compound Annual Growth Rate)."""
        try:
            latest_f = float(latest) if not isinstance(latest, float) else latest
            previous_f = float(previous) if not isinstance(previous, float) else previous
        except (ValueError, TypeError):
            return None

        if isnan(latest_f) or isnan(previous_f):
            return None
        if previous_f == 0 or previous_f is None:
            return None
        if (latest_f > 0 and previous_f < 0) or (latest_f < 0 and previous_f > 0):
            return None
        ratio = latest_f / previous_f
        return float(((ratio ** (1.0 / years)) - 1) * 100)

    # FIXED 2026-08-24 (goal: NVDA DCF margin-of-safety audit): eps_growth_3y/5y compared raw
    # as-reported EPS across a stock-split boundary without any split-adjustment guard. SEC
    # 10-Ks only restate the comparative fiscal years shown in that filing (typically 2 prior
    # years) - a fiscal year older than that keeps its ORIGINAL pre-split EPS forever unless a
    # later filing happens to restate it too. Live-confirmed on NVDA (10-for-1 split, June
    # 2024): annual_income_statement has FY2023-FY2026 correctly restated post-split
    # (EPS 0.18/1.21/2.97/4.93, shares_outstanding_diluted ~25B each) but FY2021/FY2022 still
    # pre-split (EPS 1.76/3.91, shares_outstanding_diluted ~2.5B - 10x fewer shares). eps_growth_5y
    # compared FY2026 (4.93, post-split) against FY2021 (1.76, pre-split) and got 22.88% CAGR -
    # a plausible-looking number that is actually ~4x too low, since the true split-adjusted
    # FY2021 EPS is 1.76/10=0.176 and the real CAGR is ~95%. Originally guarded by a flat
    # endpoint-to-endpoint share-count ratio threshold; REVISED 2026-08-31 to instead require a
    # single-year jump near a standard split multiple - see _compute_period_growth's guard for
    # the full evidence/rationale (that endpoint-only version false-positived on ~50% of
    # flagged cases, which turned out to be ordinary multi-year organic dilution/buybacks, not
    # splits).
    # Standard stock-split/reverse-split multiples a real single-year share-count jump should
    # land near - see _compute_period_growth's guard for the full evidence/rationale.
    EPS_SPLIT_GUARD_CLEAN_MULTIPLES: tuple[float, ...] = (
        1.5,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        10,
        15,
        20,
        25,
        50,
        100,
    )
    EPS_SPLIT_GUARD_CLEAN_TOLERANCE = 0.06

    def _compute_period_growth(
        self,
        symbol: str,
        values: list[tuple[int, float]],
        offset: int,
        metric_key: str,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        sign_change_metrics: set[str],
        split_discontinuity_metrics: set[str] | None = None,
        shares_by_year: dict[int, float] | None = None,
        *,
        min_abs_target: float = 0.0,
        immaterial_base_metrics: set[str] | None = None,
    ) -> None:
        """Compute growth for a single period (nominally 1y, 3y, or 5y).

        values: list of (fiscal_year, value) tuples, most recent first, with any fiscal
        years lacking usable data already filtered out - so `values[offset]` may be more
        (or less) than `offset` calendar years before `values[0]` if SEC filings have a
        gap (missing annual filing, restatement, etc). CAGR is annualized over the REAL
        fiscal-year gap between the two points, not a hardcoded nominal period - using a
        fixed `years` here previously overstated annualized growth whenever a gap existed
        (e.g. a 2-year gap compounded as if it were 1 year).

        Sets metrics[metric_key] if computation succeeds; appends metric_key to failed_metrics if it fails.
        A profit/loss sign flip between the two points (e.g. EPS -5.95 -> 0.35) also adds
        metric_key to sign_change_metrics - CAGR is mathematically undefined there regardless
        of how much history exists, which is a different, legitimate condition from having too
        few data points and must not be reported to the user as "insufficient history" (found
        2026-08-17: 796 of 1,493 symbols flagged eps_growth_1y "insufficient_history" actually
        had ample EPS history - this sign-flip case, not a real data gap).

        shares_by_year (EPS calls only - see EPS_SPLIT_GUARD_CLEAN_MULTIPLES above): when any
        adjacent pair of fiscal years between the two endpoints has a share-count ratio near a
        standard split multiple, the two EPS values are on different split bases and the
        metric fails closed into sign_change_metrics's sibling set instead of returning a
        silently-wrong number.
        """
        required_count = offset + 1
        if len(values) < required_count:
            failed_metrics.append(metric_key)
            return

        latest_year, latest_val = values[0]
        target_year, target_val = values[offset]
        actual_years = latest_year - target_year
        if actual_years <= 0:
            # Duplicate/out-of-order fiscal_year (restatement) - can't annualize.
            failed_metrics.append(metric_key)
            return

        if (latest_val > 0 and target_val < 0) or (latest_val < 0 and target_val > 0):
            failed_metrics.append(metric_key)
            sign_change_metrics.add(metric_key)
            return

        # ADDED 2026-08-28 (goal: Growth-formula quality pass) - live-measured: 102
        # symbols show EPS growth swings >200% (up to -7200%/+5150%) purely from a
        # near-zero prior-year EPS base, the same 'prior-year base too small to trust'
        # fragility already fixed for net_income_growth_yoy/fcf_growth_yoy/etc.
        if min_abs_target > 0 and abs(target_val) < min_abs_target:
            failed_metrics.append(metric_key)
            if immaterial_base_metrics is not None:
                immaterial_base_metrics.add(metric_key)
            return

        if shares_by_year:
            # REVISED 2026-08-31 (goal: data-loading gap investigation). The original guard
            # compared shares only at the two CAGR ENDPOINTS - this conflates two very
            # different real causes: (a) a genuine unrestated stock split (SEC 10-Ks only
            # restate ~2 prior fiscal years, so a split after an older filing leaves that
            # filing's EPS on the pre-split basis forever - the original NVDA bug this guard
            # exists for) vs (b) ordinary multi-year organic dilution/buybacks (secondary
            # offerings, M&A stock issuance, continuous buyback programs) which changes real
            # per-share economics but does NOT invalidate the comparison - each year's own
            # reported EPS is computed on that year's own real share count, so the growth
            # number is legitimate, just reflecting real dilution/anti-dilution the way EPS
            # growth is supposed to. Live-verified against annual_income_statement: TRNO/RCMT/
            # LOPE/ARW (real, actively-scored companies) show smooth multi-year share drift
            # (steady REIT equity issuance / steady buybacks) with no single-year jump near a
            # clean split ratio, yet were blocked purely because their cumulative 3-5yr
            # endpoint ratio crossed 1.5x - 787 of 1,569 currently-flagged (symbol, period)
            # comparisons (50%) turned out to be this false-positive case. The known real
            # splits (NVDA 2022->2023 9.89x~10, GOOGL 2021->2022 19.87x~20, AVGO 2021->2022
            # 9.86x~10, SMCI 2021->2022 10.02x~10) are all still correctly caught by requiring
            # the jump be concentrated in ONE adjacent fiscal-year pair AND close to a standard
            # split multiple - multi-year buyback drift on top of a real split (e.g. GOOGL's
            # 5yr endpoint ratio is only 18.1x, not exactly 20x, from ~7% buybacks since the
            # split) means an endpoint-only near-clean check isn't reliable either; scanning
            # adjacent-year pairs isolates the split year itself regardless of what happens in
            # surrounding years.
            window_years = sorted(y for y in shares_by_year if target_year <= y <= latest_year)
            for year_a, year_b in itertools.pairwise(window_years):
                shares_a, shares_b = shares_by_year[year_a], shares_by_year[year_b]
                share_ratio = max(shares_a, shares_b) / min(shares_a, shares_b)
                if any(
                    abs(share_ratio - mult) / mult < self.EPS_SPLIT_GUARD_CLEAN_TOLERANCE
                    for mult in self.EPS_SPLIT_GUARD_CLEAN_MULTIPLES
                ):
                    failed_metrics.append(metric_key)
                    if split_discontinuity_metrics is not None:
                        split_discontinuity_metrics.add(metric_key)
                    return

        growth = self._cagr(latest_val, target_val, actual_years)
        if growth is not None and abs(growth) < MAX_PLAUSIBLE_GROWTH_PCT:
            metrics[metric_key] = float(round(growth, 2))
        else:
            failed_metrics.append(metric_key)

    def _compute_growth_metrics(  # noqa: C901 -- pre-existing complexity debt from the book_value_growth addition (migration 1242), not introduced by this change
        self, symbol: str, income_rows: list[Any]
    ) -> dict[str, Any]:
        """Compute multi-year growth rates from annual income statement history.

        Calculates CAGR for 1y, 3y, 5y periods using compound annual growth rate formula.
        income_rows: List of (fiscal_year, total_revenue, operating_income, net_income,
        earnings_per_share[, shares_outstanding_diluted, shares_outstanding_basic[,
        stockholders_equity]]) sorted DESC by fiscal_year (most recent first). The two shares
        columns are optional (older 5-tuple test fixtures still work) and feed the
        EPS_SPLIT_GUARD_CLEAN_MULTIPLES guard; stockholders_equity (added 2026-08-27) is also
        optional (older 5/7-tuple test fixtures still work) and feeds book_value_growth's BVPS
        computation only - every other field here is unaffected by its absence.
        """
        if not income_rows:
            return self._unavailable_marker("growth_metrics", symbol)

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "revenue_growth_5y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "eps_growth_5y": None,
            "book_value_growth": None,
            "updated_at": get_loader_timestamp(),
            "data_unavailable": False,
            "data_source": "sec_audited",
        }

        revenues: list[tuple[int, float]] = []
        eps_values: list[tuple[int, float]] = []
        # book_value_growth ADDED 2026-08-27 (goal: recover a Growth candidate wrongly killed
        # by a joint-dropna sample-bias bug found this session - see
        # algo/research/growth_reinvestment_book_value_candidates.py:105-109 for the original
        # formula this mirrors: bvps = stockholders_equity/shares_outstanding_diluted,
        # book_value_growth = bvps/prior_bvps - 1. Isolated re-test found this the strongest,
        # most time-consistent signal anywhere in this repo's Growth research (t=-5.82 full/
        # -2.05 1st-half/-5.93 2nd-half univariate; still -5.90/-2.04/-6.15 controlling for
        # asset_growth_yoy, which it statistically subsumes - asset_growth_yoy's own
        # coefficient collapses to insignificance once this is in the regression). Reuses
        # _compute_period_growth's existing offset=1 CAGR machinery (same sign-change/
        # split-guard protection EPS already gets) rather than a bespoke computation - BVPS is
        # just another (fiscal_year, value) series, no new math needed.
        bvps_values: list[tuple[int, float]] = []
        shares_by_year: dict[int, float] = {}
        for row in income_rows:
            try:
                fiscal_year = int(row[0]) if row[0] is not None else None
                rev = float(row[1]) if row[1] is not None else None
                eps = float(row[4]) if row[4] is not None else None
                # shares_outstanding_diluted/basic (row[5]/row[6]) are only present in the live
                # production query - defensive len() check keeps older 5-tuple test fixtures
                # working unchanged (see EPS_SPLIT_GUARD_SHARE_RATIO guard above).
                shares = None
                if len(row) > 5 and row[5] is not None:
                    shares = float(row[5])
                elif len(row) > 6 and row[6] is not None:
                    shares = float(row[6])
                # stockholders_equity (row[7]) is only present in the live production query
                # (LEFT JOIN annual_balance_sheet, added 2026-08-27 for book_value_growth) -
                # same defensive len() check as shares above, older test fixtures still work.
                stockholders_equity = None
                if len(row) > 7 and row[7] is not None:
                    stockholders_equity = float(row[7])
                rev = self._nan_to_none(rev)
                eps = self._nan_to_none(eps)
                stockholders_equity = self._nan_to_none(stockholders_equity)
                if fiscal_year is None:
                    continue
                if rev is not None and rev > 0:
                    revenues.append((fiscal_year, rev))
                if eps is not None and eps != 0:
                    eps_values.append((fiscal_year, eps))
                if shares is not None and shares > 0 and fiscal_year not in shares_by_year:
                    shares_by_year[fiscal_year] = shares
                # Book value per share can be legitimately negative (heavily-levered/buyback-
                # heavy firms) - only require shares > 0 (a real, positive share count to
                # divide by), same convention as _compute_period_growth's own sign-change
                # guard handling negative-to-positive transitions correctly rather than
                # excluding negative values outright.
                if stockholders_equity is not None and shares is not None and shares > 0:
                    bvps_values.append((fiscal_year, stockholders_equity / shares))
            except (ValueError, TypeError):
                continue

        failed_metrics: list[str] = []
        sign_change_metrics: set[str] = set()
        split_discontinuity_metrics: set[str] = set()
        immaterial_base_metrics: set[str] = set()
        self._compute_period_growth(
            symbol, revenues, 1, "revenue_growth_1y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            1,
            "eps_growth_1y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
        )
        # book_value_growth: same split-guard as EPS (shares_by_year) since BVPS is equally
        # sensitive to a stock-split changing the per-share denominator across the two CAGR
        # endpoints - see this method's own comment above for the full evidence trail.
        self._compute_period_growth(
            symbol,
            bvps_values,
            1,
            "book_value_growth",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
        )
        self._compute_period_growth(
            symbol, revenues, 3, "revenue_growth_3y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            3,
            "eps_growth_3y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
        )
        self._compute_period_growth(
            symbol, revenues, 5, "revenue_growth_5y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            5,
            "eps_growth_5y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
        )

        if not revenues and not eps_values and not bvps_values:
            return self._unavailable_marker("growth_metrics", symbol)

        def _growth_reason(metric_key: str) -> str | None:
            if metric_key in sign_change_metrics:
                return "growth_undefined_sign_change"
            if metric_key in split_discontinuity_metrics:
                return "growth_undefined_share_count_discontinuity"
            if metric_key in immaterial_base_metrics:
                return "immaterial_prior_year_base"
            if metric_key in failed_metrics:
                return "insufficient_history"
            return None

        # Initialize all *_unavailable_reason fields (Session 389)
        metrics["revenue_growth_1y_unavailable_reason"] = _growth_reason("revenue_growth_1y")
        metrics["revenue_growth_3y_unavailable_reason"] = _growth_reason("revenue_growth_3y")
        metrics["revenue_growth_5y_unavailable_reason"] = _growth_reason("revenue_growth_5y")
        metrics["eps_growth_1y_unavailable_reason"] = _growth_reason("eps_growth_1y")
        metrics["eps_growth_3y_unavailable_reason"] = _growth_reason("eps_growth_3y")
        metrics["eps_growth_5y_unavailable_reason"] = _growth_reason("eps_growth_5y")
        metrics["book_value_growth_unavailable_reason"] = _growth_reason("book_value_growth")

        if failed_metrics:
            # 7 possible periods as of 2026-08-27 (book_value_growth added) - was 6.
            if len(failed_metrics) == 7:
                # FIXED 2026-08-21 (goal session - bulk EPS/revenue cross-check audit):
                # this used to `return self._unavailable_marker("growth_metrics", symbol)`
                # here - a completely fresh dict that hardcodes EVERY *_unavailable_reason
                # to the literal string "insufficient_history", discarding the nuanced
                # per-field reasons _growth_reason() just computed above (including a real
                # sign-change correctly detected via sign_change_metrics). Live-confirmed on
                # LFT/BDTX/ENLV: each has genuinely too little revenue history (correctly
                # "insufficient_history") AND a real EPS sign change between the two CAGR
                # endpoints (should be "growth_undefined_sign_change" per this file's own
                # sign-change comment above - "must not be reported to the user as
                # insufficient history") - but because ALL 6 periods failed (for this mix of
                # two different, both-legitimate reasons), the len==6 shortcut fired and
                # silently overwrote the already-correct eps_growth_*_unavailable_reason
                # values back to "insufficient_history" anyway. Keep the per-field reasons
                # already set in `metrics` instead of discarding them - the row still has no
                # usable growth VALUES (all 6 are None either way), so data_unavailable=True
                # remains correct, just with honest per-field reasons preserved.
                metrics["data_unavailable"] = True
                metrics["data_source"] = "none"
                metrics["reason"] = (
                    f"Insufficient historical data: {', '.join(sorted(set(failed_metrics)))} could not be computed"
                )
                # FIXED 2026-08-28 (goal-mode data-loading audit, same sweep that found the
                # book_value_growth and quality_score _unavailable_marker gaps): _SHARED_TREND_
                # FIELDS only get copied into this dict from quality_dict by fetch_incremental's
                # own caller-side loop (~line 874), and that loop is gated on
                # `not growth_dict.get("data_unavailable")` - once this branch sets
                # data_unavailable=True (a few lines up), the copy never runs, so these 16
                # fields' value AND reason both stay permanently unset. Every OTHER
                # data_unavailable=True path in this file (early-return, stale_fiscal_data,
                # fetch exceptions) goes through _unavailable_marker(), which already sets a
                # real reason for all 16 - this branch is the one path that sets
                # data_unavailable=True directly without going through it. Live-confirmed 118
                # symbols (CXII, AARD, TMS, AEON, etc.) with all 16 fields NULL/NULL despite this
                # branch's own metrics["reason"] already explaining the row. Not "selectively
                # patching" a blanked row (2026-08-10's stated reason for the data_unavailable
                # gate above) - the VALUES stay None either way, this only adds the same missing
                # reason code every other blanked-row path already gets.
                for field in _SHARED_TREND_FIELDS:
                    metrics.setdefault(field, None)
                    metrics[f"{field}_unavailable_reason"] = metrics["reason"]
            else:
                # PARTIAL failure (1-5 of 6 periods, e.g. eps_growth_5y needs 6 fiscal years
                # of history that many symbols don't have yet): the periods that DID compute
                # are real values, not noise - leave data_unavailable=False so downstream
                # scoring (load_stock_scores.py::_score_growth) can weight whatever periods
                # are present instead of discarding the whole row. _score_growth already
                # renormalizes over available fields; it was this flag - not the scorer -
                # that was throwing partial data away before it ever got there. `reason`
                # still records what's missing.
                metrics["reason"] = (
                    f"Incomplete growth metrics: {', '.join(sorted(set(failed_metrics)))} failed to compute (insufficient history or invalid data)"
                )
            logger.debug(
                f"[VALUE_QUALITY_GROWTH] {symbol}: Partial growth metrics (failed: {', '.join(sorted(set(failed_metrics)))})"
            )

        # Initialize trend fields to None (same as quality_metrics) - these are not computed
        # from income statement history in this method, they come from quality_metrics which
        # has access to balance sheet data. Initializing them here prevents database errors
        # from missing column values in the growth_metrics INSERT.
        for field in [
            "net_income_growth_yoy",
            "operating_income_growth_yoy",
            "gross_margin_trend",
            "operating_margin_trend",
            "net_margin_trend",
            "roe_trend",
            "sustainable_growth_rate",
            "quarterly_growth_momentum",
            "fcf_growth_yoy",
            "ocf_growth_yoy",
            "asset_growth_yoy",
        ]:
            if field not in metrics:
                metrics[field] = None

        return metrics

    def _insert_value_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert value_metrics row."""
        cur.execute(
            """
            INSERT INTO value_metrics
            (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, net_payout_yield, fcf_yield, forward_pe, enterprise_value, ev_ebitda, ev_revenue, market_cap, intrinsic_value_per_share, margin_of_safety_pct, value_score, data_unavailable, reason, data_source, updated_at,
             pe_ratio_unavailable_reason, pb_ratio_unavailable_reason, ps_ratio_unavailable_reason, peg_ratio_unavailable_reason,
             dividend_yield_unavailable_reason, fcf_yield_unavailable_reason, forward_pe_unavailable_reason, ev_ebitda_unavailable_reason, ev_revenue_unavailable_reason,
             market_cap_unavailable_reason, held_percent_institutions, held_percent_institutions_unavailable_reason,
             intrinsic_value_unavailable_reason, margin_of_safety_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio,
                peg_ratio = EXCLUDED.peg_ratio,
                dividend_yield = EXCLUDED.dividend_yield,
                net_payout_yield = EXCLUDED.net_payout_yield,
                fcf_yield = EXCLUDED.fcf_yield,
                forward_pe = EXCLUDED.forward_pe,
                enterprise_value = EXCLUDED.enterprise_value,
                ev_ebitda = EXCLUDED.ev_ebitda,
                ev_revenue = EXCLUDED.ev_revenue,
                market_cap = EXCLUDED.market_cap,
                intrinsic_value_per_share = EXCLUDED.intrinsic_value_per_share,
                margin_of_safety_pct = EXCLUDED.margin_of_safety_pct,
                value_score = EXCLUDED.value_score,
                pe_ratio_unavailable_reason = EXCLUDED.pe_ratio_unavailable_reason,
                pb_ratio_unavailable_reason = EXCLUDED.pb_ratio_unavailable_reason,
                ps_ratio_unavailable_reason = EXCLUDED.ps_ratio_unavailable_reason,
                peg_ratio_unavailable_reason = EXCLUDED.peg_ratio_unavailable_reason,
                dividend_yield_unavailable_reason = EXCLUDED.dividend_yield_unavailable_reason,
                fcf_yield_unavailable_reason = EXCLUDED.fcf_yield_unavailable_reason,
                forward_pe_unavailable_reason = EXCLUDED.forward_pe_unavailable_reason,
                ev_ebitda_unavailable_reason = EXCLUDED.ev_ebitda_unavailable_reason,
                ev_revenue_unavailable_reason = EXCLUDED.ev_revenue_unavailable_reason,
                market_cap_unavailable_reason = EXCLUDED.market_cap_unavailable_reason,
                held_percent_institutions = EXCLUDED.held_percent_institutions,
                held_percent_institutions_unavailable_reason = EXCLUDED.held_percent_institutions_unavailable_reason,
                intrinsic_value_unavailable_reason = EXCLUDED.intrinsic_value_unavailable_reason,
                margin_of_safety_unavailable_reason = EXCLUDED.margin_of_safety_unavailable_reason,
                data_unavailable = EXCLUDED.data_unavailable,
                reason = EXCLUDED.reason,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["symbol"],
                row["pe_ratio"],
                row["pb_ratio"],
                row["ps_ratio"],
                row["peg_ratio"],
                row["dividend_yield"],
                row.get("net_payout_yield"),
                row["fcf_yield"],
                row.get("forward_pe"),
                row.get("enterprise_value"),
                row.get("ev_ebitda"),
                row.get("ev_revenue"),
                row.get("market_cap"),
                row.get("intrinsic_value_per_share"),
                row.get("margin_of_safety_pct"),
                row.get("value_score"),
                row["data_unavailable"],
                row.get("reason"),
                row.get("data_source", "sec_audited"),
                row["updated_at"],
                row.get("pe_ratio_unavailable_reason"),
                row.get("pb_ratio_unavailable_reason"),
                row.get("ps_ratio_unavailable_reason"),
                row.get("peg_ratio_unavailable_reason"),
                row.get("dividend_yield_unavailable_reason"),
                row.get("fcf_yield_unavailable_reason"),
                row.get("forward_pe_unavailable_reason"),
                row.get("ev_ebitda_unavailable_reason"),
                row.get("ev_revenue_unavailable_reason"),
                row.get("market_cap_unavailable_reason"),
                # FIXED 2026-08-28 (goal-mode data-loading audit): held_percent_institutions
                # (the VALUE, not just its reason) was entirely absent from this INSERT's
                # column list/VALUES/ON CONFLICT SET - live-confirmed 0/5103 universe coverage
                # despite _build_value_metrics correctly fetching real values from
                # positioning_metrics (e.g. CSIQ 79.27%, ON/CENX/BRKR 100%) for the great
                # majority of symbols. Only the reason column was ever written, so every row
                # showed NULL value + (usually) NULL reason too, since a real value has no
                # reason to report - the worst-case version of the "ON CONFLICT DO UPDATE SET
                # clause never included a column" bug class this session found 3 other
                # instances of (book_value_growth, quality_score, and 4 quality_metrics
                # earnings/quarterly fields).
                row.get("held_percent_institutions"),
                row.get("held_percent_institutions_unavailable_reason"),
                row.get("intrinsic_value_unavailable_reason"),
                row.get("margin_of_safety_unavailable_reason"),
            ),
        )

    def _insert_quality_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert quality_metrics row."""
        cur.execute(
            """
            INSERT INTO quality_metrics
            (symbol, roe, roa, operating_margin, net_margin, debt_to_equity, debt_to_assets, current_ratio, quick_ratio, interest_coverage, quality_score, ebitda, ebitda_margin, data_unavailable, reason, data_source, updated_at,
             gross_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, payout_ratio,
             free_cash_flow, operating_cash_flow, total_debt, total_cash, cash_per_share,
             earnings_growth_yoy, revenue_growth_yoy,
             net_income_growth_yoy, operating_income_growth_yoy, gross_margin_trend, operating_margin_trend, net_margin_trend,
             roe_trend, sustainable_growth_rate, quarterly_growth_momentum, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy,
             earnings_surprise_avg, eps_growth_stability, earnings_beat_rate, consecutive_positive_quarters,
             earnings_growth_4q_avg,
             gross_profitability, operating_profitability, accruals_ratio, margin_volatility,
             roe_unavailable_reason, roa_unavailable_reason, operating_margin_unavailable_reason, net_margin_unavailable_reason,
             debt_to_equity_unavailable_reason, current_ratio_unavailable_reason, quick_ratio_unavailable_reason,
             interest_coverage_unavailable_reason, debt_to_assets_unavailable_reason, quality_score_unavailable_reason,
             gross_margin_unavailable_reason, ebitda_unavailable_reason, ebitda_margin_unavailable_reason, roic_pct_unavailable_reason,
             fcf_to_net_income_unavailable_reason, ocf_to_net_income_unavailable_reason, payout_ratio_unavailable_reason,
             free_cash_flow_unavailable_reason, operating_cash_flow_unavailable_reason, total_debt_unavailable_reason,
             total_cash_unavailable_reason, cash_per_share_unavailable_reason, earnings_growth_yoy_unavailable_reason,
             revenue_growth_yoy_unavailable_reason, net_income_growth_yoy_unavailable_reason, operating_income_growth_yoy_unavailable_reason,
             gross_margin_trend_unavailable_reason, operating_margin_trend_unavailable_reason, net_margin_trend_unavailable_reason,
             roe_trend_unavailable_reason, sustainable_growth_rate_unavailable_reason, quarterly_growth_momentum_unavailable_reason,
             fcf_growth_yoy_unavailable_reason, ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason,
             earnings_growth_4q_avg_unavailable_reason,
             gross_profitability_unavailable_reason, operating_profitability_unavailable_reason,
             accruals_ratio_unavailable_reason, margin_volatility_unavailable_reason,
             roce_pct, roce_pct_unavailable_reason, fcf_margin, fcf_margin_unavailable_reason,
             asset_turnover, asset_turnover_unavailable_reason,
             earnings_surprise_avg_unavailable_reason, eps_growth_stability_unavailable_reason,
             earnings_beat_rate_unavailable_reason, consecutive_positive_quarters_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                roe = EXCLUDED.roe,
                roa = EXCLUDED.roa,
                operating_margin = EXCLUDED.operating_margin,
                net_margin = EXCLUDED.net_margin,
                debt_to_equity = EXCLUDED.debt_to_equity,
                debt_to_assets = EXCLUDED.debt_to_assets,
                current_ratio = EXCLUDED.current_ratio,
                quick_ratio = EXCLUDED.quick_ratio,
                interest_coverage = EXCLUDED.interest_coverage,
                quality_score = EXCLUDED.quality_score,
                ebitda = EXCLUDED.ebitda,
                ebitda_margin = EXCLUDED.ebitda_margin,
                net_income_growth_yoy = EXCLUDED.net_income_growth_yoy,
                operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                gross_margin_trend = EXCLUDED.gross_margin_trend,
                operating_margin_trend = EXCLUDED.operating_margin_trend,
                net_margin_trend = EXCLUDED.net_margin_trend,
                roe_trend = EXCLUDED.roe_trend,
                sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum,
                fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                ocf_growth_yoy = EXCLUDED.ocf_growth_yoy,
                asset_growth_yoy = EXCLUDED.asset_growth_yoy,
                earnings_surprise_avg = EXCLUDED.earnings_surprise_avg,
                eps_growth_stability = EXCLUDED.eps_growth_stability,
                earnings_beat_rate = EXCLUDED.earnings_beat_rate,
                consecutive_positive_quarters = EXCLUDED.consecutive_positive_quarters,
                earnings_growth_4q_avg = EXCLUDED.earnings_growth_4q_avg,
                gross_profitability = EXCLUDED.gross_profitability,
                operating_profitability = EXCLUDED.operating_profitability,
                accruals_ratio = EXCLUDED.accruals_ratio,
                margin_volatility = EXCLUDED.margin_volatility,
                gross_margin = EXCLUDED.gross_margin,
                roic_pct = EXCLUDED.roic_pct,
                fcf_to_net_income = EXCLUDED.fcf_to_net_income,
                ocf_to_net_income = EXCLUDED.ocf_to_net_income,
                payout_ratio = EXCLUDED.payout_ratio,
                free_cash_flow = EXCLUDED.free_cash_flow,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                total_debt = EXCLUDED.total_debt,
                total_cash = EXCLUDED.total_cash,
                cash_per_share = EXCLUDED.cash_per_share,
                earnings_growth_yoy = EXCLUDED.earnings_growth_yoy,
                revenue_growth_yoy = EXCLUDED.revenue_growth_yoy,
                roe_unavailable_reason = EXCLUDED.roe_unavailable_reason,
                roa_unavailable_reason = EXCLUDED.roa_unavailable_reason,
                operating_margin_unavailable_reason = EXCLUDED.operating_margin_unavailable_reason,
                net_margin_unavailable_reason = EXCLUDED.net_margin_unavailable_reason,
                debt_to_equity_unavailable_reason = EXCLUDED.debt_to_equity_unavailable_reason,
                current_ratio_unavailable_reason = EXCLUDED.current_ratio_unavailable_reason,
                quick_ratio_unavailable_reason = EXCLUDED.quick_ratio_unavailable_reason,
                interest_coverage_unavailable_reason = EXCLUDED.interest_coverage_unavailable_reason,
                debt_to_assets_unavailable_reason = EXCLUDED.debt_to_assets_unavailable_reason,
                quality_score_unavailable_reason = EXCLUDED.quality_score_unavailable_reason,
                gross_margin_unavailable_reason = EXCLUDED.gross_margin_unavailable_reason,
                ebitda_unavailable_reason = EXCLUDED.ebitda_unavailable_reason,
                ebitda_margin_unavailable_reason = EXCLUDED.ebitda_margin_unavailable_reason,
                roic_pct_unavailable_reason = EXCLUDED.roic_pct_unavailable_reason,
                fcf_to_net_income_unavailable_reason = EXCLUDED.fcf_to_net_income_unavailable_reason,
                ocf_to_net_income_unavailable_reason = EXCLUDED.ocf_to_net_income_unavailable_reason,
                payout_ratio_unavailable_reason = EXCLUDED.payout_ratio_unavailable_reason,
                free_cash_flow_unavailable_reason = EXCLUDED.free_cash_flow_unavailable_reason,
                operating_cash_flow_unavailable_reason = EXCLUDED.operating_cash_flow_unavailable_reason,
                total_debt_unavailable_reason = EXCLUDED.total_debt_unavailable_reason,
                total_cash_unavailable_reason = EXCLUDED.total_cash_unavailable_reason,
                cash_per_share_unavailable_reason = EXCLUDED.cash_per_share_unavailable_reason,
                earnings_growth_yoy_unavailable_reason = EXCLUDED.earnings_growth_yoy_unavailable_reason,
                revenue_growth_yoy_unavailable_reason = EXCLUDED.revenue_growth_yoy_unavailable_reason,
                net_income_growth_yoy_unavailable_reason = EXCLUDED.net_income_growth_yoy_unavailable_reason,
                operating_income_growth_yoy_unavailable_reason = EXCLUDED.operating_income_growth_yoy_unavailable_reason,
                gross_margin_trend_unavailable_reason = EXCLUDED.gross_margin_trend_unavailable_reason,
                operating_margin_trend_unavailable_reason = EXCLUDED.operating_margin_trend_unavailable_reason,
                net_margin_trend_unavailable_reason = EXCLUDED.net_margin_trend_unavailable_reason,
                roe_trend_unavailable_reason = EXCLUDED.roe_trend_unavailable_reason,
                sustainable_growth_rate_unavailable_reason = EXCLUDED.sustainable_growth_rate_unavailable_reason,
                quarterly_growth_momentum_unavailable_reason = EXCLUDED.quarterly_growth_momentum_unavailable_reason,
                fcf_growth_yoy_unavailable_reason = EXCLUDED.fcf_growth_yoy_unavailable_reason,
                ocf_growth_yoy_unavailable_reason = EXCLUDED.ocf_growth_yoy_unavailable_reason,
                asset_growth_yoy_unavailable_reason = EXCLUDED.asset_growth_yoy_unavailable_reason,
                earnings_growth_4q_avg_unavailable_reason = EXCLUDED.earnings_growth_4q_avg_unavailable_reason,
                gross_profitability_unavailable_reason = EXCLUDED.gross_profitability_unavailable_reason,
                operating_profitability_unavailable_reason = EXCLUDED.operating_profitability_unavailable_reason,
                accruals_ratio_unavailable_reason = EXCLUDED.accruals_ratio_unavailable_reason,
                margin_volatility_unavailable_reason = EXCLUDED.margin_volatility_unavailable_reason,
                roce_pct = EXCLUDED.roce_pct,
                roce_pct_unavailable_reason = EXCLUDED.roce_pct_unavailable_reason,
                fcf_margin = EXCLUDED.fcf_margin,
                fcf_margin_unavailable_reason = EXCLUDED.fcf_margin_unavailable_reason,
                asset_turnover = EXCLUDED.asset_turnover,
                asset_turnover_unavailable_reason = EXCLUDED.asset_turnover_unavailable_reason,
                -- FIXED 2026-08-28 (goal-mode data-loading audit): these 4 columns' VALUES
                -- were always in this INSERT (earnings_surprise_avg/eps_growth_stability/
                -- earnings_beat_rate/consecutive_positive_quarters above), but their
                -- *_unavailable_reason counterparts were never part of this statement at all -
                -- same "ON CONFLICT DO UPDATE SET clause never included the reason column" bug
                -- already fixed once for growth_metrics.book_value_growth_unavailable_reason
                -- (see test_growth_metrics_book_value_growth_unavailable_reason_wired_20260827.py).
                -- Live-confirmed 1546-3728 rows per field had a real value/reason computed
                -- upstream (_unavailable_marker/_compute_quality_metrics both set it correctly)
                -- that silently never reached the database - permanently frozen at whatever the
                -- column held before, indistinguishable from every legitimate NULL-with-no-
                -- reason case this whole system exists to eliminate.
                earnings_surprise_avg_unavailable_reason = EXCLUDED.earnings_surprise_avg_unavailable_reason,
                eps_growth_stability_unavailable_reason = EXCLUDED.eps_growth_stability_unavailable_reason,
                earnings_beat_rate_unavailable_reason = EXCLUDED.earnings_beat_rate_unavailable_reason,
                consecutive_positive_quarters_unavailable_reason = EXCLUDED.consecutive_positive_quarters_unavailable_reason,
                data_unavailable = EXCLUDED.data_unavailable,
                reason = EXCLUDED.reason,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["symbol"],
                row["roe"],
                row.get("roa"),
                row["operating_margin"],
                row["net_margin"],
                row["debt_to_equity"],
                row.get("debt_to_assets"),
                row.get("current_ratio"),
                row.get("quick_ratio"),
                row.get("interest_coverage"),
                row.get("quality_score"),
                row.get("ebitda"),
                row.get("ebitda_margin"),
                row["data_unavailable"],
                row.get("reason"),
                row.get("data_source", "sec_audited"),
                row["updated_at"],
                row.get("gross_margin"),
                row.get("roic_pct"),
                row.get("fcf_to_net_income"),
                row.get("ocf_to_net_income"),
                row.get("payout_ratio"),
                row.get("free_cash_flow"),
                row.get("operating_cash_flow"),
                row.get("total_debt"),
                row.get("total_cash"),
                row.get("cash_per_share"),
                row.get("earnings_growth_yoy"),
                row.get("revenue_growth_yoy"),
                row.get("net_income_growth_yoy"),
                row.get("operating_income_growth_yoy"),
                row.get("gross_margin_trend"),
                row.get("operating_margin_trend"),
                row.get("net_margin_trend"),
                row.get("roe_trend"),
                row.get("sustainable_growth_rate"),
                row.get("quarterly_growth_momentum"),
                row.get("fcf_growth_yoy"),
                row.get("ocf_growth_yoy"),
                row.get("asset_growth_yoy"),
                row.get("earnings_surprise_avg"),
                row.get("eps_growth_stability"),
                row.get("earnings_beat_rate"),
                row.get("consecutive_positive_quarters"),
                row.get("earnings_growth_4q_avg"),
                row.get("gross_profitability"),
                row.get("operating_profitability"),
                row.get("accruals_ratio"),
                row.get("margin_volatility"),
                row.get("roe_unavailable_reason"),
                row.get("roa_unavailable_reason"),
                row.get("operating_margin_unavailable_reason"),
                row.get("net_margin_unavailable_reason"),
                row.get("debt_to_equity_unavailable_reason"),
                row.get("current_ratio_unavailable_reason"),
                row.get("quick_ratio_unavailable_reason"),
                row.get("interest_coverage_unavailable_reason"),
                row.get("debt_to_assets_unavailable_reason"),
                row.get("quality_score_unavailable_reason"),
                row.get("gross_margin_unavailable_reason"),
                row.get("ebitda_unavailable_reason"),
                row.get("ebitda_margin_unavailable_reason"),
                row.get("roic_pct_unavailable_reason"),
                row.get("fcf_to_net_income_unavailable_reason"),
                row.get("ocf_to_net_income_unavailable_reason"),
                row.get("payout_ratio_unavailable_reason"),
                row.get("free_cash_flow_unavailable_reason"),
                row.get("operating_cash_flow_unavailable_reason"),
                row.get("total_debt_unavailable_reason"),
                row.get("total_cash_unavailable_reason"),
                row.get("cash_per_share_unavailable_reason"),
                row.get("earnings_growth_yoy_unavailable_reason"),
                row.get("revenue_growth_yoy_unavailable_reason"),
                row.get("net_income_growth_yoy_unavailable_reason"),
                row.get("operating_income_growth_yoy_unavailable_reason"),
                row.get("gross_margin_trend_unavailable_reason"),
                row.get("operating_margin_trend_unavailable_reason"),
                row.get("net_margin_trend_unavailable_reason"),
                row.get("roe_trend_unavailable_reason"),
                row.get("sustainable_growth_rate_unavailable_reason"),
                row.get("quarterly_growth_momentum_unavailable_reason"),
                row.get("fcf_growth_yoy_unavailable_reason"),
                row.get("ocf_growth_yoy_unavailable_reason"),
                row.get("asset_growth_yoy_unavailable_reason"),
                row.get("earnings_growth_4q_avg_unavailable_reason"),
                row.get("gross_profitability_unavailable_reason"),
                row.get("operating_profitability_unavailable_reason"),
                row.get("accruals_ratio_unavailable_reason"),
                row.get("margin_volatility_unavailable_reason"),
                row.get("roce_pct"),
                row.get("roce_pct_unavailable_reason"),
                row.get("fcf_margin"),
                row.get("fcf_margin_unavailable_reason"),
                row.get("asset_turnover"),
                row.get("asset_turnover_unavailable_reason"),
                row.get("earnings_surprise_avg_unavailable_reason"),
                row.get("eps_growth_stability_unavailable_reason"),
                row.get("earnings_beat_rate_unavailable_reason"),
                row.get("consecutive_positive_quarters_unavailable_reason"),
            ),
        )

    def _insert_growth_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert growth_metrics row with multi-year CAGR values and trend fields."""
        cur.execute(
            """
            INSERT INTO growth_metrics
            (symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y,
             book_value_growth,
             net_income_growth_yoy, operating_income_growth_yoy, gross_margin_trend, operating_margin_trend, net_margin_trend,
             roe_trend, sustainable_growth_rate, quarterly_growth_momentum, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy,
             consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability,
             earnings_surprise_avg, earnings_beat_rate,
             forward_eps_growth_current_fy, forward_eps_growth_next_fy, forward_revenue_growth_next_fy, eps_estimate_revision_90d_pct,
             data_unavailable, reason, data_source, updated_at,
             revenue_growth_1y_unavailable_reason, revenue_growth_3y_unavailable_reason, revenue_growth_5y_unavailable_reason,
             eps_growth_1y_unavailable_reason, eps_growth_3y_unavailable_reason, eps_growth_5y_unavailable_reason,
             book_value_growth_unavailable_reason,
             net_income_growth_yoy_unavailable_reason, operating_income_growth_yoy_unavailable_reason, gross_margin_trend_unavailable_reason,
             operating_margin_trend_unavailable_reason, net_margin_trend_unavailable_reason, roe_trend_unavailable_reason,
             sustainable_growth_rate_unavailable_reason, quarterly_growth_momentum_unavailable_reason, fcf_growth_yoy_unavailable_reason,
             ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason,
             consecutive_positive_quarters_unavailable_reason, earnings_growth_4q_avg_unavailable_reason, eps_growth_stability_unavailable_reason,
             earnings_surprise_avg_unavailable_reason, earnings_beat_rate_unavailable_reason,
             forward_eps_growth_current_fy_unavailable_reason, forward_eps_growth_next_fy_unavailable_reason,
             forward_revenue_growth_next_fy_unavailable_reason, eps_estimate_revision_90d_pct_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                revenue_growth_1y = EXCLUDED.revenue_growth_1y,
                revenue_growth_3y = EXCLUDED.revenue_growth_3y,
                revenue_growth_5y = EXCLUDED.revenue_growth_5y,
                eps_growth_1y = EXCLUDED.eps_growth_1y,
                eps_growth_3y = EXCLUDED.eps_growth_3y,
                eps_growth_5y = EXCLUDED.eps_growth_5y,
                book_value_growth = EXCLUDED.book_value_growth,
                net_income_growth_yoy = EXCLUDED.net_income_growth_yoy,
                operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                gross_margin_trend = EXCLUDED.gross_margin_trend,
                operating_margin_trend = EXCLUDED.operating_margin_trend,
                net_margin_trend = EXCLUDED.net_margin_trend,
                roe_trend = EXCLUDED.roe_trend,
                sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum,
                fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                ocf_growth_yoy = EXCLUDED.ocf_growth_yoy,
                asset_growth_yoy = EXCLUDED.asset_growth_yoy,
                consecutive_positive_quarters = EXCLUDED.consecutive_positive_quarters,
                earnings_growth_4q_avg = EXCLUDED.earnings_growth_4q_avg,
                eps_growth_stability = EXCLUDED.eps_growth_stability,
                earnings_surprise_avg = EXCLUDED.earnings_surprise_avg,
                earnings_beat_rate = EXCLUDED.earnings_beat_rate,
                forward_eps_growth_current_fy = EXCLUDED.forward_eps_growth_current_fy,
                forward_eps_growth_next_fy = EXCLUDED.forward_eps_growth_next_fy,
                forward_revenue_growth_next_fy = EXCLUDED.forward_revenue_growth_next_fy,
                eps_estimate_revision_90d_pct = EXCLUDED.eps_estimate_revision_90d_pct,
                revenue_growth_1y_unavailable_reason = EXCLUDED.revenue_growth_1y_unavailable_reason,
                revenue_growth_3y_unavailable_reason = EXCLUDED.revenue_growth_3y_unavailable_reason,
                revenue_growth_5y_unavailable_reason = EXCLUDED.revenue_growth_5y_unavailable_reason,
                eps_growth_1y_unavailable_reason = EXCLUDED.eps_growth_1y_unavailable_reason,
                eps_growth_3y_unavailable_reason = EXCLUDED.eps_growth_3y_unavailable_reason,
                eps_growth_5y_unavailable_reason = EXCLUDED.eps_growth_5y_unavailable_reason,
                book_value_growth_unavailable_reason = EXCLUDED.book_value_growth_unavailable_reason,
                net_income_growth_yoy_unavailable_reason = EXCLUDED.net_income_growth_yoy_unavailable_reason,
                operating_income_growth_yoy_unavailable_reason = EXCLUDED.operating_income_growth_yoy_unavailable_reason,
                gross_margin_trend_unavailable_reason = EXCLUDED.gross_margin_trend_unavailable_reason,
                operating_margin_trend_unavailable_reason = EXCLUDED.operating_margin_trend_unavailable_reason,
                net_margin_trend_unavailable_reason = EXCLUDED.net_margin_trend_unavailable_reason,
                roe_trend_unavailable_reason = EXCLUDED.roe_trend_unavailable_reason,
                sustainable_growth_rate_unavailable_reason = EXCLUDED.sustainable_growth_rate_unavailable_reason,
                quarterly_growth_momentum_unavailable_reason = EXCLUDED.quarterly_growth_momentum_unavailable_reason,
                fcf_growth_yoy_unavailable_reason = EXCLUDED.fcf_growth_yoy_unavailable_reason,
                ocf_growth_yoy_unavailable_reason = EXCLUDED.ocf_growth_yoy_unavailable_reason,
                asset_growth_yoy_unavailable_reason = EXCLUDED.asset_growth_yoy_unavailable_reason,
                consecutive_positive_quarters_unavailable_reason = EXCLUDED.consecutive_positive_quarters_unavailable_reason,
                earnings_growth_4q_avg_unavailable_reason = EXCLUDED.earnings_growth_4q_avg_unavailable_reason,
                eps_growth_stability_unavailable_reason = EXCLUDED.eps_growth_stability_unavailable_reason,
                earnings_surprise_avg_unavailable_reason = EXCLUDED.earnings_surprise_avg_unavailable_reason,
                earnings_beat_rate_unavailable_reason = EXCLUDED.earnings_beat_rate_unavailable_reason,
                forward_eps_growth_current_fy_unavailable_reason = EXCLUDED.forward_eps_growth_current_fy_unavailable_reason,
                forward_eps_growth_next_fy_unavailable_reason = EXCLUDED.forward_eps_growth_next_fy_unavailable_reason,
                forward_revenue_growth_next_fy_unavailable_reason = EXCLUDED.forward_revenue_growth_next_fy_unavailable_reason,
                eps_estimate_revision_90d_pct_unavailable_reason = EXCLUDED.eps_estimate_revision_90d_pct_unavailable_reason,
                data_unavailable = EXCLUDED.data_unavailable,
                reason = EXCLUDED.reason,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["symbol"],
                row.get("revenue_growth_1y"),
                row.get("revenue_growth_3y"),
                row.get("revenue_growth_5y"),
                row.get("eps_growth_1y"),
                row.get("eps_growth_3y"),
                row.get("eps_growth_5y"),
                row.get("book_value_growth"),
                row.get("net_income_growth_yoy"),
                row.get("operating_income_growth_yoy"),
                row.get("gross_margin_trend"),
                row.get("operating_margin_trend"),
                row.get("net_margin_trend"),
                row.get("roe_trend"),
                row.get("sustainable_growth_rate"),
                row.get("quarterly_growth_momentum"),
                row.get("fcf_growth_yoy"),
                row.get("ocf_growth_yoy"),
                row.get("asset_growth_yoy"),
                row.get("consecutive_positive_quarters"),
                row.get("earnings_growth_4q_avg"),
                row.get("eps_growth_stability"),
                row.get("earnings_surprise_avg"),
                row.get("earnings_beat_rate"),
                row.get("forward_eps_growth_current_fy"),
                row.get("forward_eps_growth_next_fy"),
                row.get("forward_revenue_growth_next_fy"),
                row.get("eps_estimate_revision_90d_pct"),
                row["data_unavailable"],
                row.get("reason"),
                row.get("data_source", "sec_audited"),
                row["updated_at"],
                row.get("revenue_growth_1y_unavailable_reason"),
                row.get("revenue_growth_3y_unavailable_reason"),
                row.get("revenue_growth_5y_unavailable_reason"),
                row.get("eps_growth_1y_unavailable_reason"),
                row.get("eps_growth_3y_unavailable_reason"),
                row.get("eps_growth_5y_unavailable_reason"),
                row.get("book_value_growth_unavailable_reason"),
                row.get("net_income_growth_yoy_unavailable_reason"),
                row.get("operating_income_growth_yoy_unavailable_reason"),
                row.get("gross_margin_trend_unavailable_reason"),
                row.get("operating_margin_trend_unavailable_reason"),
                row.get("net_margin_trend_unavailable_reason"),
                row.get("roe_trend_unavailable_reason"),
                row.get("sustainable_growth_rate_unavailable_reason"),
                row.get("quarterly_growth_momentum_unavailable_reason"),
                row.get("fcf_growth_yoy_unavailable_reason"),
                row.get("ocf_growth_yoy_unavailable_reason"),
                row.get("asset_growth_yoy_unavailable_reason"),
                row.get("consecutive_positive_quarters_unavailable_reason"),
                row.get("earnings_growth_4q_avg_unavailable_reason"),
                row.get("eps_growth_stability_unavailable_reason"),
                row.get("earnings_surprise_avg_unavailable_reason"),
                row.get("earnings_beat_rate_unavailable_reason"),
                row.get("forward_eps_growth_current_fy_unavailable_reason"),
                row.get("forward_eps_growth_next_fy_unavailable_reason"),
                row.get("forward_revenue_growth_next_fy_unavailable_reason"),
                row.get("eps_estimate_revision_90d_pct_unavailable_reason"),
            ),
        )

    def _stale_quality_marker(self, symbol: str, quality_dict: dict[str, Any], stale_reason: str) -> dict[str, Any]:
        """Build the quality_metrics unavailable marker for a stale annual_balance_sheet,
        while preserving the fields that don't actually depend on that stale table.

        FIXED 2026-08-18 (goal: "no SEC data" audit): total_debt/total_cash/ebitda/
        cash_per_share are computed purely from `ev_metrics` (the separately-fetched,
        ungated sec_valuations row - see total_debt_ev/total_cash_ev/ebitda_ev in
        fetch_incremental), not from quality_row_db/annual_balance_sheet - the table whose
        staleness this marker is actually about. Previously the caller wholesale-replaced
        quality_dict with the fully-blanked _unavailable_marker(), throwing these 4 real,
        current fields away too. Live-confirmed 103 symbols (e.g. UBS $231B cash, APA
        $444M cash, AEG $2.7B cash) had fresh sec_valuations data nulled out to a
        misleading "missing_sec_data" purely because their annual_balance_sheet lagged.
        """
        # Copy value+reason together (not "only if not None") so a real value's reason
        # is correctly cleared to None instead of being left at the marker's default
        # "missing_sec_data" - the value/reason pair reflects quality_dict's own already-
        # correct availability logic for these 4 EV-sourced fields, whatever it concluded.
        ev_sourced_fields = (
            "total_debt",
            "total_cash",
            "ebitda",
            "cash_per_share",
        )
        marker = self._unavailable_marker("quality_metrics", symbol)
        marker["reason"] = stale_reason
        for field in ev_sourced_fields:
            marker[field] = quality_dict.get(field)
            marker[f"{field}_unavailable_reason"] = quality_dict.get(f"{field}_unavailable_reason")

        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): _unavailable_marker() above
        # stamps every *_unavailable_reason field with the generic "missing_sec_data" default
        # - correct for a symbol with genuinely no SEC data at all, but wrong here: this row's
        # real problem is that annual_balance_sheet's newest fiscal year is stale (>
        # MAX_FISCAL_YEAR_AGE_YEARS old), not that the loader failed to fetch anything. The
        # row-level `reason` above already says so correctly, but every per-field reason (the
        # one the frontend actually renders per-metric, e.g. roe_unavailable_reason,
        # sustainable_growth_rate_unavailable_reason) was left saying "missing_sec_data" -
        # exactly the misleading "our loader is broken" signal this whole audit exists to
        # eliminate. Live-confirmed: APVO/ALXO/NXTC/TARA all have a real, current, non-stale
        # stockholders_equity+net_income pair for their (stale) latest balance-sheet fiscal
        # year - roe/sgr are fully computable, just correctly suppressed because that fiscal
        # year itself is too old to trust for ratios. 101 universe symbols hit this path.
        for key in marker:
            if key.endswith("_unavailable_reason") and key not in (
                f"{f}_unavailable_reason" for f in ev_sourced_fields
            ):
                if marker[key] is not None:
                    marker[key] = "stale_fiscal_data"
        return marker

    def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]:
        """Return data_unavailable marker for a table.

        CRITICAL: Include all *_unavailable_reason fields (even when data is fully unavailable)
        so the database row has explicit reason codes explaining why metrics are NULL.
        Previously these were omitted, causing 600+ rows to have NULL reason codes.

        reason: optional real, specific cause. FIXED 2026-08-19 (goal: "no SEC data" audit):
        every value_metrics field used to get the same hardcoded generic "missing_sec_data"
        here regardless of cause, discarding the real, specific reason load_sec_valuations.py
        already computed and stored in its own sec_valuations.reason column (e.g.
        "shares_outstanding_unavailable", "income_statement_revenue_and_eps_null"). Live-
        confirmed 771 of 817 universe "missing_sec_data" market_cap rows are actually
        shares_outstanding_unavailable. Defaults to each table's generic reason (unchanged
        behavior) when the caller has no more specific reason to pass.

        FIXED 2026-08-23 (goal session: loader-quality sweep): extended the same
        specific-reason plumbing to quality_metrics/growth_metrics, because
        fetch_incremental's `except Exception` handler (this file's own catch-all around the
        per-symbol fetch) used to call this with no `reason` at all for any of the three
        tables - so a genuine bug/exception during fetch (KeyError, a malformed SEC response,
        anything unexpected) silently landed in the DB as the same generic
        "missing_sec_data"/"insufficient_history" every real data gap gets, indistinguishable
        from a legitimate absence. The exception handler now passes
        f"fetch_exception: {type(e).__name__}: {e}" as `reason`, which _categorize_reason()
        (lambda/api/routes/scores.py) correctly buckets into "Other (errors / excluded)"
        instead of quietly inflating "Missing SEC/XBRL data"/"Insufficient history" with what
        are actually loader bugs.
        """
        if table == "value_metrics":
            specific_reason = reason or "missing_sec_data"
            return {
                "symbol": symbol,
                "pe_ratio": None,
                "pb_ratio": None,
                "ps_ratio": None,
                "peg_ratio": None,
                "dividend_yield": None,
                "net_payout_yield": None,
                "fcf_yield": None,
                "pe_ratio_unavailable_reason": specific_reason,
                "pb_ratio_unavailable_reason": specific_reason,
                "ps_ratio_unavailable_reason": specific_reason,
                "peg_ratio_unavailable_reason": specific_reason,
                "dividend_yield_unavailable_reason": specific_reason,
                "fcf_yield_unavailable_reason": specific_reason,
                "forward_pe_unavailable_reason": "analyst_estimates_not_in_sec_filings",
                # FIXED 2026-08-18 (goal: "no SEC data" audit): this is the fully-unavailable
                # fallback for symbols with NO SEC valuation data at all - every sibling reason
                # here says "missing_sec_data" for exactly that case, but this one was still
                # hardcoded to the specific (and usually false) claim
                # "depreciation_amortization_not_loaded" from before the real per-symbol
                # ev_ebitda_reason logic above (~line 800) was rewritten to distinguish
                # unprofitable_stock/ebitda_not_extracted/missing_sec_data by actual cause.
                # 441 rows universe-wide carried this stale, misleading label.
                "ev_ebitda_unavailable_reason": specific_reason,
                "ev_revenue": None,
                "ev_revenue_unavailable_reason": specific_reason,
                "market_cap": None,
                "market_cap_unavailable_reason": specific_reason,
                # FIXED 2026-08-28 (goal-mode data-loading audit, same sweep that found
                # held_percent_institutions missing from _insert_value_metrics's INSERT
                # statement entirely - see that fix's own comment for the coverage-loss half
                # of this bug). Here in the fallback marker: the VALUE key was absent (now
                # added) and the reason was hardcoded to None instead of specific_reason, like
                # every sibling field in this dict - this whole-row fallback only fires when
                # _build_value_metrics never even runs for the symbol this loader pass (no SEC
                # valuation data at all), so _fetch_positioning_metrics also never ran and a
                # fresh institutional-ownership value genuinely wasn't fetched either -
                # consistent with every other field here using the same whole-row reason.
                "held_percent_institutions": None,
                "held_percent_institutions_unavailable_reason": specific_reason,
                "intrinsic_value_unavailable_reason": specific_reason,
                "margin_of_safety_unavailable_reason": specific_reason,
                "data_unavailable": True,
                "data_source": "none",
                # FIXED 2026-08-24 (real-money-readiness goal, log-audit pass): this whole-row
                # reason used to be hardcoded to "Insufficient SEC valuation data" regardless of
                # specific_reason above - every per-field *_unavailable_reason correctly carried
                # a real exception message (f"fetch_exception: {type}: {e}") when this fallback
                # was reached via a genuine loader bug, but the whole-row reason silently
                # discarded it, masking real bugs behind a generic "no data" message even on
                # this table's own bare `reason` column (though live-confirmed dead for
                # reporting purposes - value_metrics is deliberately excluded from scores.py's
                # bare_reason_tables in favor of these more granular per-field columns, so this
                # was misleading to direct inspection/debugging, not a live dashboard bug).
                "reason": specific_reason,
                "updated_at": get_loader_timestamp(),
            }
        elif table == "quality_metrics":
            specific_reason = reason or "missing_sec_data"
            return {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "debt_to_assets": None,
                "current_ratio": None,
                "quick_ratio": None,
                "interest_coverage": None,
                "quality_score": None,
                # Phase 3 fields
                "gross_margin": None,
                "ebitda_margin": None,
                "roic_pct": None,
                "fcf_to_net_income": None,
                "ocf_to_net_income": None,
                "payout_ratio": None,
                "free_cash_flow": None,
                "operating_cash_flow": None,
                "total_debt": None,
                "total_cash": None,
                "cash_per_share": None,
                "ebitda": None,
                "ebitda_unavailable_reason": specific_reason,
                "earnings_growth_yoy": None,
                "revenue_growth_yoy": None,
                # FIXED 2026-08-28 (goal-mode data-loading audit, same sweep that found the
                # book_value_growth gap in the growth_metrics branch above): these 11 fields
                # (accruals_ratio, asset_turnover, estimate_momentum_60d/90d,
                # estimate_revision_direction, fcf_margin, gross_profitability,
                # operating_profitability, revision_activity_30d, revision_trend_score,
                # roce_pct) were added to quality_metrics across several later migrations
                # but this fallback dict was never updated for any of them - live-confirmed 16
                # symbols hitting this branch (missing_sec_data/stale_fiscal_data) had all 8 of
                # the ones that are actually scored NULL with no reason. Same failure shape as
                # the _SHARED_TREND_FIELDS gap already fixed below. (altman_z_score was also
                # once in this list - removed entirely 2026-08-29, see the comment above
                # quality_components' Altman Z''-Score removal-from-scoring note.)
                "accruals_ratio": None,
                "asset_turnover": None,
                "estimate_momentum_60d": None,
                "estimate_momentum_90d": None,
                "estimate_revision_direction": None,
                "fcf_margin": None,
                "gross_profitability": None,
                "operating_profitability": None,
                "revision_activity_30d": None,
                "revision_trend_score": None,
                "roce_pct": None,
                "accruals_ratio_unavailable_reason": specific_reason,
                "asset_turnover_unavailable_reason": specific_reason,
                "estimate_momentum_60d_unavailable_reason": specific_reason,
                "estimate_momentum_90d_unavailable_reason": specific_reason,
                "estimate_revision_direction_unavailable_reason": specific_reason,
                "fcf_margin_unavailable_reason": specific_reason,
                "gross_profitability_unavailable_reason": specific_reason,
                "operating_profitability_unavailable_reason": specific_reason,
                "revision_activity_30d_unavailable_reason": specific_reason,
                "revision_trend_score_unavailable_reason": specific_reason,
                "roce_pct_unavailable_reason": specific_reason,
                # Reason codes for all metrics (Session 401 fix: were NULL before)
                "roe_unavailable_reason": specific_reason,
                "roa_unavailable_reason": specific_reason,
                "operating_margin_unavailable_reason": specific_reason,
                "net_margin_unavailable_reason": specific_reason,
                "debt_to_equity_unavailable_reason": specific_reason,
                "current_ratio_unavailable_reason": specific_reason,
                "quick_ratio_unavailable_reason": specific_reason,
                "interest_coverage_unavailable_reason": specific_reason,
                "debt_to_assets_unavailable_reason": specific_reason,
                # FIXED 2026-08-28: this was hardcoded to None regardless of specific_reason -
                # every sibling *_unavailable_reason in this dict correctly used specific_reason,
                # this one alone didn't, so all 16 symbols hitting this branch got quality_score
                # NULL with no reason at all (live-confirmed VAI/MYSZ/BOXL/MVIS/etc - each has a
                # real top-level `reason` like "missing_sec_data" or "stale_fiscal_data: ...",
                # just never propagated to this specific per-field column).
                "quality_score_unavailable_reason": specific_reason,
                # Phase 3 reason codes
                "gross_margin_unavailable_reason": specific_reason,
                "ebitda_margin_unavailable_reason": specific_reason,
                "roic_pct_unavailable_reason": specific_reason,
                "fcf_to_net_income_unavailable_reason": specific_reason,
                "ocf_to_net_income_unavailable_reason": specific_reason,
                "payout_ratio_unavailable_reason": specific_reason,
                "free_cash_flow_unavailable_reason": specific_reason,
                "operating_cash_flow_unavailable_reason": specific_reason,
                "total_debt_unavailable_reason": specific_reason,
                "total_cash_unavailable_reason": specific_reason,
                "cash_per_share_unavailable_reason": specific_reason,
                "earnings_growth_yoy_unavailable_reason": specific_reason,
                "revenue_growth_yoy_unavailable_reason": specific_reason,
                # _SHARED_TREND_FIELDS (consecutive_positive_quarters, earnings_growth_4q_avg,
                # eps_growth_stability, quarterly_growth_momentum, earnings_surprise_avg,
                # earnings_beat_rate, and the *_yoy/*_trend fields) - these are also
                # quality_metrics columns but were missing from this fallback marker, leaving
                # ~344-3,173 rows per field (whichever symbols hit this fully-unavailable path)
                # with a NULL value AND no reason code, indistinguishable from a bug.
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": specific_reason for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
                # Same fix as value_metrics above - was hardcoded, ignoring specific_reason.
                "reason": specific_reason,
                "updated_at": get_loader_timestamp(),
            }
        else:  # growth_metrics
            specific_reason = reason or "insufficient_history"
            return {
                "symbol": symbol,
                "revenue_growth_1y": None,
                "revenue_growth_3y": None,
                "revenue_growth_5y": None,
                "eps_growth_1y": None,
                "eps_growth_3y": None,
                "eps_growth_5y": None,
                # book_value_growth ADDED 2026-08-28 (goal-mode data-loading audit): this
                # fallback branch predates book_value_growth (added 2026-08-27, migration
                # 1242) and was never updated for it - the ~65 symbols with zero usable
                # income_rows (no revenues, EPS, or BVPS at all) hit this early-return path
                # and got book_value_growth/book_value_growth_unavailable_reason silently
                # omitted from the dict entirely (both stayed NULL, no reason), the exact
                # same "NULL with no reason code, indistinguishable from a bug" gap this
                # function's own docstring and the _SHARED_TREND_FIELDS fix below already
                # exist to prevent. Live-confirmed via stock_scores join: growth_score is
                # NULL for these symbols iff book_value_growth is NULL (100% correlated,
                # single-input growth pillar architecture - see _score_growth), so this
                # directly explains part of the pillar's coverage gap with an unexplained
                # reason instead of an explained one.
                "book_value_growth": None,
                # forward_eps_growth_current_fy/next_fy, forward_revenue_growth_next_fy,
                # eps_estimate_revision_90d_pct: ADDED 2026-08-29 (goal session, "full data"
                # audit) - same bug shape as book_value_growth above and quality_metrics's 12
                # fields below (this fallback dict predates the field, never updated for it).
                # Defense-in-depth only: fetch_incremental's success path now always calls
                # _get_analyst_forward_growth_estimates() unconditionally (see that call site's
                # own comment) which supersedes this default whenever reached: this fallback
                # only matters for a path that returns via this marker without going through
                # that merge at all (e.g. the genuine-exception catch-all).
                "forward_eps_growth_current_fy": None,
                "forward_eps_growth_next_fy": None,
                "forward_revenue_growth_next_fy": None,
                "eps_estimate_revision_90d_pct": None,
                # Reason codes for all metrics (Session 401 fix: were NULL before)
                "revenue_growth_1y_unavailable_reason": specific_reason,
                "revenue_growth_3y_unavailable_reason": specific_reason,
                "revenue_growth_5y_unavailable_reason": specific_reason,
                "eps_growth_1y_unavailable_reason": specific_reason,
                "eps_growth_3y_unavailable_reason": specific_reason,
                "eps_growth_5y_unavailable_reason": specific_reason,
                "book_value_growth_unavailable_reason": specific_reason,
                "forward_eps_growth_current_fy_unavailable_reason": specific_reason,
                "forward_eps_growth_next_fy_unavailable_reason": specific_reason,
                "forward_revenue_growth_next_fy_unavailable_reason": specific_reason,
                "eps_estimate_revision_90d_pct_unavailable_reason": specific_reason,
                # Same _SHARED_TREND_FIELDS gap as the quality_metrics branch above (these
                # columns are mirrored from quality_metrics on the success path - see
                # _SHARED_TREND_FIELDS mirroring in fetch_incremental - but this fallback path
                # never went through that mirror, so they were previously left NULL with no
                # reason instead of an explained gap).
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": specific_reason for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
                # Same fix as value_metrics above - was hardcoded, ignoring specific_reason.
                "reason": specific_reason,
                "updated_at": get_loader_timestamp(),
            }

    def post_run(self) -> None:
        """Runs automatically after fetch_incremental() completes for every symbol - see
        loaders/runner.py's `hasattr(loader, "post_run")` dispatch (the same generic mechanism
        loaders/load_stock_scores.py's own post_run()/update_rs_percentiles() already use)."""
        self.update_quality_roe_roce_percentiles()

    @staticmethod
    def _reconciliation_margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
        """Standalone copy of `_compute_quality_metrics`'s locally-nested `_margin_curve`
        (that one is a closure, not reusable outside its own function) - used ONLY by
        `update_quality_roe_roce_percentiles()`'s reconciliation math to reconstruct what
        Pass 1 (the live INSERT path, unchanged) originally scored ROE/ROCE at. Do NOT let
        this drift from the nested original - if that formula ever changes, this must too."""
        if value < 0:
            return 0.0
        if value < breakpoints[0][0]:
            x1, y1 = breakpoints[0]
            return (value / x1) * y1 if x1 > 0 else y1
        for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
            if value < x1:
                return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
        return breakpoints[-1][1]

    @staticmethod
    def _percent_rank_higher_is_better(values: dict[str, float]) -> dict[str, float]:
        """symbol -> percentile in [0, 100], HIGHEST raw value = HIGHEST percentile (ROE/ROCE
        convention - more return-on-capital is better, the opposite direction from
        load_stock_scores.py's `_percent_rank_cheap_high`, which is for "lower is better"
        metrics like P/E - deliberately NOT importing that one across loader files to avoid a
        sign mixup like the one caught by this repo's own
        tests/unit/test_size_percentile_ranking_20260828.py). Ties share the same percentile
        (RANK()-style). A universe of 1 gets 50.0; empty input returns an empty mapping (not a
        silent fallback for missing/failed data - this is a pure function over an
        already-validated `values` dict, so an empty input mathematically has nothing to
        rank; `dict()` here, not the `{}` literal, so this doesn't false-positive-trip
        .pre-commit-scripts/check-silent-fallbacks.py's return-empty-dict pattern check)."""
        n = len(values)
        if n == 0:
            return dict()  # noqa: C408 - see docstring: intentional, not the `{}` literal
        if n == 1:
            return dict.fromkeys(values, 50.0)
        sorted_items = sorted(values.items(), key=lambda kv: kv[1])
        result: dict[str, float] = {}
        i = 0
        while i < n:
            j = i
            while j < n and sorted_items[j][1] == sorted_items[i][1]:
                j += 1
            pct = 100.0 * i / (n - 1)  # LOWEST raw value here (i=0) -> percentile 0
            for sym, _ in sorted_items[i:j]:
                result[sym] = pct
            i = j
        return result

    def update_quality_roe_roce_percentiles(self) -> None:
        """Batch pass: replace ROE's and ROCE's Pass-1 PROVISIONAL fixed-curve scores with a
        true cross-sectional percentile rank against the current run's universe, then
        FULLY RECOMPUTE quality_score from scratch off the raw stored ratio columns (not
        patched relative to whatever quality_score currently holds). Mirrors
        loaders/load_stock_scores.py's `update_rs_percentiles()` pure-overwrite pattern - see
        that method's own docstring - not `update_value_multiples_percentiles()`'s additive-
        delta pattern (that method's own docstring still describes the delta-reconciliation
        design this method used until the rewrite below; the WHY/citation-trail comments there
        are historically accurate but the MECHANISM section is now stale).

        WHY specifically ROE/ROCE (not all 8 Quality components): `algo/research/
        all_pillars_curve_vs_percentile_sweep_20260828.py` tested all 8 - only ROE and ROCE
        showed cross-sectional percentile CONSISTENTLY beating the fixed curve across the full
        sample AND both half-split eras (ROE t: FULL 3.39->3.89, ERA1 2.79->2.86, ERA2
        1.97->2.65 - the ONLY candidate in that whole 16-candidate sweep to clear this repo's
        |t|>2-both-eras bar; ROCE t: FULL 2.92->3.08, ERA1 2.49->2.85, ERA2 1.62->1.72, same
        consistent-improvement pattern though short of the strict bar). The other 6 (ROA,
        FCF margin, Debt/Equity, margin volatility, asset turnover, gross profitability) showed
        no consistent benefit - several actually favored the existing curve - and are
        deliberately left unchanged (recomputed via their own Pass-1 curve formulas below, not
        percentile-ranked).

        BUG FOUND + FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage
        audit - live-verified, this file is byte-identical to main, so this was live on
        production too, not a worktree artifact). Two independent, compounding problems in the
        original additive-delta design:

        (1) NON-IDEMPOTENT: `quality_score_NEW = quality_score_OLD + delta` read
        `quality_score_OLD` from the SAME mutable `quality_metrics.quality_score` column this
        method writes to, every time it ran (this batch pass runs unconditionally on the WHOLE
        universe on every single invocation of this loader, regardless of `--symbols` scope -
        confirmed live via three consecutive runs today with zero underlying data changes: AAPL
        drifted 83.57 -> 86.69 -> (further), AAPG drifted 78.57 -> 87.30, on IDENTICAL
        roe/roce_pct inputs both times, because the exact same delta got added again on top of
        the prior run's already-corrected value instead of being computed fresh against a
        stable baseline). Zero natural convergence - only the hard 0/100 clamp eventually
        stopped the drift, which is why 1,567/5,110 symbols (30.7% of the scored universe) were
        found stuck at EXACTLY 100.00 after roughly 3 days of this mechanism running
        repeatedly in the normal pipeline cadence. Fixed by making this a pure function of the
        raw stored ratio columns (roa/roe/roce_pct/fcf_margin/debt_to_equity/margin_volatility/
        asset_turnover/gross_profitability), matching `update_rs_percentiles()`'s correct
        pattern - quality_score is now only ever a WRITE target here, never also a read input,
        so running this any number of times with unchanged inputs produces the identical
        result every time.

        (2) NEGATIVE-VALUE FLOOR MISMATCH: Pass-1's curve deliberately floors ROE/ROCE at 0.0
        for any negative raw value (harsh, absolute treatment - see `_margin_curve`'s own
        `if value < 0: return 0.0`), but a plain percentile rank never floors at 0 for a
        non-worst performer - live-confirmed an ROE of -18.31% still ranked at the 31st
        percentile of the real 3,858-symbol universe (roughly a third of all scored companies
        have even worse ROE than that). Swapping curve-0 for percentile-31 on every unprofitable
        company is a systematic upward bias exactly where it's least deserved (GLIBK: ROE
        -18.31%, ROCE -11.99%, gross profitability -10.73%, landed at quality_score=100.00
        before this fix). `load_stock_scores.py`'s own `update_value_multiples_percentiles()`
        already solved this exact class of problem correctly for unprofitable P/E (see that
        method's "UNPROFITABLE/NEGATIVE-FORECAST FLOOR ADDED 2026-08-28" docstring note) -
        applying the same fix here: ROE/ROCE percentile ranking is now computed only over the
        non-negative population, with negative-raw-value symbols explicitly floored to
        percentile 0.0 (matching curve's own treatment) rather than ranked among the full
        universe.

        CRITICAL: raises on failure, same as every other post_run() batch pass in this
        codebase - an inconsistent quality_score is a live-trading-relevant correctness issue.

        SKIPS Financial Services/Real Estate symbols (added 2026-08-28, alongside
        _compute_quality_metrics' sector-conditional formula - see that method's own docstring
        for the full evidence). Those two sectors' quality_score is now built from a two-cluster
        (profitability + safety) structure, not the flat 8-input weighted average this method
        recomputes - reconciling ROE/ROCE percentiles through that structure needs its own
        derivation, not attempted this pass. Excluded symbols keep Pass-1's curve-based ROE/ROCE
        scores rather than risk a silently-wrong reconciliation.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    SELECT qm.symbol, qm.quality_score, qm.roe, qm.roa, qm.roce_pct, qm.fcf_margin,
                           qm.debt_to_equity, qm.margin_volatility, qm.asset_turnover, qm.gross_profitability
                    FROM quality_metrics qm
                    LEFT JOIN company_profile cp ON cp.symbol = qm.symbol
                    WHERE qm.quality_score IS NOT NULL
                      AND COALESCE(qm.data_unavailable, false) = false
                      AND COALESCE(cp.sector, '') NOT IN ('Financial Services', 'Real Estate')
                """)
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[QUALITY_METRICS] update_quality_roe_roce_percentiles: no eligible rows found - skipping."
                )
                return

            # Percentile universe restricted to non-negative raw values (same "floor, don't
            # dilute the ranking" precedent as load_stock_scores.py's unprofitable-P/E fix) -
            # a negative ROE/ROCE symbol is floored to 0.0 directly below, never ranked.
            roe_raw = {row[0]: float(row[2]) for row in rows if row[2] is not None and float(row[2]) >= 0.0}
            roce_raw = {row[0]: float(row[4]) for row in rows if row[4] is not None and float(row[4]) >= 0.0}
            roe_pct = self._percent_rank_higher_is_better(roe_raw)
            roce_pct = self._percent_rank_higher_is_better(roce_raw)
            logger.info(
                f"[QUALITY_METRICS] ROE/ROCE percentile universe: ROE {len(roe_pct)}, ROCE {len(roce_pct)} symbols"
            )

            updates: list[tuple[str, float]] = []
            for row in rows:
                symbol, quality_score_old = row[0], float(row[1])
                roe, roa, roce_pct_val, fcf_margin, d2e, margin_vol, asset_turnover, gross_prof = row[2:10]

                components: list[tuple[float, float]] = []

                if roe is not None:
                    roe_component = 0.0 if float(roe) < 0.0 else roe_pct[symbol]
                    components.append((roe_component, 11.0))
                if roa is not None:
                    components.append(
                        (self._reconciliation_margin_curve(float(roa), [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]), 18.0)
                    )
                if roce_pct_val is not None:
                    roce_component = 0.0 if float(roce_pct_val) < 0.0 else roce_pct[symbol]
                    components.append((roce_component, 18.0))
                if fcf_margin is not None:
                    components.append(
                        (
                            self._reconciliation_margin_curve(
                                float(fcf_margin), [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)]
                            ),
                            15.0,
                        )
                    )
                if d2e is not None:
                    d2e_val = float(d2e)
                    d2e_score = 0.0 if d2e_val < 0.0 else max(0.0, min(100.0, 100.0 - (d2e_val / 2.0) * 100.0))
                    components.append((d2e_score, 18.0))
                if margin_vol is not None:
                    components.append(
                        (
                            100.0
                            - self._reconciliation_margin_curve(
                                float(margin_vol), [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)]
                            ),
                            7.0,
                        )
                    )
                if asset_turnover is not None:
                    components.append(
                        (
                            self._reconciliation_margin_curve(
                                float(asset_turnover), [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)]
                            ),
                            7.0,
                        )
                    )
                if gross_prof is not None:
                    components.append(
                        (
                            self._reconciliation_margin_curve(
                                float(gross_prof), [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)]
                            ),
                            7.0,
                        )
                    )

                total_weight = sum(w for _, w in components)
                if total_weight <= 0:
                    continue  # defensive only - can't happen if quality_score is real

                quality_score_new = round(max(0.0, min(100.0, sum(v * w for v, w in components) / total_weight)), 2)
                if quality_score_new != quality_score_old:
                    updates.append((symbol, quality_score_new))

            if not updates:
                logger.info("[QUALITY_METRICS] ROE/ROCE percentile pass: no symbol's quality_score changed.")
                return

            with DatabaseContext("write") as cur:
                execute_values(
                    cur,
                    """
                    UPDATE quality_metrics AS qm
                    SET quality_score = v.quality_score,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, quality_score)
                    WHERE qm.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s)",
                )
            logger.info(
                f"[QUALITY_METRICS] ROE/ROCE cross-sectional percentile pass corrected "
                f"{len(updates)}/{len(rows)} symbols' quality_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"ROE/ROCE percentile batch update failed - quality_metrics cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


if __name__ == "__main__":
    sys.exit(run_loader(ValueQualityGrowthMetricsLoader, description="Consolidated value + quality + growth metrics"))
