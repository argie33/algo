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

import logging
import sys
import time
from datetime import date, datetime, timezone
from math import isnan, sqrt
from typing import Any

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

# Sanity bound for absolute-dollar fields (free_cash_flow, operating_cash_flow, total_debt,
# total_cash, ebitda) - all stored in NUMERIC(15,2) columns (max abs value < 10^13, i.e.
# $10 trillion). Live-confirmed via the 2026-08-09 metrics pipeline run: VFS and KEP (both
# foreign filers reporting in local currency - VND/KRW) overflowed this column, aborting
# the entire 3-table quality/value/growth write transaction for those symbols - not just
# the one garbage field, the whole row, same failure mode as MAX_TREND_PERCENTAGE_POINTS
# above. Root cause not yet fixed (likely a missing currency-unit conversion for these
# filers, same class of bug as sec_statements.py's other foreign-filer fixes) - this bound
# only prevents the crash-and-lose-everything symptom by marking the implausible value
# unavailable instead of writing it.
MAX_ABSOLUTE_DOLLAR_VALUE = 1_000_000_000_000.0  # $1 trillion - no real company in this universe exceeds this for any single one of these fields

# Computed once in _compute_quality_metrics (needs balance-sheet data _compute_growth_metrics
# doesn't have), then mirrored into growth_dict in fetch_incremental - see that call site for
# why quality_metrics and growth_metrics each carry their own copy of the same 11 values.
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
            }

        except Exception as e:
            logger.error(f"[VALUE_QUALITY_GROWTH FATAL] {type(e).__name__}: {e}", exc_info=True)
            error_msg = str(e)[:500]
            for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                manager = managers.get(table) or LoaderStatusManager(table)
                manager.mark_failed(error_msg)
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
                if sec_val_row:
                    cur.execute(
                        "SELECT total_debt, total_cash, ebitda FROM sec_valuations WHERE symbol = %s",
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
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_interest_expense
                    FROM annual_balance_sheet abs
                    LEFT JOIN annual_income_statement ais ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year AND ais.data_unavailable = FALSE
                    LEFT JOIN annual_cash_flow acf ON abs.symbol = acf.symbol AND abs.fiscal_year = acf.fiscal_year AND acf.data_unavailable = FALSE
                    LEFT JOIN (
                        SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                        FROM sec_valuations
                        ORDER BY symbol, updated_at DESC
                    ) sv ON abs.symbol = sv.symbol
                    WHERE abs.symbol = %s AND abs.data_unavailable = FALSE
                    ORDER BY (CASE WHEN ais.revenue IS NOT NULL THEN 0
                                    WHEN ais.symbol IS NOT NULL THEN 1
                                    ELSE 2 END),
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
                        MAX_FISCAL_YEAR_AGE_YEARS,
                    ),
                )
                quality_row_db = cur.fetchone()

                # Get annual income statement history for growth computation (not from growth_metrics table)
                # NOTE: Removed revenue IS NOT NULL filter - banks often have NULL revenue but valid net_income
                # Individual growth metrics will only be calculated if their specific inputs are available
                cur.execute(
                    """
                    SELECT fiscal_year, revenue, operating_income, net_income, earnings_per_share
                    FROM annual_income_statement
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC
                    LIMIT 10
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
            quality_dict = self._compute_quality_metrics(symbol, quality_row_db, ev_metrics)
            # Compute growth metrics from annual income statement history (not read from DB)
            growth_dict = self._compute_growth_metrics(symbol, income_rows)

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

            return [(value_dict, quality_dict, growth_dict)]

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Fetch failed: {e}")
            return [
                (
                    self._unavailable_marker("value_metrics", symbol),
                    self._unavailable_marker("quality_metrics", symbol),
                    self._unavailable_marker("growth_metrics", symbol),
                )
            ]

    def _build_value_metrics(self, symbol: str, sec_val_row: Any) -> dict[str, Any]:
        """Build value_metrics from SEC valuations (yfinance-free, Session 271).

        All metrics from SEC-audited data. Dividend yield added 2026-07-20 (migration
        1144): load_sec_valuations.py now computes it from the SEC "PaymentsOfDividends"
        cash-flow concept / market_cap - was previously hardcoded None here because SEC
        had no dividend source wired up at all (dead 8%-weight bucket in value_score).

        Session 385: Added enterprise value and EV ratio metrics from sec_valuations.
        """
        if not sec_val_row or sec_val_row[2]:  # data_unavailable flag at index 2
            return self._unavailable_marker("value_metrics", symbol)

        # Extract SEC-derived valuations (all from sec_valuations table)
        # Using dict access - tuple fallback violates fail-fast governance
        row_dict = dict(sec_val_row) if hasattr(sec_val_row, "__getitem__") else {}
        if not row_dict:
            return self._unavailable_marker("value_metrics", symbol)

        pe = row_dict.get("pe_ratio")
        pb = row_dict.get("pb_ratio")
        ps = row_dict.get("ps_ratio")
        peg = row_dict.get("peg_ratio")
        fcf_yield = row_dict.get("fcf_yield")
        dividend_yield = row_dict.get("dividend_yield")
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
                forward_pe = float(current_price) / float(forward_eps)

        # Validate: at least one core metric must be non-None
        # FIXED 2026-08-06: Include forward_pe in validation. Analyst-derived forward PE should
        # count toward "available" metric even if historical SEC PE/PB/PS/FCF is missing.
        # Without this, unprofitable companies with analyst forward EPS guidance were marked
        # "data_unavailable" despite having a usable forward valuation metric.
        core_metrics = [pe, pb, ps, fcf_yield, forward_pe]
        if all(m is None for m in core_metrics):
            return self._unavailable_marker("value_metrics", symbol)

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

        # pe_ratio reason: was hardcoded "missing_sec_data" regardless of cause. load_sec_
        # valuations.py only computes pe_ratio when ttm_eps > 0 (a negative/zero-EPS company
        # has no meaningful P/E, same "not applicable" class as non_dividend_paying_stock).
        # Live audit: 2283 of 2519 universe pe_ratio NULLs are unprofitable companies with a
        # real, present EPS that's just <= 0 - only 126 are genuine missing-EPS gaps. peg_ratio
        # requires pe_ratio, so it inherits the same reason when pe_ratio itself is the blocker.
        pe_ratio_reason = None
        if pe is None:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
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
                cur.execute(
                    """
                    SELECT fiscal_year, earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
                    ORDER BY fiscal_year DESC LIMIT 2
                    """,
                    (symbol,),
                )
                eps_rows = cur.fetchall()
            peg_ratio_reason = peg_ratio_reason_from_eps_history(eps_rows)
        else:
            peg_ratio_reason = pe_ratio_reason if peg is None and pe is None else None

        # Track which fields are unavailable (Session 389). No yfinance fallback remains
        # (removed 2026-08-17 - see comment above data_source_peg/data_source_dividend), so
        # this is always "sec_audited" now regardless of which individual field is populated.
        overall_data_source = "sec_audited"

        return {
            "symbol": symbol,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "ps_ratio": ps,
            "peg_ratio": peg,
            "dividend_yield": dividend_yield,
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
            "pb_ratio_unavailable_reason": "missing_sec_data" if pb is None else None,
            "ps_ratio_unavailable_reason": "missing_sec_data" if ps is None else None,
            "peg_ratio_unavailable_reason": peg_ratio_reason,
            "dividend_yield_unavailable_reason": dividend_yield_reason,
            "fcf_yield_unavailable_reason": "missing_sec_data" if fcf_yield is None else None,
            "forward_pe_unavailable_reason": "no_analyst_estimates" if forward_pe is None else None,
            "ev_ebitda_unavailable_reason": ev_ebitda_reason if ev_ebitda is None else None,
            "ev_revenue_unavailable_reason": "missing_sec_data" if ev_revenue is None else None,
            "market_cap_unavailable_reason": "missing_sec_data" if market_cap is None else None,
            "intrinsic_value_unavailable_reason": intrinsic_value_reason,
            "margin_of_safety_unavailable_reason": margin_of_safety_reason,
            "held_percent_insiders_unavailable_reason": None,  # In positioning_metrics, not here
            "held_percent_institutions_unavailable_reason": None,  # In positioning_metrics, not here
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
                # Not enough quarterly data - set unavailable reasons for metrics that depend on quarters
                for field in [
                    "consecutive_positive_quarters",
                    "quarterly_growth_momentum",
                    "earnings_growth_4q_avg",
                    "eps_growth_stability",
                ]:
                    metrics[f"{field}_unavailable_reason"] = "insufficient_quarterly_history"
                return metrics

            quarters.reverse()
            quarterly_data = [
                {
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

            eps_growth_rates = []
            for i in range(1, len(last_4q)):
                curr_eps = last_4q[i]["eps"]
                prev_eps = last_4q[i - 1]["eps"]
                if curr_eps is not None and prev_eps is not None and prev_eps != 0:
                    growth = ((curr_eps - prev_eps) / abs(prev_eps)) * 100
                    eps_growth_rates.append(growth)

            if eps_growth_rates:
                earnings_growth_4q_avg = sum(eps_growth_rates) / len(eps_growth_rates)
                # Bounded like every other growth/trend field in this file (see
                # MAX_TREND_PERCENTAGE_POINTS above) - a near-zero prior-quarter EPS makes a
                # single quarter's growth rate (and therefore this average) mathematically
                # enormous despite being a "real" computation, which would overflow this
                # NUMERIC(10,4) column and abort the entire row's write.
                if abs(earnings_growth_4q_avg) < MAX_TREND_PERCENTAGE_POINTS:
                    metrics["earnings_growth_4q_avg"] = float(round(earnings_growth_4q_avg, 2))
                else:
                    metrics["earnings_growth_4q_avg_unavailable_reason"] = "garbage_metric_value_abs_gt_100000"

                if len(eps_growth_rates) >= 2:
                    mean_growth = sum(eps_growth_rates) / len(eps_growth_rates)
                    variance = sum((x - mean_growth) ** 2 for x in eps_growth_rates) / len(eps_growth_rates)
                    stability_stddev = sqrt(variance)
                    # Same overflow risk as earnings_growth_4q_avg above - stddev of a set
                    # containing one enormous near-zero-denominator growth rate is itself
                    # enormous.
                    if stability_stddev < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["eps_growth_stability"] = float(round(stability_stddev, 2))
                    else:
                        metrics["eps_growth_stability_unavailable_reason"] = "garbage_metric_value_abs_gt_100000"
                else:
                    # Only one quarter-over-quarter EPS comparison available - not enough to
                    # compute a variance/stddev, but this is a real, explainable gap.
                    metrics["eps_growth_stability_unavailable_reason"] = "insufficient_eps_growth_datapoints"
            else:
                # >=4 quarters existed (the insufficient_quarterly_history branch above was not
                # hit) but none had both a current and prior EPS value to diff - e.g. missing
                # EPS in the source rows. Previously this left earnings_growth_4q_avg/
                # eps_growth_stability unset with no reason, indistinguishable from a bug.
                metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_eps_data"
                metrics["eps_growth_stability_unavailable_reason"] = "insufficient_eps_data"

            revenue_growth_rates = []
            for i in range(1, len(last_4q)):
                curr_rev = last_4q[i]["revenue"]
                prev_rev = last_4q[i - 1]["revenue"]
                if curr_rev is not None and prev_rev is not None and prev_rev != 0:
                    growth = ((curr_rev - prev_rev) / abs(prev_rev)) * 100
                    revenue_growth_rates.append(growth)

            if revenue_growth_rates:
                quarterly_growth_momentum = sum(revenue_growth_rates) / len(revenue_growth_rates)
                # Same near-zero-prior-quarter overflow risk as earnings_growth_4q_avg above.
                if abs(quarterly_growth_momentum) < MAX_TREND_PERCENTAGE_POINTS:
                    metrics["quarterly_growth_momentum"] = float(round(quarterly_growth_momentum, 2))
                else:
                    metrics["quarterly_growth_momentum_unavailable_reason"] = "garbage_metric_value_abs_gt_100000"
            else:
                metrics["quarterly_growth_momentum_unavailable_reason"] = "insufficient_revenue_data"

            # Phase 3A: Earnings surprise and beat rate
            # Use last quarter EPS vs current analyst forward EPS as proxy for surprise
            last_eps = last_4q[-1]["eps"]
            forward_eps = self._get_analyst_forward_eps(symbol)

            if last_eps is not None and forward_eps is not None and last_eps != 0:
                # Earnings surprise: (last reported - forward estimate) / |forward estimate| * 100
                surprise = ((last_eps - forward_eps) / abs(forward_eps)) * 100
                metrics["earnings_surprise_avg"] = float(round(surprise, 2))

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

    def _compute_quality_metrics(self, symbol: str, quality_row: Any, ev_metrics: Any = None) -> dict[str, Any]:  # noqa: C901
        """Compute quality_metrics from SEC financials (balance sheet + income statement + cash flow + EV data).

        ev_metrics: tuple of (total_debt, total_cash, ebitda) from sec_valuations
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
                    # First try: recent history (3 years)
                    cur.execute(
                        """
                        SELECT interest_expense, operating_income, pretax_income
                        FROM annual_income_statement
                        WHERE symbol = %s AND interest_expense IS NOT NULL AND interest_expense > 0
                          AND (operating_income IS NOT NULL OR pretax_income IS NOT NULL)
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

            # ROE = Net Income / Shareholders' Equity
            if net_income is not None and stockholders_equity is not None and stockholders_equity != 0:
                metrics["roe"] = float((net_income / stockholders_equity) * 100)
            else:
                failed_metrics.append("roe")

            # ROA = Net Income / Total Assets
            if net_income is not None and total_assets is not None and total_assets != 0:
                metrics["roa"] = float((net_income / total_assets) * 100)
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

            # Debt to Equity = Total Liabilities / Shareholders' Equity
            if total_liabilities is not None and stockholders_equity is not None and stockholders_equity != 0:
                metrics["debt_to_equity"] = float(total_liabilities / stockholders_equity)
            else:
                failed_metrics.append("debt_to_equity")

            # Debt to Assets = Total Liabilities / Total Assets
            # Both inputs are already fetched above for ROA; this was previously never
            # computed even though stock_scores._score_stability has a standing 10%-weight
            # slot for it (merged in from quality_metrics.debt_to_assets).
            if total_liabilities is not None and total_assets is not None and total_assets != 0:
                metrics["debt_to_assets"] = float(total_liabilities / total_assets)
            else:
                failed_metrics.append("debt_to_assets")

            # Current Ratio = Current Assets / Current Liabilities
            # Both inputs come from the same annual_balance_sheet row already fetched above;
            # this was previously never computed even though stock_scores._score_quality's
            # fallback formula (used when quality_score itself is unavailable) has a standing
            # slot for it.
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                metrics["current_ratio"] = float(current_assets / current_liabilities)
            else:
                failed_metrics.append("current_ratio")

            # Quick Ratio = (Current Assets - Inventory) / Current Liabilities
            # `inventory` is NULL for ~66% of rows (service/software companies legitimately
            # carry none, and some filers simply don't break it out) - treat NULL as 0 rather
            # than failing the metric, same treatment IBD/most screeners use. Was previously
            # never computed even though quality_metrics.quick_ratio has existed since
            # migration 072 and stock_scores/load_stock_scores.py already queries it.
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                metrics["quick_ratio"] = float((current_assets - (inventory or 0)) / current_liabilities)
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
                    cur.execute(
                        """
                        SELECT gross_profit, cost_of_revenue, revenue
                        FROM annual_income_statement
                        WHERE symbol = %s AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL)
                          AND revenue IS NOT NULL
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
                              AND revenue IS NOT NULL
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
            roic_tax_expense, roic_pretax_income, roic_operating_income, roic_interest_expense = (
                income_tax_expense,
                pretax_income,
                operating_income,
                anchor_interest_expense_for_roic,
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
                    cur.execute(
                        """
                        SELECT income_tax_expense, pretax_income, operating_income, interest_expense
                        FROM annual_income_statement
                        WHERE symbol = %s AND income_tax_expense IS NOT NULL
                          AND pretax_income IS NOT NULL
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                       THEN 0 ELSE 1 END), fiscal_year DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_tax_row = cur.fetchone()

                    # If 3-year window fails, search entire history
                    if not fallback_tax_row:
                        cur.execute(
                            """
                            SELECT income_tax_expense, pretax_income, operating_income, interest_expense
                            FROM annual_income_statement
                            WHERE symbol = %s AND income_tax_expense IS NOT NULL
                              AND pretax_income IS NOT NULL
                            ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                           THEN 0 ELSE 1 END), fiscal_year DESC
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_tax_row = cur.fetchone()

                if fallback_tax_row:
                    roic_tax_expense = self._nan_to_none(
                        safe_float(fallback_tax_row[0], f"{symbol}.income_tax_expense_fallback_year", allow_none=True)
                    )
                    roic_pretax_income = self._nan_to_none(
                        safe_float(fallback_tax_row[1], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                    )
                    roic_operating_income = self._nan_to_none(
                        safe_float(fallback_tax_row[2], f"{symbol}.operating_income_fallback_year", allow_none=True)
                    )
                    roic_interest_expense = self._nan_to_none(
                        safe_float(fallback_tax_row[3], f"{symbol}.interest_expense_fallback_year", allow_none=True)
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
                    # First try: both fields in recent history (3 years)
                    cur.execute(
                        """
                        SELECT stockholders_equity, cash_and_equivalents
                        FROM annual_balance_sheet
                        WHERE symbol = %s AND stockholders_equity IS NOT NULL
                          AND cash_and_equivalents IS NOT NULL
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
                              AND cash_and_equivalents IS NOT NULL
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
                    cur.execute(
                        """
                        SELECT long_term_debt
                        FROM annual_balance_sheet
                        WHERE symbol = %s AND long_term_debt IS NOT NULL
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
                            WHERE symbol = %s AND long_term_debt IS NOT NULL
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
            if dividends_paid is not None and net_income is not None and net_income > 0:
                payout_ratio_pct = (dividends_paid / net_income) * 100
                if abs(payout_ratio_pct) <= MAX_PAYOUT_RATIO_ABS_PCT:
                    metrics["payout_ratio"] = float(payout_ratio_pct)
                else:
                    failed_metrics.append("payout_ratio")
                    payout_ratio_reason = "implausible_ratio"
            else:
                failed_metrics.append("payout_ratio")
                if dividends_paid is not None and net_income is not None and net_income <= 0:
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
            if total_cash_ev is not None and shares_outstanding is not None and shares_outstanding > 0:
                metrics["cash_per_share"] = float(total_cash_ev / shares_outstanding)
            else:
                failed_metrics.append("cash_per_share")

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
            if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
                try:
                    yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["earnings_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("earnings_growth_yoy")
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
                try:
                    ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100
                    if abs(ni_growth) < MAX_TREND_PERCENTAGE_POINTS:
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
                # Gross Margin Trend - now can compute with prior-year cost_of_revenue
                if cost_of_revenue is not None and prior_year_cost_of_revenue is not None:
                    curr_gm = ((revenue - cost_of_revenue) / revenue) * 100 if revenue > 0 else None
                    prior_gm = (
                        ((prior_year_revenue - prior_year_cost_of_revenue) / prior_year_revenue) * 100
                        if prior_year_revenue > 0
                        else None
                    )
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
            sgr_dividends_paid = dividends_paid
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
                        # Same MAX_TREND_PERCENTAGE_POINTS overflow guard as the growth_yoy
                        # fields above - a near-zero stockholders_equity base blows up roe_pct
                        # the same way a near-zero prior-year base blows up those ratios.
                        if abs(sgr) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["sustainable_growth_rate"] = float(sgr)
                        elif sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                    except (ValueError, TypeError, ZeroDivisionError):
                        if sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                elif sgr_reason is None:
                    sgr_reason = "missing_sec_data"
            elif sgr_reason is None:
                sgr_reason = "missing_sec_data"

            # ROE Trend = Current ROE - Prior ROE (now can compute with prior-year equity)
            # Same per-side MAX_MARGIN_ABS_PCT bound as the margin trends above - a near-zero
            # prior-year equity base (the ORKA 8.3M% case this function's docstring already
            # describes) must be caught before the subtraction, not just via the looser
            # trend-level MAX_TREND_PERCENTAGE_POINTS check on the delta.
            if (
                stockholders_equity is not None
                and net_income is not None
                and stockholders_equity > 0
                and prior_year_stockholders_equity is not None
                and prior_year_net_income is not None
                and prior_year_stockholders_equity > 0
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
                try:
                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100
                    if abs(fcf_growth) < MAX_TREND_PERCENTAGE_POINTS:
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
            debt_to_assets_score = (
                100.0 - metrics["debt_to_assets"] * 100.0 if metrics["debt_to_assets"] is not None else None
            )
            # Interest coverage: solvency curve, not a raw percentage. <1.5x is going-concern
            # risk territory, >=10x is effectively debt-service-risk-free.
            interest_coverage_score = None
            if metrics["interest_coverage"] is not None:
                ic = metrics["interest_coverage"]
                if ic < 0:
                    interest_coverage_score = 0.0
                elif ic < 1.5:
                    interest_coverage_score = (ic / 1.5) * 40
                elif ic < 3:
                    interest_coverage_score = 40 + ((ic - 1.5) / 1.5) * 30
                elif ic < 10:
                    interest_coverage_score = 70 + ((ic - 3) / 7) * 30
                else:
                    interest_coverage_score = 100.0
            quality_components = [
                metrics["roe"],
                metrics["roa"],
                metrics["operating_margin"],
                metrics["net_margin"],
                debt_to_assets_score,
                interest_coverage_score,
            ]
            available_components = [m for m in quality_components if m is not None]

            # An unprofitable company still has a real, computed quality score (0,
            # after clamping) - that's honest data, not missing data. Do not mark
            # data_unavailable just because every component came out <= 0.
            if available_components:
                # Normalize to 0-100 scale: ROE/margins can exceed 100, cap at 100;
                # negative components clamp to 0 (floor of the quality scale).
                normalized = [min(100, max(0, m)) for m in available_components]
                metrics["quality_score"] = float(sum(normalized) / len(normalized))

            # CRITICAL FIX 2026-07-20: Only mark data_unavailable if ALL metrics are missing.
            # Partial quality data is valid and should be scored with completeness tracking.
            # Session 297: Quality scores with 2-3 metrics are legitimate (with completeness % for filtering).
            # Do NOT mark partial data as unavailable - that violates GOVERNANCE "honest incomplete data" principle.

            # Initialize all *_unavailable_reason fields (Session 389)
            # These explain WHY a metric is NULL for users/operators
            metrics["roe_unavailable_reason"] = "missing_sec_data" if "roe" in failed_metrics else None
            metrics["roa_unavailable_reason"] = "missing_sec_data" if "roa" in failed_metrics else None
            metrics["operating_margin_unavailable_reason"] = (
                ("implausible_ratio" if "operating_margin" in implausible_ratio_metrics else "missing_sec_data")
                if "operating_margin" in failed_metrics
                else None
            )
            metrics["net_margin_unavailable_reason"] = (
                ("implausible_ratio" if "net_margin" in implausible_ratio_metrics else "missing_sec_data")
                if "net_margin" in failed_metrics
                else None
            )
            metrics["debt_to_equity_unavailable_reason"] = (
                "missing_sec_data" if "debt_to_equity" in failed_metrics else None
            )
            metrics["current_ratio_unavailable_reason"] = (
                ("reit_special_entity" if unclassified_balance_sheet else "missing_sec_data")
                if "current_ratio" in failed_metrics
                else None
            )
            metrics["quick_ratio_unavailable_reason"] = (
                ("reit_special_entity" if unclassified_balance_sheet else "missing_sec_data")
                if "quick_ratio" in failed_metrics
                else None
            )
            metrics["interest_coverage_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "interest_coverage" in implausible_ratio_metrics
                    else "interest_expense_not_itemized"
                    if no_recent_interest_expense
                    else "missing_sec_data"
                )
                if "interest_coverage" in failed_metrics
                else None
            )
            metrics["debt_to_assets_unavailable_reason"] = (
                "missing_sec_data" if "debt_to_assets" in failed_metrics else None
            )
            # Phase 3 Expansion (Session 357+): New metrics - initialize their _unavailable_reason fields
            metrics["gross_margin_unavailable_reason"] = (
                (
                    "reit_special_entity"
                    if no_gross_profit_concept
                    else "implausible_ratio"
                    if "gross_margin" in implausible_ratio_metrics
                    else "missing_sec_data"
                )
                if "gross_margin" in failed_metrics
                else None
            )
            metrics["ebitda_margin_unavailable_reason"] = (
                ("implausible_ratio" if "ebitda_margin" in implausible_ratio_metrics else "missing_sec_data")
                if "ebitda_margin" in failed_metrics
                else None
            )
            metrics["roic_pct_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roic_pct" in implausible_ratio_metrics
                    else ("unprofitable_stock" if roic_pct_unprofitable else "missing_sec_data")
                )
                if "roic_pct" in failed_metrics
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
            metrics["total_debt_unavailable_reason"] = "missing_sec_data" if "total_debt" in failed_metrics else None
            metrics["total_cash_unavailable_reason"] = "missing_sec_data" if "total_cash" in failed_metrics else None
            metrics["cash_per_share_unavailable_reason"] = (
                "missing_sec_data" if "cash_per_share" in failed_metrics else None
            )
            metrics["ebitda_unavailable_reason"] = "missing_sec_data" if "ebitda" in failed_metrics else None
            metrics["earnings_growth_yoy_unavailable_reason"] = (
                "missing_sec_data" if "earnings_growth_yoy" in failed_metrics else None
            )
            metrics["revenue_growth_yoy_unavailable_reason"] = (
                "missing_sec_data" if "revenue_growth_yoy" in failed_metrics else None
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

            metrics["quality_score_unavailable_reason"] = None  # Score can be partial; only mark if ALL metrics failed

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

    def _compute_period_growth(
        self,
        symbol: str,
        values: list[tuple[int, float]],
        offset: int,
        metric_key: str,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        sign_change_metrics: set[str],
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

        growth = self._cagr(latest_val, target_val, actual_years)
        if growth is not None:
            metrics[metric_key] = float(round(growth, 2))
        else:
            failed_metrics.append(metric_key)

    def _compute_growth_metrics(self, symbol: str, income_rows: list[Any]) -> dict[str, Any]:
        """Compute multi-year growth rates from annual income statement history.

        Calculates CAGR for 1y, 3y, 5y periods using compound annual growth rate formula.
        income_rows: List of (fiscal_year, total_revenue, operating_income, net_income,
        earnings_per_share) sorted DESC by fiscal_year (most recent first).
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
            "updated_at": get_loader_timestamp(),
            "data_unavailable": False,
            "data_source": "sec_audited",
        }

        revenues: list[tuple[int, float]] = []
        eps_values: list[tuple[int, float]] = []
        for row in income_rows:
            try:
                fiscal_year = int(row[0]) if row[0] is not None else None
                rev = float(row[1]) if row[1] is not None else None
                eps = float(row[4]) if row[4] is not None else None
                rev = self._nan_to_none(rev)
                eps = self._nan_to_none(eps)
                if fiscal_year is None:
                    continue
                if rev is not None and rev > 0:
                    revenues.append((fiscal_year, rev))
                if eps is not None and eps != 0:
                    eps_values.append((fiscal_year, eps))
            except (ValueError, TypeError):
                continue

        failed_metrics: list[str] = []
        sign_change_metrics: set[str] = set()
        self._compute_period_growth(
            symbol, revenues, 1, "revenue_growth_1y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol, eps_values, 1, "eps_growth_1y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol, revenues, 3, "revenue_growth_3y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol, eps_values, 3, "eps_growth_3y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol, revenues, 5, "revenue_growth_5y", metrics, failed_metrics, sign_change_metrics
        )
        self._compute_period_growth(
            symbol, eps_values, 5, "eps_growth_5y", metrics, failed_metrics, sign_change_metrics
        )

        if not revenues and not eps_values:
            return self._unavailable_marker("growth_metrics", symbol)

        def _growth_reason(metric_key: str) -> str | None:
            if metric_key in sign_change_metrics:
                return "growth_undefined_sign_change"
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

        if failed_metrics:
            if len(failed_metrics) == 6:
                return self._unavailable_marker("growth_metrics", symbol)
            # PARTIAL failure (1-5 of 6 periods, e.g. eps_growth_5y needs 6 fiscal years of
            # history that many symbols don't have yet): the periods that DID compute are
            # real values, not noise - leave data_unavailable=False so downstream scoring
            # (load_stock_scores.py::_score_growth) can weight whatever periods are present
            # instead of discarding the whole row. _score_growth already renormalizes over
            # available fields; it was this flag - not the scorer - that was throwing partial
            # data away before it ever got there. `reason` still records what's missing.
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
            (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, forward_pe, enterprise_value, ev_ebitda, ev_revenue, market_cap, intrinsic_value_per_share, margin_of_safety_pct, value_score, data_unavailable, reason, data_source, updated_at,
             pe_ratio_unavailable_reason, pb_ratio_unavailable_reason, ps_ratio_unavailable_reason, peg_ratio_unavailable_reason,
             dividend_yield_unavailable_reason, fcf_yield_unavailable_reason, forward_pe_unavailable_reason, ev_ebitda_unavailable_reason, ev_revenue_unavailable_reason,
             market_cap_unavailable_reason, held_percent_insiders_unavailable_reason, held_percent_institutions_unavailable_reason,
             intrinsic_value_unavailable_reason, margin_of_safety_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio,
                peg_ratio = EXCLUDED.peg_ratio,
                dividend_yield = EXCLUDED.dividend_yield,
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
                held_percent_insiders_unavailable_reason = EXCLUDED.held_percent_insiders_unavailable_reason,
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
                row.get("held_percent_insiders_unavailable_reason"),
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
             earnings_growth_4q_avg_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            ),
        )

    def _insert_growth_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert growth_metrics row with multi-year CAGR values and trend fields."""
        cur.execute(
            """
            INSERT INTO growth_metrics
            (symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y,
             net_income_growth_yoy, operating_income_growth_yoy, gross_margin_trend, operating_margin_trend, net_margin_trend,
             roe_trend, sustainable_growth_rate, quarterly_growth_momentum, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy,
             consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability,
             data_unavailable, reason, data_source, updated_at,
             revenue_growth_1y_unavailable_reason, revenue_growth_3y_unavailable_reason, revenue_growth_5y_unavailable_reason,
             eps_growth_1y_unavailable_reason, eps_growth_3y_unavailable_reason, eps_growth_5y_unavailable_reason,
             net_income_growth_yoy_unavailable_reason, operating_income_growth_yoy_unavailable_reason, gross_margin_trend_unavailable_reason,
             operating_margin_trend_unavailable_reason, net_margin_trend_unavailable_reason, roe_trend_unavailable_reason,
             sustainable_growth_rate_unavailable_reason, quarterly_growth_momentum_unavailable_reason, fcf_growth_yoy_unavailable_reason,
             ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason,
             consecutive_positive_quarters_unavailable_reason, earnings_growth_4q_avg_unavailable_reason, eps_growth_stability_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                revenue_growth_1y = EXCLUDED.revenue_growth_1y,
                revenue_growth_3y = EXCLUDED.revenue_growth_3y,
                revenue_growth_5y = EXCLUDED.revenue_growth_5y,
                eps_growth_1y = EXCLUDED.eps_growth_1y,
                eps_growth_3y = EXCLUDED.eps_growth_3y,
                eps_growth_5y = EXCLUDED.eps_growth_5y,
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
                revenue_growth_1y_unavailable_reason = EXCLUDED.revenue_growth_1y_unavailable_reason,
                revenue_growth_3y_unavailable_reason = EXCLUDED.revenue_growth_3y_unavailable_reason,
                revenue_growth_5y_unavailable_reason = EXCLUDED.revenue_growth_5y_unavailable_reason,
                eps_growth_1y_unavailable_reason = EXCLUDED.eps_growth_1y_unavailable_reason,
                eps_growth_3y_unavailable_reason = EXCLUDED.eps_growth_3y_unavailable_reason,
                eps_growth_5y_unavailable_reason = EXCLUDED.eps_growth_5y_unavailable_reason,
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
        return marker

    def _unavailable_marker(self, table: str, symbol: str) -> dict[str, Any]:
        """Return data_unavailable marker for a table.

        CRITICAL: Include all *_unavailable_reason fields (even when data is fully unavailable)
        so the database row has explicit reason codes explaining why metrics are NULL.
        Previously these were omitted, causing 600+ rows to have NULL reason codes.
        """
        if table == "value_metrics":
            return {
                "symbol": symbol,
                "pe_ratio": None,
                "pb_ratio": None,
                "ps_ratio": None,
                "peg_ratio": None,
                "dividend_yield": None,
                "fcf_yield": None,
                "pe_ratio_unavailable_reason": "missing_sec_data",
                "pb_ratio_unavailable_reason": "missing_sec_data",
                "ps_ratio_unavailable_reason": "missing_sec_data",
                "peg_ratio_unavailable_reason": "missing_sec_data",
                "dividend_yield_unavailable_reason": "missing_sec_data",
                "fcf_yield_unavailable_reason": "missing_sec_data",
                "forward_pe_unavailable_reason": "analyst_estimates_not_in_sec_filings",
                # FIXED 2026-08-18 (goal: "no SEC data" audit): this is the fully-unavailable
                # fallback for symbols with NO SEC valuation data at all - every sibling reason
                # here says "missing_sec_data" for exactly that case, but this one was still
                # hardcoded to the specific (and usually false) claim
                # "depreciation_amortization_not_loaded" from before the real per-symbol
                # ev_ebitda_reason logic above (~line 800) was rewritten to distinguish
                # unprofitable_stock/ebitda_not_extracted/missing_sec_data by actual cause.
                # 441 rows universe-wide carried this stale, misleading label.
                "ev_ebitda_unavailable_reason": "missing_sec_data",
                "ev_revenue": None,
                "ev_revenue_unavailable_reason": "missing_sec_data",
                "market_cap": None,
                "market_cap_unavailable_reason": "missing_sec_data",
                "held_percent_insiders_unavailable_reason": None,
                "held_percent_institutions_unavailable_reason": None,
                "intrinsic_value_unavailable_reason": "missing_sec_data",
                "margin_of_safety_unavailable_reason": "missing_sec_data",
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient SEC valuation data",
                "updated_at": get_loader_timestamp(),
            }
        elif table == "quality_metrics":
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
                "ebitda_unavailable_reason": "missing_sec_data",
                "earnings_growth_yoy": None,
                "revenue_growth_yoy": None,
                # Reason codes for all metrics (Session 401 fix: were NULL before)
                "roe_unavailable_reason": "missing_sec_data",
                "roa_unavailable_reason": "missing_sec_data",
                "operating_margin_unavailable_reason": "missing_sec_data",
                "net_margin_unavailable_reason": "missing_sec_data",
                "debt_to_equity_unavailable_reason": "missing_sec_data",
                "current_ratio_unavailable_reason": "missing_sec_data",
                "quick_ratio_unavailable_reason": "missing_sec_data",
                "interest_coverage_unavailable_reason": "missing_sec_data",
                "debt_to_assets_unavailable_reason": "missing_sec_data",
                "quality_score_unavailable_reason": None,
                # Phase 3 reason codes
                "gross_margin_unavailable_reason": "missing_sec_data",
                "ebitda_margin_unavailable_reason": "missing_sec_data",
                "roic_pct_unavailable_reason": "missing_sec_data",
                "fcf_to_net_income_unavailable_reason": "missing_sec_data",
                "ocf_to_net_income_unavailable_reason": "missing_sec_data",
                "payout_ratio_unavailable_reason": "missing_sec_data",
                "free_cash_flow_unavailable_reason": "missing_sec_data",
                "operating_cash_flow_unavailable_reason": "missing_sec_data",
                "total_debt_unavailable_reason": "missing_sec_data",
                "total_cash_unavailable_reason": "missing_sec_data",
                "cash_per_share_unavailable_reason": "missing_sec_data",
                "earnings_growth_yoy_unavailable_reason": "missing_sec_data",
                "revenue_growth_yoy_unavailable_reason": "missing_sec_data",
                # _SHARED_TREND_FIELDS (consecutive_positive_quarters, earnings_growth_4q_avg,
                # eps_growth_stability, quarterly_growth_momentum, earnings_surprise_avg,
                # earnings_beat_rate, and the *_yoy/*_trend fields) - these are also
                # quality_metrics columns but were missing from this fallback marker, leaving
                # ~344-3,173 rows per field (whichever symbols hit this fully-unavailable path)
                # with a NULL value AND no reason code, indistinguishable from a bug.
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": "missing_sec_data" for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient SEC financial data",
                "updated_at": get_loader_timestamp(),
            }
        else:  # growth_metrics
            return {
                "symbol": symbol,
                "revenue_growth_1y": None,
                "revenue_growth_3y": None,
                "revenue_growth_5y": None,
                "eps_growth_1y": None,
                "eps_growth_3y": None,
                "eps_growth_5y": None,
                # Reason codes for all metrics (Session 401 fix: were NULL before)
                "revenue_growth_1y_unavailable_reason": "insufficient_history",
                "revenue_growth_3y_unavailable_reason": "insufficient_history",
                "revenue_growth_5y_unavailable_reason": "insufficient_history",
                "eps_growth_1y_unavailable_reason": "insufficient_history",
                "eps_growth_3y_unavailable_reason": "insufficient_history",
                "eps_growth_5y_unavailable_reason": "insufficient_history",
                # Same _SHARED_TREND_FIELDS gap as the quality_metrics branch above (these
                # columns are mirrored from quality_metrics on the success path - see
                # _SHARED_TREND_FIELDS mirroring in fetch_incremental - but this fallback path
                # never went through that mirror, so they were previously left NULL with no
                # reason instead of an explained gap).
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": "insufficient_history" for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient historical data",
                "updated_at": get_loader_timestamp(),
            }


if __name__ == "__main__":
    sys.exit(run_loader(ValueQualityGrowthMetricsLoader, description="Consolidated value + quality + growth metrics"))
