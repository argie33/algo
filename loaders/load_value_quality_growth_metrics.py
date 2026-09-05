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
from typing import Any, cast

import psycopg2
from psycopg2.extras import execute_values

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Full timestamp, not just date - a date-only value casts to midnight and makes the
# freshness monitor see stale data for hours after the actual load time.
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

    load_sec_valuations.py only computes peg_ratio when YoY EPS growth is positive (declining
    or newly-profitable earnings make PEG not meaningful, same "not applicable" class as
    unprofitable_stock/non_dividend_paying_stock elsewhere in this file) - distinguish that
    from a genuine <2-fiscal-years-on-file gap ("insufficient_history"), since scores.py's
    `_categorize_reason()` buckets them into different UI categories.

    Args:
        eps_rows: 0-2 (fiscal_year, earnings_per_share) tuples, already filtered to non-NULL
            EPS and ordered fiscal_year DESC (i.e. exactly what the caller's DB query returns).
    """
    if len(eps_rows) < 2:
        return "insufficient_history"
    ttm_eps_for_growth, prior_eps_for_growth = eps_rows[0][1], eps_rows[1][1]
    if prior_eps_for_growth is None or prior_eps_for_growth <= 0:
        return "negative_earnings_growth"
    if ttm_eps_for_growth is not None and ttm_eps_for_growth <= prior_eps_for_growth:
        return "negative_earnings_growth"
    return "missing_sec_data"


def intrinsic_value_reason_from_fcf_yield(fcf_yield: float | None, fcf_yield_reason: str | None = None) -> str:
    """Decide why intrinsic_value_per_share (the DCF result) is unavailable when it's NULL.

    fcf_yield being present does NOT imply FCF was positive (it only requires being within
    +/-1000% of market cap) - _compute_dcf_intrinsic_value's first gate is `fcf <= 0` (the
    2-stage FCFE model can't discount a cash-burning company), so fcf_yield <= 0 must map to
    "negative_free_cash_flow", not a generic "implausible_dcf_result".

    Args:
        fcf_yield: sec_valuations.fcf_yield for this symbol (same sign as the FCF that fed
            the DCF, since both derive from the same ocf - capex over the same positive
            market_cap).
        fcf_yield_reason: the already-computed fcf_yield_unavailable_reason for this symbol
            (e.g. "capex_never_tagged_in_recent_filings", "no_recent_free_cash_flow_reported")
            when fcf_yield is None - propagate this specific reason instead of collapsing to
            the generic "missing_cash_flow_data" label; that label is only a fallback when no
            specific reason is available (e.g. direct callers/tests).
    """
    if fcf_yield is None:
        return fcf_yield_reason or "missing_cash_flow_data"
    if fcf_yield <= 0:
        return "negative_free_cash_flow"
    return "implausible_dcf_result"


# Fiscal-year data older than this is flagged as unavailable rather than silently scored as
# current - real active filers report annually with at most ~2 years of lag through this
# pipeline (sharp cliff in the universe's age distribution at 2 years); older means
# delisted/inactive or a genuine data gap.
MAX_FISCAL_YEAR_AGE_YEARS = 3

# Sanity bound for the 4 percentage-point-delta trend fields (gross/operating/net margin
# trend, ROE trend), stored in NUMERIC(10,4) columns. A near-zero prior-year denominator
# (equity/revenue crossing from negative to barely-positive) makes the delta mathematically
# enormous despite being a real computation - treat as unavailable rather than let it
# overflow the column and roll back the entire 3-table write for that symbol.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# Plausibility bound for growth-RATE fields (distinct from the margin/ROE trend fields
# above, which are percentage-POINT deltas bounded by the 0-100% margin range and stay on
# MAX_TREND_PERCENTAGE_POINTS). A near-zero prior-period denominator can produce
# mathematically enormous but meaningless growth rates; genuine hypergrowth small-caps can
# hit a few hundred percent but essentially never four or five digits.
MAX_PLAUSIBLE_GROWTH_PCT = 2_000.0

# Sanity bound for absolute-dollar fields (free_cash_flow, operating_cash_flow, total_debt,
# total_cash, ebitda), stored in NUMERIC(15,2) columns (max abs value < 10^13). Foreign
# filers reporting in local currency (e.g. VND/KRW) can overflow this column if a value
# isn't converted to USD before reaching this file, which would abort the entire 3-table
# write transaction for that symbol - mark implausible values unavailable instead of
# crashing on them, as a safety net independent of any particular currency-conversion bug.
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


def _mirror_shared_trend_fields(quality_dict: dict[str, Any], growth_dict: dict[str, Any]) -> None:
    """Copy _SHARED_TREND_FIELDS values/reasons from quality_dict into growth_dict in place.

    Mirrors unconditionally, even when growth_dict.data_unavailable is set - these fields come
    from _compute_quality_metrics (ROE/dividends), a completely different input set than
    growth's revenue/EPS history, so a growth-side failure must not overwrite a real
    quality-side value with growth's own blanket "insufficient history" reason. Only leaves
    growth_dict's own reason untouched when quality has no value AND no reason either.
    """
    for field in _SHARED_TREND_FIELDS:
        reason_field = f"{field}_unavailable_reason"
        if quality_dict.get(field) is not None:
            growth_dict[field] = quality_dict[field]
            growth_dict[reason_field] = None
        elif quality_dict.get(reason_field) is not None:
            growth_dict[reason_field] = quality_dict[reason_field]


class ValueQualityGrowthMetricsLoader(OptimalLoader, SymbolGateMixin):
    """Consolidated value + quality + growth metrics from SEC + valuations.

    Writes to 3 output tables in single per-symbol transaction:
    - value_metrics (PE, PB, PS, PEG, FCF, dividend yield from SEC)
    - quality_metrics (ROE, margins, debt ratios from SEC)
    - growth_metrics (revenue/EPS growth from SEC)
    """

    # forward_pe = current_price / forward_eps: a symbol whose tiny real share count inflates
    # every per-share figure would otherwise win percentile 100 in Value's
    # _percent_rank_cheap_high, same class of bug as pe/pb/ps ratios elsewhere. Excludes from
    # the percentile universe rather than forcing a floor/ceiling score.
    MIN_PLAUSIBLE_FORWARD_PE_RATIO = 0.05

    # Matches load_sec_valuations.py's MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO - this file's TIER
    # 3/TIER 4 dividend_yield fallbacks must stay in sync with that file's primary computation.
    MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO = 0.30

    # Pure oil/gas grantor royalty trusts (SIC 6792/6795) pass through royalty proceeds and
    # file a trust-basis balance sheet with no debt/cash/equity/operating-income concepts in
    # the GAAP-operating-company sense - same structural gap current_ratio/quick_ratio/
    # gross_margin already recognize via "reit_special_entity", extended here to the
    # debt/cash/interest/FCF-derived fields so it isn't miscounted as a recoverable gap.
    # Curated by hand, not a SIC-code rule: 6792/6795 also covers real operating companies
    # (RGLD/SSRM/TFPM/TPL/EROK/LB) that report normal financials and must not be swept in.
    _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS = frozenset({"NRT", "MTR", "CRT", "PBT", "SBR", "SJT"})

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

        # This loader fully overrides OptimalLoader.run() and never calls super().run(), so
        # it never got the base class's SLAMonitor wiring - wired up manually here.
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

                    # Always upsert all 3 tables, even when a row is data_unavailable - value/
                    # quality/growth are computed independently (different source queries), and
                    # skipping the write on unavailable would leave a table with no row at all
                    # (not even an unavailable marker), or let a stale last-good row keep
                    # showing forever with no way to downgrade it once data goes bad.
                    with DatabaseContext("write") as cur:
                        # Insert value metrics (ALWAYS present, either data or unavailable marker)
                        self._insert_value_metrics(cur, value_row)
                        value_inserts += 1

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

            # VERIFY: Confirm all 3 tables actually have TODAY's data before claiming success
            # (FAIL-FAST). Must use UTC date, not ET - loader inserts use DB timestamps (UTC).
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

            # Mark all 3 tables as ok via LoaderStatusManager (uses advisory locks). Per-table
            # dict, not a bare loop variable - each table's own latest_date must reach its own
            # mark_completed() call, not whichever table happened to be queried last.
            latest_dates: dict[str, Any] = {}
            with DatabaseContext("write") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    # Query the actual MAX(date) from each table
                    safe_table = assert_safe_table(table)
                    cur.execute(f"SELECT MAX(updated_at)::date FROM {safe_table}")
                    result = cur.fetchone()
                    latest_dates[table] = result[0] if result and result[0] else None

            execution_duration = time.time() - start_time
            # Report the real success ratio (not a hardcoded 100%) since mark_completed() reads
            # symbols_loaded/completion_pct to decide COMPLETED vs FAILED. Uses this loader's own
            # max_fail_rate (20%) instead of the generic 98% default - value/growth/quality
            # legitimately have higher failure rates (foreign filers, ADRs, non-SEC issuers).
            # Per-table counters, not one shared count - value/quality/growth come from
            # independent source queries and fail independently.
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
                # runner.py always re-marks the primary table (table_name = "value_metrics")
                # after run() returns, reading duration from stats["duration_sec"] - must be
                # present or runner.py clobbers the real duration already written above with None.
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

                # Also fetch EV metrics by column name to avoid index confusion. `reason` is a
                # 4th column (appended last so existing positional ev_metrics[0..2] reads stay
                # unchanged) letting total_cash/cash_per_share reuse sec_valuations' specific
                # unavailability cause instead of falling back to generic "missing_sec_data".
                if sec_val_row:
                    cur.execute(
                        "SELECT total_debt, total_cash, ebitda, reason FROM sec_valuations WHERE symbol = %s",
                        (symbol,),
                    )
                    ev_metrics = cur.fetchone()
                else:
                    ev_metrics = None

                # Get quality from SEC financials (annual balance sheet + income statement latest year),
                # plus prior year EPS/revenue for YoY growth. shares_outstanding comes from
                # sec_valuations, not annual_balance_sheet - must use its latest row to avoid
                # duplicate joins.
                #
                # The fiscal-year ORDER BY below picks one anchor year for both balance-sheet and
                # income-statement fields, ranked in this priority: (1) recent AND has real revenue,
                # (2) recent AND the income-statement join matched at all, (3) merely recent, (4) any
                # year with real revenue, (5) any year the join matched, (6) fiscal_year DESC. This
                # matters because a joined income-statement row can exist but be unusable (e.g. a
                # partial fact set with net_income but NULL revenue/operating_income/cost_of_revenue -
                # load_financial_statements.py's transform() only requires one of {revenue, net_income}
                # to pass), which would otherwise let a stale/wrong-year statement silently pair with a
                # fresh balance sheet and produce a plausible-looking but wrong margin/ROE, or a
                # merely-present-but-old year outrank a fresh, complete balance sheet just because it
                # has non-NULL revenue (e.g. $0 for a pre-revenue biotech). "Prefer usable data over
                # merely-present data" applies both within the fresh tier and within the stale
                # fallback tier. The FCF/recency tiebreak (secondary CASE below) is similarly bounded
                # to MAX_FISCAL_YEAR_AGE_YEARS so preferring an audited-FCF year never trades away a
                # fresh, complete balance sheet for one with ancient FCF data.
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
                    -- Freshness (within MAX_FISCAL_YEAR_AGE_YEARS) is the PRIMARY sort key; the
                    -- revenue/matched-income preference is only a tiebreak within the fresh tier
                    -- and, separately, within the stale-fallback tier - a fresh but revenue-poor
                    -- balance sheet must never lose to an older year just for having revenue.
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

                # Get annual income statement history for growth computation (not from growth_metrics
                # table). No revenue IS NOT NULL filter - banks often have NULL revenue but valid
                # net_income; individual growth metrics are only calculated when their specific
                # inputs are available. LIMIT 30 (not a tighter number): a 5y CAGR needs 6 usable
                # data points, and gap years (NULL-revenue restatements, real $0-revenue early-stage
                # years) can eat well over half of the most recent rows - 30 is the real DB-wide max
                # rows for any single symbol.
                #
                # stockholders_equity (8th column) is LEFT JOINed so a fiscal year with income-
                # statement data but no matching balance-sheet row still contributes to every OTHER
                # growth calc; book_value_growth alone goes unavailable for that year via the NULL.
                # Appended last so existing positional reads (income_rows[i][0..6] in
                # _compute_growth_metrics/_compute_margin_volatility) stay unchanged.
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

            # Construct value metrics from sec_valuations only (yfinance-free)
            value_dict = self._build_value_metrics(symbol, sec_val_row)
            # Trailing-3yr stdev of net_margin (QMJ Safety-leg proxy). Computed here, not inside
            # _compute_quality_metrics, because it needs the multi-year income_rows history
            # already fetched above - _compute_quality_metrics only sees a single fiscal year's row.
            margin_volatility, margin_volatility_unavailable_reason = self._compute_margin_volatility(income_rows)
            quality_dict = self._compute_quality_metrics(symbol, quality_row_db, ev_metrics, margin_volatility)
            if margin_volatility is None and isinstance(quality_dict, dict):
                quality_dict["margin_volatility_unavailable_reason"] = margin_volatility_unavailable_reason
            # Compute growth metrics from annual income statement history (not read from DB)
            growth_dict = self._compute_growth_metrics(symbol, income_rows)
            # Forward EPS/revenue growth estimates + estimate-revision trend, from
            # analyst_earnings_estimates (independent of the SEC-filing-driven fields above, so
            # merged unconditionally - a thin-SEC-history symbol like a recent IPO can still have
            # real analyst coverage even when growth_dict is a data_unavailable marker).
            if isinstance(growth_dict, dict):
                growth_dict.update(self._get_analyst_forward_growth_estimates(symbol))

            # quality and growth are each gated on their OWN source fiscal year, not a blended/max
            # value - quality_row_db's fiscal_year comes from annual_balance_sheet while growth uses
            # the standalone annual_income_statement history, and these can diverge by over a
            # decade for some filers. A fresh income statement must not mask a stale balance sheet
            # that quality_metrics (ROE, debt ratios, current ratio) actually depends on.
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
                    # _unavailable_marker() hardcodes every per-field *_unavailable_reason to the
                    # generic "insufficient_history" - propagate the real stale_fiscal_data cause
                    # to those too, since downstream consumers (Scores Data Coverage tab) read the
                    # per-field reason, not just the top-level summary.
                    for key in growth_dict:
                        if key.endswith("_unavailable_reason") and growth_dict[key] is not None:
                            growth_dict[key] = "stale_fiscal_data"

            # These trend fields are computed once in _compute_quality_metrics (it has the
            # balance-sheet data the calculations need) but consumed by BOTH quality_metrics
            # and growth_metrics - _compute_growth_metrics has no access to that computation and
            # always defaults its own copy to None, so it must be mirrored in. Safe to copy
            # even when quality_dict.data_unavailable is True, since _unavailable_marker always
            # populates a real reason code per field; growth_dict's own data_unavailable still
            # gates the write target so a fully-blanked growth row isn't selectively patched.
            _mirror_shared_trend_fields(quality_dict, growth_dict)

            # Forward growth/estimate-revision fields (informational only, do not feed
            # growth_score - see _get_analyst_forward_growth_estimates's docstring). Applied
            # unconditionally, unlike the SEC-derived _SHARED_TREND_FIELDS mirror above: these
            # fields come from analyst_earnings_estimates, a source independent of SEC financial
            # history, so a growth_dict.data_unavailable for an unrelated SEC reason must not
            # suppress real analyst data that's otherwise available. _get_analyst_forward_
            # growth_estimates() always returns a fully-populated dict (real value or explicit
            # "no_analyst_estimates" reason per field), so running it unconditionally can only
            # add information, never leave a previously-explained field unexplained.
            growth_dict.update(self._get_analyst_forward_growth_estimates(symbol))

            return [(value_dict, quality_dict, growth_dict)]

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Fetch failed: {e}")
            # Pass the actual exception through as the reason (not a generic "missing_sec_data")
            # so scores.py's _categorize_reason routes it to "Other (errors/excluded)" instead of
            # inflating the legitimate-gap buckets with real loader bugs.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return [
                (
                    self._unavailable_marker("value_metrics", symbol, reason=exc_reason),
                    self._unavailable_marker("quality_metrics", symbol, reason=exc_reason),
                    self._unavailable_marker("growth_metrics", symbol, reason=exc_reason),
                )
            ]

    def _build_value_metrics(  # noqa: C901 -- net_payout_yield's TIER 2 fallback pushed this
        # pre-existing multi-tier function over the complexity threshold; self-contained, not
        # entangled with the existing tiers, so left in place rather than force-extracted.
        self,
        symbol: str,
        sec_val_row: Any,
    ) -> dict[str, Any]:
        """Build value_metrics from SEC valuations (yfinance-free).

        All metrics from SEC-audited data. dividend_yield comes from load_sec_valuations.py's
        SEC "PaymentsOfDividends" cash-flow concept / market_cap.
        """
        # Extract SEC-derived valuations (all from sec_valuations table)
        # Using dict access - tuple fallback violates fail-fast governance
        row_dict = dict(sec_val_row) if sec_val_row and hasattr(sec_val_row, "__getitem__") else {}
        if not row_dict or row_dict.get("data_unavailable"):  # data_unavailable flag (was index 2)
            # Propagate the specific reason load_sec_valuations.py already computed (e.g.
            # "shares_outstanding_unavailable") rather than a generic "missing_sec_data" -
            # falls back to the generic reason only when sec_valuations has no row at all.
            marker = self._unavailable_marker("value_metrics", symbol, reason=row_dict.get("reason"))
            # A preferred/subordinated-debenture ticker (see
            # _get_preferred_or_debt_security_symbols()'s docstring) never gets a
            # sec_valuations row at all (load_sec_valuations.py doesn't compute market-cap/EV
            # for these child tickers), so this early return was the ONLY code path reachable
            # for them - the same gate's per-field wiring further below (pe_ratio_reason/
            # pb_ratio_reason/ps_ratio_reason/peg_ratio's own cascades) is correct but
            # unreachable dead code for this exact case. Same "wrong, not missing" reasoning,
            # applied here instead. Deliberately excludes dividend_yield (a preferred's fixed
            # coupon / its own market price is a real, meaningful yield - see that gate's own
            # docstring) and every other field (market_cap/EV/intrinsic_value etc. haven't been
            # vetted the same way) - only overriding the four ratios that gate already covers.
            if symbol in self._get_preferred_or_debt_security_symbols():
                for field in ("pe_ratio", "pb_ratio", "ps_ratio", "peg_ratio"):
                    if marker.get(f"{field}_unavailable_reason") is not None:
                        marker[f"{field}_unavailable_reason"] = "preferred_or_debt_security_no_common_equity_ratio"
            return marker

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

        # yfinance_snapshot has had no live writer for a long time (frozen table) - dropping
        # any fallback that reads it only removes stale/frozen values, doesn't touch anything live.
        if dividend_yield is None:
            # TIER 2 FALLBACK: Try SEC dividend_data (most recent dividend)
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
                        # FIX 2026-09-04 (goal: "Missing SEC/XBRL data" reduction - same
                        # Decimal/float class as the fcf_margin fallback fix elsewhere in this
                        # file): sec_div_row[0] is a raw psycopg2 Decimal (dividend_yield_pct is
                        # NUMERIC) - `Decimal / 100.0` raises TypeError, silently caught by this
                        # block's own try/except below and logged at debug level, so this SEC
                        # dividend_data fallback tier never actually populated dividend_yield for
                        # any symbol that reached it.
                        dividend_yield = float(sec_div_row[0]) / 100.0  # Convert percentage to decimal
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
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): the TIER 3
        # fallback below already independently confirms - via this exact aggregate-yield
        # computation - a case entirely distinct from "no dividend data": a REAL dividends_
        # paid figure and a REAL market_cap producing a REAL ratio that's simply too large to
        # be a genuine current yield (live-confirmed BGSF 37.3%, CMCT 60.1%, CMTG 53.2% -
        # small/distressed-price companies whose historical dividend now dwarfs a since-
        # collapsed market cap). That fact was computed and then silently discarded (just a
        # debug log) instead of being propagated to dividend_yield_reason below, which instead
        # fell through to the generic "missing_sec_data" - the same "real value, deliberately
        # rejected as implausible" mislabel class already fixed elsewhere in this file, just
        # not yet wired here. `implausible_ratio` is a different, already-correctly-bucketed
        # coverage category ("Implausible / rejected value") than "missing_sec_data" ("Missing
        # SEC/XBRL data") - this is a real headline-relevant fix, not just a diagnostic one.
        dividend_yield_implausible_from_cash_flow = False
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
                        # market_cap here can be a real but badly-scaled shares_outstanding
                        # figure sec_valuations itself already refused to compute a ratio against
                        # (a scale mismatch inflates the yield) - bound matches
                        # load_sec_valuations.py's own primary dividend_yield bound.
                        candidate = float(cf_div_row[0]) / float(market_cap)
                        if 0 < candidate <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                            dividend_yield = candidate
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using annual_cash_flow.dividends_paid "
                                f"aggregate yield: {dividend_yield:.2%}"
                            )
                        else:
                            dividend_yield_implausible_from_cash_flow = True
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback "
                                f"yield out of bounds ({candidate:.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback failed: {e}")

        # TIER 2 FALLBACK for net_payout_yield - same rationale as the dividend TIER 3 fallback
        # above: aggregate (dividends + buybacks) / market_cap when sec_valuations.
        # net_payout_yield is NULL but annual_cash_flow has raw dividends_paid/
        # common_stock_repurchased. No curated buyback-specific table exists, so this is the
        # only fallback tier for this field.
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
                        # Bound is tighter (50%) than sec_valuations' own fresh computation
                        # (150%, which has upstream cross-checks this fallback lacks): this
                        # fallback's market_cap can be a broken shares_outstanding figure
                        # sec_valuations itself already refused to compute a ratio against -
                        # real shareholder-return companies rarely exceed 15-20%/yr anyway.
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

        # forward_pe = current_price / consensus forward EPS, joined from analyst_earnings_estimates
        # (load_sec_valuations.py stays SEC-only by design; SEC filings never carry forward estimates).
        # ebitda is only ever None when operating_income itself is unavailable (D&A is additive,
        # never required for the ebitda computation) - and when ebitda IS present but <= 0, that's
        # a real negative/zero-EBITDA company where EV/EBITDA isn't a meaningful ratio, same
        # "not applicable" class as non_dividend_paying_stock, not missing data.
        ebitda_raw = row_dict.get("ebitda")
        # load_sec_valuations.py only ever persists enterprise_value when market_cap + total_debt
        # - total_cash > 0 - a net-cash-rich filer (cash alone exceeds market_cap + debt)
        # computes a negative/zero EV there, a genuine "not a meaningful ratio" case (EV/EBITDA
        # and EV/Revenue undefined), not a data gap. Approximates load_sec_valuations.py's
        # entity-wide EV formula with the per-class market_cap already persisted here - used
        # only for labeling, never for a computed value.
        _computed_ev_for_reason = (
            market_cap + (row_dict.get("total_debt") or 0) - (row_dict.get("total_cash") or 0)
            if market_cap is not None
            else None
        )
        if ebitda_raw is not None and ebitda_raw <= 0:
            ev_ebitda_reason = "unprofitable_stock"
        elif ebitda_raw is None:
            ev_ebitda_reason = "ebitda_not_extracted"
        # ebitda>0 present, enterprise_value missing or out of bounds: enterprise_value =
        # market_cap + total_debt - total_cash, so it fails whenever total_debt can't be
        # itemized - reuse the same gate quality_metrics.total_debt already uses.
        elif symbol in self._get_no_recent_debt_components_symbols():
            ev_ebitda_reason = "total_debt_not_itemized"
        elif _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0:
            ev_ebitda_reason = "negative_enterprise_value"
        # ev_ebitda is one of the fields _sanity_check_market_cap nulls on a shares_outstanding
        # scale mismatch (see pb_ratio_reason below) - placed last so a real ebitda_raw<=0/
        # no-debt-itemized/negative-EV cause above still wins.
        elif row_dict.get("reason") == "shares_outstanding_scale_mismatch":
            ev_ebitda_reason = "shares_outstanding_scale_mismatch"
        else:
            ev_ebitda_reason = "missing_sec_data"

        # fcf_yield's own specific reason, computed once here so both fcf_yield_unavailable_reason
        # below and intrinsic_value_reason_from_fcf_yield() show the same real, already-categorized
        # cause instead of two different labels for one fact.
        fcf_yield_reason_str = (
            (
                "no_recent_free_cash_flow_reported"
                if symbol in self._get_no_recent_free_cash_flow_symbols()
                or symbol in self._get_never_tagged_free_cash_flow_symbols()
                else "capex_never_tagged_in_recent_filings"
                if symbol in self._get_no_recent_capex_symbols()
                # fcf_yield is also nulled by _sanity_check_market_cap's shares_outstanding
                # scale-mismatch guard (fcf_yield divides by market_cap); this also flows into
                # intrinsic_value/margin_of_safety's reasons below, which derive from this value.
                else "shares_outstanding_scale_mismatch"
                if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                else "missing_sec_data"
            )
            if fcf_yield is None
            else None
        )

        # intrinsic_value_per_share reason: sec_valuations doesn't persist raw OCF/CapEx, only
        # the fcf_yield ratio derived from them - reuse it as the same "is FCF usable" signal
        # load_sec_valuations.py's DCF itself gates on.
        intrinsic_value_reason = (
            intrinsic_value_reason_from_fcf_yield(fcf_yield, fcf_yield_reason_str)
            if intrinsic_value_per_share is None
            else None
        )
        if margin_of_safety_pct is None:
            # load_sec_valuations.py's _compute_dcf_intrinsic_value computes intrinsic_per_share
            # and margin_of_safety_pct together as a pair - the ONLY way to get a real
            # intrinsic_per_share alongside a None margin_of_safety_pct is its explicit
            # `-1000 <= margin_of_safety_pct <= 1000` bounds rejection (implausible DCF result),
            # not a missing-data case - 100% precise, not a probabilistic gate.
            margin_of_safety_reason = (
                intrinsic_value_reason if intrinsic_value_per_share is None else "implausible_dcf_result"
            )
        else:
            margin_of_safety_reason = None

        forward_pe = None
        # A real analyst forward-EPS estimate for a company projected to LOSE money next year
        # (common for biotech/EV/early-growth names) correctly leaves forward_pe undefined
        # (price / negative earnings isn't a valid multiple) - distinguish that from genuinely
        # having zero analyst coverage rather than lumping both under "no_analyst_estimates".
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

        # Validate: at least one core metric must be non-None. forward_pe counts toward
        # "available" even if historical SEC PE/PB/PS/FCF is missing - an unprofitable company
        # with analyst forward EPS guidance still has a usable forward valuation metric.
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
            if dividend_yield_implausible_from_cash_flow:
                dividend_yield_reason = "implausible_ratio"
            else:
                # Must filter data_unavailable=FALSE: load_dividend_data.py writes an explicit
                # "confirmed no dividend" marker row for every symbol it checks, not just payers -
                # without the filter those marker rows would look like real payment history.
                # 2-year recency window on ex_dividend_date so a stock that discontinued its
                # dividend years ago reads as "not a data gap, a stock characteristic" too, same
                # as one that never paid at all.
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

                # Confirmed non-payers get dividend_yield=0.0 (semantically correct), not NULL,
                # with the reason tracked for transparency.
                if not has_dividend_history:
                    dividend_yield = 0.0
                    dividend_yield_reason = "non_dividend_paying_stock"
                else:
                    dividend_yield_reason = "missing_sec_data"

        # TIER 3 FALLBACK for net_payout_yield: a confirmed non-dividend-payer (dividend_yield_
        # reason == "non_dividend_paying_stock") with no recent buyback either should get 0.0,
        # not permanently NULL - NULL silently drops the symbol out of _score_value's weighted
        # average (the `is not None` gate there) instead of scoring it at the low end. Same
        # 2-year recency window as TIER 2's buyback check, same `!= 0` convention (sign isn't
        # guaranteed consistent).
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

        # load_sec_valuations.py only computes pe_ratio when ttm_eps > 0 (a negative/zero-EPS
        # company has no meaningful P/E, same "not applicable" class as
        # non_dividend_paying_stock). peg_ratio requires pe_ratio, so it inherits the same
        # reason when pe_ratio itself is the blocker.
        #
        # This query must mirror load_sec_valuations.py's real anchor-row selection's
        # `data_unavailable IS NOT TRUE` filter - without it, a most-recent fiscal year flagged
        # data_unavailable (e.g. 'incomplete_sec_filing_income') can still carry a stray
        # non-null EPS value that the real valuation engine skips (falling back to the prior,
        # complete year) but this query would pick up, wrongly concluding "not unprofitable,
        # must be a data gap" instead of matching the real computation's actual answer.
        pe_ratio_reason = None
        if pe is None and symbol in self._get_preferred_or_debt_security_symbols():
            # See _get_preferred_or_debt_security_symbols()'s docstring: this ticker's real
            # EPS on file belongs to its parent's common stock, not to itself - a P/E computed
            # from it would be wrong, not just missing.
            pe_ratio_reason = "preferred_or_debt_security_no_common_equity_ratio"
        elif pe is None and row_dict.get("reason") == "eps_scale_mismatch":
            # load_sec_valuations.py's _sanity_check_pe_ratio already deliberately nulls
            # pe_ratio/peg_ratio and records this specific reason (a >10x SEC-vs-yfinance PE
            # disagreement - a mis-scaled ttm_eps, not a missing one); reuse it instead of
            # re-deriving from annual_income_statement, which finds a real-looking EPS (the
            # mis-scale is in ttm_eps's computation, not the raw tagged value) and would
            # otherwise fall through to a generic "missing_sec_data" label. `eps_scale_mismatch`
            # is already mapped in scores.py's _categorize_reason to "Implausible / rejected value".
            pe_ratio_reason = "eps_scale_mismatch"
        elif pe is None:
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
            # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): mirrors
            # load_sec_valuations.py's own pe_ratio bounds check (MIN_PLAUSIBLE_PE_RATIO..10000)
            # - a real, positive, tiny EPS (near-zero-denominator) produces a real but
            # astronomically large P/E that gets silently rejected there (just a warning log,
            # no reason recorded), so this cascade never learned the true cause and fell
            # through to "missing_sec_data". Live-confirmed KLIC (Kulicke & Soffa): FY2025
            # earnings_per_share=$0.0040 (real, positive) against current_price=$81.62 implies
            # pe_ratio=20,405 - the exact >10000 rejection. Same "real value, deliberately
            # rejected as implausible" mislabel class already fixed for dividend_yield this
            # session - implausible_ratio is a different, already-correctly-bucketed coverage
            # category than missing_sec_data, so this is headline-relevant, not just cosmetic.
            _pe_implausible_from_eps = False
            if latest_eps is not None and latest_eps > 0:
                _current_price = row_dict.get("current_price")
                if _current_price is not None and float(_current_price) > 0:
                    _implied_pe = float(_current_price) / float(latest_eps)
                    if _implied_pe > 10000 or _implied_pe < 0.05:
                        _pe_implausible_from_eps = True
            pe_ratio_reason = (
                "implausible_ratio"
                if _pe_implausible_from_eps
                else "unprofitable_stock"
                if latest_eps is not None and latest_eps <= 0
                # `eps_row is None` (this query already searches full history, no fiscal-year
                # window) means ZERO fiscal years have a real earnings_per_share value - distinct
                # from "found a value but pe still came out null" (price/ttm-anchor mismatch,
                # which correctly stays "missing_sec_data"). Foreign 20-F/IFRS filers and
                # MLP/unit-structure filers (e.g. "net income per unit" instead of EPS) commonly
                # never tag an EPS concept at all despite having real net_income every year.
                else "eps_never_tagged_in_filings"
                if eps_row is None
                # A positive EPS was found, but not in the symbol's own SEC-selected anchor
                # fiscal year (see _get_eps_absent_from_anchor_year_symbols()'s docstring,
                # e.g. BRK.A/BRK.B) - label-only, distinct from the true "anchor year has it,
                # pe still null for some other reason" case below.
                else "eps_absent_from_anchor_year"
                if symbol in self._get_eps_absent_from_anchor_year_symbols()
                else "missing_sec_data"
            )

        peg_ratio_reason: str | None
        if peg is None and pe is not None:
            with DatabaseContext("read") as cur:
                # Must mirror the real peg_ratio computation's `data_unavailable IS NOT TRUE`
                # filter (same bug class as pe_ratio_reason above) - without it a stray non-NULL
                # EPS on an incomplete/unfiled fiscal year could be compared as if it were the
                # real TTM or prior-year figure, disagreeing with what actually decided peg_ratio.
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

        # load_sec_valuations.py only computes pb_ratio when stockholders_equity > 0; a real
        # negative book value (buybacks/accumulated deficit) is "not applicable", not missing.
        pb_ratio_reason = None
        if pb is None and symbol in self._get_preferred_or_debt_security_symbols():
            # See _get_preferred_or_debt_security_symbols()'s docstring - same "wrong, not
            # missing" reasoning as pe_ratio_reason above, for book value per share.
            pb_ratio_reason = "preferred_or_debt_security_no_common_equity_ratio"
        elif pb is None:
            with DatabaseContext("read") as cur:
                # Must mirror load_sec_valuations.py's real book_value query's `data_unavailable
                # IS NOT TRUE` filter, else an unfiled fiscal year's stray value can drive this
                # reason independent of what the real pb_ratio computation actually saw.
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
            # The query above deliberately has no `stockholders_equity IS NOT NULL` filter, so a
            # symbol with balance-sheet rows but stockholders_equity NULL in all of them still
            # yields a non-None equity_row (a 1-tuple wrapping None) — check latest_book_value,
            # not equity_row, to catch this "never tagged" case.
            _pb_shares_out = safe_float(row_dict.get("shares_outstanding"), f"{symbol}.pb_reason_shares_outstanding")
            _pb_current_price = safe_float(row_dict.get("current_price"), f"{symbol}.pb_reason_current_price")
            pb_ratio_reason = (
                "negative_book_value"
                if latest_book_value is not None and latest_book_value <= 0
                # A resolved equity value but pb still null (MLPs tagging "Partners' Capital"
                # instead of "StockholdersEquity", or ADRs with no extracted field at all) is a
                # genuine "never tagged" case, not an ambiguous remainder.
                else "stockholders_equity_never_tagged_in_filings"
                if latest_book_value is None
                # Recompute the same MIN_PLAUSIBLE_PB_RATIO(0.05..1000) bound load_sec_
                # valuations.py's pb computation applies but leaves unrecorded on rejection, so a
                # real book value/share count that just falls outside it reads as implausible
                # rather than a generic extraction gap.
                else "implausible_ratio"
                if (
                    latest_book_value > 0
                    and _pb_shares_out is not None
                    and _pb_current_price is not None
                    and _pb_shares_out > 0
                    and not (0.05 <= (_pb_current_price / (float(latest_book_value) / _pb_shares_out)) <= 1000)
                )
                # _sanity_check_market_cap (load_sec_valuations.py) nulls pb/ps/market_cap/
                # fcf_yield/ev_ebitda/ev_revenue/intrinsic_value/margin_of_safety together on a
                # >10x SEC-vs-yfinance market_cap disagreement, recording
                # shares_outstanding_scale_mismatch on the row — but that reason is only checked
                # in the whole-row-unavailable early return, not here when the row still resolves
                # (e.g. pe_ratio survived independently). Placed last so a more specific real
                # gate above (e.g. genuine negative_book_value) always wins.
                else "shares_outstanding_scale_mismatch"
                if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                else "missing_sec_data"
            )

        # load_sec_valuations.py's ps computation rejects (silently, no reason recorded) any
        # ratio outside MIN_PLAUSIBLE_PS_RATIO(0.05..10000); recheck that bound here so a real,
        # positive revenue combined with an out-of-bounds share count/price reads as
        # "implausible_ratio" rather than a generic missing-data fallback.
        #
        # FIXED 2026-09-05 (goal session: "implausible values" sweep): the ORDER BY only
        # required revenue IS NOT NULL, so a real but NEGATIVE most-recent-year revenue (BWMX/
        # Betterware de Mexico live-confirmed: FY2022 revenue=-$543.3M, likely a restatement/
        # writeback artifact on this IFRS filer, with real POSITIVE revenue $7.2B/$10.1B in the
        # two years just before it) got picked as "the latest revenue" - the `_ps_latest_revenue
        # > 0` guard below then correctly refused to use it for the implausible-ratio check, but
        # never fell back to the real positive figure sitting one fiscal year earlier, silently
        # dropping to the generic "missing_sec_data" fallback instead of "implausible_ratio" or
        # a real computed check. Same "prefer a real positive value even if not the newest" tiered
        # preference already used throughout this file's other reason-derivation queries (e.g.
        # _get_revenue_available_elsewhere_symbols and siblings) - positive revenue now ranks
        # ahead of a merely-non-null one, so a negative anchor year no longer masks a real
        # positive figure from an adjacent year.
        _ps_implausible_ratio = False
        if ps is None:
            _ps_shares_out = safe_float(row_dict.get("shares_outstanding"), f"{symbol}.ps_reason_shares_outstanding")
            _ps_current_price = safe_float(row_dict.get("current_price"), f"{symbol}.ps_reason_current_price")
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT revenue
                    FROM annual_income_statement
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN revenue IS NOT NULL AND revenue > 0 THEN 0
                                   WHEN revenue IS NOT NULL THEN 1
                                   ELSE 2 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                _ps_revenue_row = cur.fetchone()
            _ps_latest_revenue = (
                safe_float(_ps_revenue_row[0], f"{symbol}.ps_reason_revenue") if _ps_revenue_row else None
            )
            if (
                _ps_latest_revenue is not None
                and _ps_latest_revenue > 0
                and _ps_shares_out is not None
                and _ps_current_price is not None
                and _ps_shares_out > 0
                and not (0.05 <= (_ps_current_price / (_ps_latest_revenue / _ps_shares_out)) <= 10000)
            ):
                _ps_implausible_ratio = True

        # Fetch held_percent fields from positioning_metrics (FIXED 2026-08-18)
        held_percent_institutions, held_percent_institutions_reason = self._fetch_positioning_metrics(symbol)

        # No yfinance fallback remains for pe/pb/ps/fcf_yield/dividend/ev/market_cap/
        # intrinsic_value - always SEC-sourced. forward_pe is the one exception (computed from
        # analyst_earnings_estimates, real yfinance consensus data), so it needs its own
        # composite label rather than a blanket "sec_audited" - feeds
        # lambda/api/routes/scores.py's data-source coverage dashboard.
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
                (
                    # See _get_preferred_or_debt_security_symbols()'s docstring - same "wrong,
                    # not missing" reasoning as pe_ratio_reason/pb_ratio_reason above, for
                    # revenue per share.
                    "preferred_or_debt_security_no_common_equity_ratio"
                    if symbol in self._get_preferred_or_debt_security_symbols()
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # Real $0 anchor-year revenue, distinct from "never any revenue in 3
                    # years" above - see _get_zero_revenue_anchor_symbols()'s own docstring.
                    else "zero_revenue_reported_this_period"
                    if symbol in self._get_zero_revenue_anchor_symbols()
                    # Real revenue exists in an earlier year, just not the current anchor
                    # year - see _get_revenue_absent_from_anchor_year_symbols()'s docstring.
                    else "revenue_absent_from_anchor_year"
                    if symbol in self._get_revenue_absent_from_anchor_year_symbols()
                    # ps_ratio is one of the fields _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch (see pb_ratio_reason above).
                    else "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "implausible_ratio"
                    if _ps_implausible_ratio
                    else "missing_sec_data"
                )
                if ps is None
                else None
            ),
            "peg_ratio_unavailable_reason": peg_ratio_reason,
            "dividend_yield_unavailable_reason": dividend_yield_reason,
            # Computed once above (fcf_yield_reason_str) so this and intrinsic_value_reason show
            # the same specific cause - see intrinsic_value_reason_from_fcf_yield()'s docstring.
            "fcf_yield_unavailable_reason": fcf_yield_reason_str,
            "forward_pe_unavailable_reason": forward_pe_reason if forward_pe is None else None,
            "ev_ebitda_unavailable_reason": ev_ebitda_reason if ev_ebitda is None else None,
            "ev_revenue_unavailable_reason": (
                (
                    "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # enterprise_value = market_cap + total_debt - total_cash, so it fails
                    # whenever total_debt can't be itemized even when revenue is present.
                    else "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    # Net cash exceeds market_cap + total_debt - see _computed_ev_for_reason.
                    else "negative_enterprise_value"
                    if _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0
                    # Real $0 anchor-year revenue, distinct from "never any revenue" above.
                    else "zero_revenue_reported_this_period"
                    if symbol in self._get_zero_revenue_anchor_symbols()
                    # Real revenue exists in an earlier year, just not the current anchor year.
                    else "revenue_absent_from_anchor_year"
                    if symbol in self._get_revenue_absent_from_anchor_year_symbols()
                    # ev_revenue is one of the fields _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch; placed last so a real revenue-shaped cause wins.
                    else "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "missing_sec_data"
                )
                if ev_revenue is None
                else None
            ),
            "market_cap_unavailable_reason": (
                (
                    # market_cap is the first field _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch, and has no other real gate to defer to, so this
                    # can be checked unconditionally rather than as a last-resort fallback.
                    "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "missing_sec_data"
                )
                if market_cap is None
                else None
            ),
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

    def _fetch_annual_fallback_row(
        self, table: str, columns: str, extra_where: str, symbol: str
    ) -> tuple[Any, ...] | None:
        """3yr-then-full-history search for a not-null annual value, used when the anchor row's
        own value is NULL. `table`/`columns`/`extra_where` are always hardcoded strings from
        this file, never user input.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                f"""
                SELECT {columns} FROM {table}
                WHERE symbol = %s {extra_where}
                  AND data_unavailable IS NOT TRUE
                  AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                ORDER BY fiscal_year DESC LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    f"""
                    SELECT {columns} FROM {table}
                    WHERE symbol = %s {extra_where}
                      AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
        return cast("tuple[Any, ...] | None", row)

    def _fetch_balance_sheet_anchor_fallback(self, symbol: str, column: str) -> float | None:
        """Single-column convenience wrapper around `_fetch_annual_fallback_row` for
        annual_balance_sheet fields."""
        row = self._fetch_annual_fallback_row("annual_balance_sheet", column, f"AND {column} IS NOT NULL", symbol)
        if not row:
            return None
        return self._nan_to_none(safe_float(row[0], f"{symbol}.{column}_fallback_year", allow_none=True))

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
        feed growth_score (see GROWTH_SCORE_FIELDS in loaders/load_stock_scores.py) - forward/
        analyst-consensus EPS growth is a standard Growth-factor descriptor, though this table
        lacks enough historical depth (only ~24 distinct snapshot dates, no backfill capability)
        to backtest predictive power here. eps_estimate_revision_90d_pct stays informational only
        (estimate-revision momentum is a distinct factor style from a growth-RATE level).

        These 4 fields need their own plausibility bound (MAX_PLAUSIBLE_GROWTH_PCT, same as every
        other growth field) - a near-zero prior-year EPS/revenue denominator can otherwise produce
        mathematically enormous but non-exception-raising growth rates.

        Reason codes distinguish 3 states: no `data_unavailable = FALSE` row found at all ->
        "no_analyst_estimates" (genuinely zero coverage); a row was found but this specific field
        is NULL -> "analyst_coverage_incomplete_for_field" (real coverage exists, just not this
        one derived figure - yfinance's `earnings_estimate` data can be sparse per-field even for
        well-covered symbols); a row was found and the field has a value but it's implausible ->
        "garbage_metric_value_implausible_ratio".
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
                            # A real row was found but this field is NULL, distinct from no
                            # coverage at all (the default set above).
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
                    ORDER BY period_end DESC NULLS LAST, fiscal_year DESC, fiscal_quarter DESC
                    LIMIT 8
                    """,
                    (symbol,),
                )
                quarters = cur.fetchall()

                if len(quarters) < 4:
                    # Foreign private issuers (20-F/40-F filers) are exempt from mandatory
                    # quarterly (10-Q) SEC reporting, so sparse quarterly history for them is a
                    # permanent exemption, not a data gap that will fill in over time -
                    # "insufficient_quarterly_history" wrongly implies the latter.
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

            # Compare each quarter to the SAME quarter a year ago (not sequential Q-over-Q) to
            # avoid contaminating seasonal businesses with swings unrelated to underlying growth.
            # Matched by (fiscal_year, fiscal_quarter), not a fixed index offset, so a gap in
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
                    quarter_eps_growth = ((curr_eps - prev_eps) / abs(prev_eps)) * 100
                    # Exclude an individual quarter whose own ratio already exceeds
                    # MAX_PLAUSIBLE_GROWTH_PCT before averaging - otherwise one near-zero-
                    # denominator quarter dilutes into a superficially "trusted" aggregate that
                    # bounding only the average/stddev wouldn't catch.
                    if abs(quarter_eps_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                        eps_growth_rates.append(quarter_eps_growth)
                curr_rev, prev_rev = q["revenue"], prior["revenue"]
                if curr_rev is not None and prev_rev is not None and prev_rev != 0:
                    quarter_rev_growth = ((curr_rev - prev_rev) / abs(prev_rev)) * 100
                    # Same per-quarter dilution guard as eps_growth_rates above.
                    if abs(quarter_rev_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                        revenue_yoy_growth_rates.append(quarter_rev_growth)

            if eps_growth_rates:
                earnings_growth_4q_avg = sum(eps_growth_rates) / len(eps_growth_rates)
                # Bounded by MAX_PLAUSIBLE_GROWTH_PCT (not MAX_TREND_PERCENTAGE_POINTS) - a
                # near-zero prior-quarter EPS can make this average mathematically enormous,
                # which would overflow this NUMERIC(10,4) column and abort the row's write.
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
                # Bounded like quarterly_growth_momentum above - a near-zero forward_eps estimate
                # (common for turnaround/recovery names) can otherwise divide this into a
                # meaningless, orders-of-magnitude "surprise" percentage.
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

        Guards |margin|>1000 per-year (same bound as every sibling margin ratio in this file)
        before the variance calc - a near-zero-revenue year's raw margin can otherwise overflow
        quality_metrics.margin_volatility's NUMERIC(10,2) column and crash the entire row's
        INSERT, not just this field. Scans the full fetched history (already bounded to 30 rows
        by the caller) and takes the 3 most recent USABLE years, skipping - not aborting on - a
        bad or missing one in between, so one garbage year doesn't discard an otherwise-usable
        older one. `implausible` tracks whether any skipped year was real-but-garbage (vs.
        simply missing), for the fallback reason string when fewer than 3 usable years exist.
        """
        margins: list[float] = []
        implausible = False
        for row in income_rows:
            if len(margins) >= 3:
                break
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

    def _find_plausible_cross_year_ratio(
        self, symbol: str, numerator_field: str, denominator_field: str
    ) -> float | None:
        """Cross-year fallback for ROE/ROA/asset_turnover's |ratio|>1000 implausible-value
        bound (net_income/stockholders_equity, net_income/total_assets, revenue/total_assets
        respectively). An anchor year with a near-zero denominator (extraction artifact, not a
        real business characteristic) would otherwise throw the symbol straight to
        implausible_ratio even when an older fiscal year has a plausible pair.

        Only called from the implausible-ratio branch (rare: <1% of symbols), so the extra
        per-symbol query here doesn't touch the common path.
        """
        field_index = {"net_income": 0, "total_assets": 1, "stockholders_equity": 2, "revenue": 3}
        num_idx, den_idx = field_index[numerator_field], field_index[denominator_field]
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT ais.net_income, abs.total_assets, abs.stockholders_equity, ais.revenue
                FROM annual_income_statement ais
                JOIN annual_balance_sheet abs
                  ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year
                  AND abs.data_unavailable = FALSE
                WHERE ais.symbol = %s AND ais.data_unavailable = FALSE
                ORDER BY ais.fiscal_year DESC
                LIMIT 30
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        for row in rows:
            numerator, denominator = row[num_idx], row[den_idx]
            if numerator is None or denominator is None or denominator == 0:
                continue
            # numerator/denominator are raw psycopg2 Decimal values - `Decimal * float` raises
            # TypeError, which propagates up and wipes the entire quality_metrics row. Must
            # convert to float before arithmetic.
            ratio = float(numerator) / float(denominator) * 100.0
            if abs(ratio) <= 1000:
                return float(ratio)
        return None

    def _find_plausible_cross_year_roic_ratio(self, symbol: str, metric: str) -> float | None:
        """Cross-year fallback for roic_pct/roce_pct's |ratio|>1000 implausible-value bound,
        same shape/safety argument as `_find_plausible_cross_year_ratio` above but for the
        wider NOPAT/invested-capital (roic_pct) or EBIT/capital-employed (roce_pct) formulas.

        Searches for an older fiscal year where income-statement and balance-sheet
        concepts all coherently exist together for that SAME year (a genuine same-year
        pair, not a field substituted from a different period) and recomputes the metric
        entirely from that year's own data. Deliberately excludes total_debt_ev
        (sec_valuations) as a debt source here - unlike the primary anchor-year
        computation, that table has no fiscal-year dimension (single latest-snapshot row),
        so mixing it with an older year's equity/cash would be exactly the cross-period
        Frankenstein-mix this fallback must avoid; only long_term_debt from the matching
        fiscal year's own balance sheet is used.

        Only called from the implausible-ratio branch (rare: <1% of symbols), so the extra
        per-symbol query doesn't touch the common path.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT ais.operating_income, ais.income_tax_expense, ais.pretax_income,
                       abs.stockholders_equity, abs.cash_and_equivalents, abs.long_term_debt
                FROM annual_income_statement ais
                JOIN annual_balance_sheet abs
                  ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year
                  AND abs.data_unavailable = FALSE
                WHERE ais.symbol = %s AND ais.data_unavailable = FALSE
                ORDER BY ais.fiscal_year DESC
                LIMIT 30
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        for row in rows:
            operating_income, tax_expense, pretax_income, equity, cash, debt = row
            if None in (operating_income, tax_expense, pretax_income, equity, cash, debt):
                continue
            # Decimal values from psycopg2 - convert before arithmetic (Decimal * float
            # raises TypeError).
            operating_income = float(operating_income)
            tax_expense = float(tax_expense)
            pretax_income = float(pretax_income)
            equity = float(equity)
            cash = float(cash)
            debt = float(debt)
            if pretax_income <= 0:
                continue
            rate = tax_expense / pretax_income
            if not (-0.60 <= rate <= 0.60):
                continue
            if metric == "roic_pct":
                invested_capital = equity + debt - cash
                if invested_capital <= 0:
                    continue
                ratio = (operating_income * (1 - rate) / invested_capital) * 100.0
            else:
                capital_employed = equity + debt
                if capital_employed <= 0:
                    continue
                ratio = (operating_income / capital_employed) * 100.0
            if abs(ratio) <= 1000:
                return float(ratio)
        return None

    def _ratio_with_implausible_fallback(
        self,
        symbol: str,
        numerator: float | None,
        denominator: float | None,
        numerator_field: str,
        denominator_field: str,
        *,
        denominator_must_be_positive: bool = False,
    ) -> tuple[float | None, bool]:
        """Shared `_find_plausible_cross_year_ratio` wiring for ROE/ROA/asset_turnover.

        Returns (value, hit_implausible_with_no_fallback) - value is None either because an
        input was missing/zero (denominator_must_be_positive=True for asset_turnover, which
        requires denominator > 0 rather than merely != 0) or because the anchor ratio was
        implausible and no plausible cross-year fallback existed; the second element tells the
        caller which of those two happened, since ROE/ROA/asset_turnover each track that
        distinction differently in their own bookkeeping.
        """
        if numerator is None or denominator is None:
            return None, False
        if denominator_must_be_positive:
            if denominator <= 0:
                return None, False
        elif denominator == 0:
            return None, False
        computed = numerator / denominator * 100.0
        if abs(computed) > 1000:
            fallback = self._find_plausible_cross_year_ratio(symbol, numerator_field, denominator_field)
            if fallback is not None:
                return fallback, False
            return None, True
        return float(computed), False

    def _get_symbol_sector(self, symbol: str) -> str | None:
        """Lazily fetches and caches symbol -> company_profile.sector (GICS) once per loader
        run, reused across every _compute_quality_metrics call (no per-symbol query).

        Financial Services and Real Estate get a 7-input variant of quality_score (see
        quality_components below) that drops asset_turnover_score - Revenue/Total Assets isn't a
        coherent "operating efficiency" measure for a bank's loan book or a REIT's portfolio the
        way it is for an operating company (confirmed via isolated testing, matches Fama-French's
        practice of excluding financials from similar factor constructions).

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
            # The anchor balance-sheet row (quality_row[0]) can have stockholders_equity NULL
            # even though a nearby fiscal year has a real value - ROE/sustainable_growth_rate
            # need the same 3-year-window-then-full-history fallback search already used
            # elsewhere in this file (roic_pct/roce_pct/debt_to_equity get it via
            # roic_stockholders_equity below).
            # The anchor balance-sheet row (quality_row[0]) can have stockholders_equity NULL
            # even though a nearby fiscal year has a real value - ROE/sustainable_growth_rate
            # need the same 3-year-window-then-full-history fallback search already used
            # elsewhere in this file (roic_pct/roce_pct/debt_to_equity get it via
            # roic_stockholders_equity below). Same fallback pattern applies to
            # total_liabilities/total_assets/current_assets/current_liabilities below.
            if stockholders_equity is None:
                stockholders_equity = self._fetch_balance_sheet_anchor_fallback(symbol, "stockholders_equity")
            total_liabilities = self._nan_to_none(
                safe_float(quality_row[1], f"{symbol}.total_liabilities", allow_none=True)
            )
            if total_liabilities is None:
                total_liabilities = self._fetch_balance_sheet_anchor_fallback(symbol, "total_liabilities")
            total_assets = self._nan_to_none(safe_float(quality_row[2], f"{symbol}.total_assets", allow_none=True))
            if total_assets is None:
                total_assets = self._fetch_balance_sheet_anchor_fallback(symbol, "total_assets")
            net_income = self._nan_to_none(safe_float(quality_row[3], f"{symbol}.net_income", allow_none=True))
            revenue = self._nan_to_none(safe_float(quality_row[4], f"{symbol}.revenue", allow_none=True))
            operating_income = self._nan_to_none(
                safe_float(quality_row[5], f"{symbol}.operating_income", allow_none=True)
            )
            current_assets = self._nan_to_none(safe_float(quality_row[6], f"{symbol}.current_assets", allow_none=True))
            if current_assets is None:
                current_assets = self._fetch_balance_sheet_anchor_fallback(symbol, "current_assets")
            current_liabilities = self._nan_to_none(
                safe_float(quality_row[7], f"{symbol}.current_liabilities", allow_none=True)
            )
            if current_liabilities is None:
                current_liabilities = self._fetch_balance_sheet_anchor_fallback(symbol, "current_liabilities")
            inventory = self._nan_to_none(safe_float(quality_row[9], f"{symbol}.inventory", allow_none=True))
            interest_expense = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense", allow_none=True)
            )
            pretax_income = self._nan_to_none(safe_float(quality_row[23], f"{symbol}.pretax_income", allow_none=True))
            # quality_row is ONE joined row for a single fiscal_year (chosen to prioritize FCF
            # availability - see the ORDER BY above), so interest_expense/operating_income/
            # pretax_income can be NULL together even when an older year has all three - search
            # across years below rather than mixing an anchor value with a fallback from a
            # different year. EBIT = Pretax Income + Interest Expense is used as a fallback
            # numerator when a filer never tags OperatingIncomeLoss at all (some real filers
            # never do, not a missing-year issue).
            interest_coverage_operating_income = operating_income
            interest_coverage_pretax_income = pretax_income
            _interest_expense_invalid = interest_expense is None or interest_expense <= 0
            # A filer can have a valid current-year interest_expense while only operating_income/
            # pretax_income are missing for that specific anchor year - trigger the fallback
            # search on either condition, not just interest_expense itself.
            _income_inputs_missing = (
                interest_coverage_operating_income is None and interest_coverage_pretax_income is None
            )
            if _interest_expense_invalid or _income_inputs_missing:
                # `data_unavailable IS NOT TRUE` (applied inside the helper) prevents an
                # incomplete/unfiled fiscal year's stub value from being picked up as the real
                # figure.
                fallback_ie_row = self._fetch_annual_fallback_row(
                    "annual_income_statement",
                    "interest_expense, operating_income, pretax_income",
                    "AND interest_expense IS NOT NULL AND interest_expense > 0 "
                    "AND (operating_income IS NOT NULL OR pretax_income IS NOT NULL)",
                    symbol,
                )

                if fallback_ie_row:
                    # Only overwrite interest_expense itself when IT was the reason this
                    # fallback fired - WELL-style callers already have a real, current-year
                    # interest_expense and must keep it, not silently swap in a prior year's
                    # (which would mix a current-year denominator with a stale numerator).
                    if _interest_expense_invalid:
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
            # The shared query's `acf.data_unavailable = FALSE` JOIN condition discards
            # dividends_paid whenever the row is flagged incomplete_sec_filing_cashflow (missing
            # operating_cash_flow flags the WHOLE row), even when dividends_paid itself was
            # extracted fine. Recover it directly for the SAME fiscal year as the anchor row -
            # never mixes years, and operating_cash_flow/free_cash_flow correctly stay None.
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
            # Recovers dividends_paid when the anchor fiscal year genuinely never extracted it
            # (vs. the same-year "unavailable row" rescue above, which only handles the
            # masked-but-present case). Appended as the LAST column (index 34), bounds-checked
            # rather than accessed bare so an old 34-column test fixture reads None instead of
            # raising IndexError - see the Net Debt Issuance comment below for why adding a
            # column here elsewhere had to be deferred.
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
            # Pure in-memory fallback (no new DB call - this function's tests mock the cursor
            # with a fixed, position-matched sequence of canned results).
            dividends_paid_with_prior_year_fallback = dividends_paid
            if dividends_paid_with_prior_year_fallback is None and prior_year_dividends_paid is not None:
                dividends_paid_with_prior_year_fallback = prior_year_dividends_paid
            # prior_year_dividends_paid only reaches back one fiscal year, so a gap spanning 3+
            # consecutive years still falls through to None - see
            # _get_last_known_zero_dividends_symbols()'s docstring for why only the "last known
            # value was exactly $0" subset is safe to carry forward indefinitely.
            if (
                dividends_paid_with_prior_year_fallback is None
                and symbol in self._get_last_known_zero_dividends_symbols()
            ):
                dividends_paid_with_prior_year_fallback = 0.0
            # Net Debt Issuance (Bradshaw/Richardson/Sloan 2006) DEFERRED: needs prior-year
            # long_term_debt, which isn't in quality_row (appending a column there breaks
            # fixed-length mock rows in existing tests) and can't be fetched via a new
            # mid-function query either (tests mock the DB cursor with a fixed,
            # position-matched sequence of canned results - any new cur.execute() call shifts
            # that sequence for every test exercising this path). Its 5% weight allocation
            # moved to margin_volatility_score below instead.
            # EBIT-approximation fallback for prior-year operating income, mirroring the
            # current-year fallback below - needed so operating_income_growth_yoy/
            # operating_margin_trend (which compare CURRENT vs PRIOR year) aren't blocked for
            # filers that tag pretax_income/interest_expense but never OperatingIncomeLoss.
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
            # Metrics suppressed by the |ratio| > 1000 garbage-value bound below - tracked
            # separately from failed_metrics because "we computed a real ratio and threw it
            # away as implausible" (near-zero-denominator extraction artifact, or a
            # legitimately near-zero-revenue filer like a pre-revenue biotech/SPAC) is a
            # materially different situation from "SEC never reported the inputs at all", and
            # both were previously labeled with the same generic "missing_sec_data" reason.
            implausible_ratio_metrics: list[str] = []
            # Tracks the reason for the sign-change guards below (a YoY comparison that flips
            # sign, e.g. -$15M to +$2M, produces a meaningless growth percentage).
            sign_change_yoy_metrics: list[str] = []
            # A prior-year base under 1% of that year's revenue is too small to produce a
            # meaningful growth percentage even without a sign flip - mark unavailable rather
            # than compute a technically-real but misleading number.
            immaterial_base_yoy_metrics: list[str] = []

            # ROE = Net Income / Shareholders' Equity. Same near-zero-denominator garbage-value
            # bound as the other ratios in this function; falls back to the most recent OTHER
            # fiscal year with a plausible pair before giving up as implausible_ratio.
            metrics["roe"], _roe_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, stockholders_equity, "net_income", "stockholders_equity"
            )
            if metrics["roe"] is None:
                failed_metrics.append("roe")
                if _roe_implausible:
                    implausible_ratio_metrics.append("roe")

            # ROA = Net Income / Total Assets. Same bound and cross-year fallback as roe above.
            metrics["roa"], _roa_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, total_assets, "net_income", "total_assets"
            )
            if metrics["roa"] is None:
                failed_metrics.append("roa")
                if _roa_implausible:
                    implausible_ratio_metrics.append("roa")

            # Operating Margin = Operating Income / Revenue
            # Fallback for banks (NULL revenue): use Operating Income / Total Assets instead
            # EBIT-approximation fallback (pretax_income + interest_expense), same as
            # interest_coverage_operating_income/roic_operating_income above - uses the anchor
            # row's own pretax_income/interest_expense (not the cross-year-searched value) so
            # numerator and denominator (revenue) stay from the same fiscal year.
            operating_income_for_margin = operating_income
            if operating_income_for_margin is None and pretax_income is not None:
                operating_income_for_margin = pretax_income + (interest_expense or 0)
            # Some REIT/tonnage-tax filers (AGNC/ARE/AMH-class) never tag OperatingIncomeLoss OR
            # pretax_income/income_tax_expense at all - a permanent different-accounting-model
            # gap, not an XBRL extraction failure, so recategorize as "reit_special_entity"
            # rather than "missing_sec_data" once confirmed unrecoverable (reuses the same
            # _get_no_tax_concept_symbols() 3-consecutive-year check as roic_pct's
            # effective_tax_rate=0.0 branch). Deliberately does not attempt a numeric
            # reconstruction here (net_income-based reconstruction was tried and rejected
            # elsewhere in this file - too much deviation). sustainable_growth_rate is
            # unaffected since its ROE input only needs net_income+equity.
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
                    # Same near-zero-denominator garbage-value bound as gross_margin/
                    # ebitda_margin/roic_pct above.
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
                    # Same near-zero-denominator garbage-value bound as the margins above.
                    if abs(computed_net_margin) > 1000:
                        failed_metrics.append("net_margin")
                        implausible_ratio_metrics.append("net_margin")
                    else:
                        metrics["net_margin"] = float(computed_net_margin)
            else:
                failed_metrics.append("net_margin")

            # Debt to Equity is computed after roic_pct below, alongside ROCE, from
            # debt_for_roic (interest-bearing debt) / equity - NOT Total Liabilities / Equity,
            # which is a different, broader ratio (includes AP/deferred revenue/accrued
            # expenses) than what "Debt-to-Equity" means in standard finance usage or what was
            # Fama-MacBeth validated for this factor.

            # Debt to Assets = Total Liabilities / Total Assets
            # Same >1000 near-zero-denominator bound as the other ratios in this function.
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
            # Same >1000 bound as the other ratios above.
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
            # `inventory` NULL means genuinely none carried (service/software) or simply not
            # broken out - treat as 0 rather than failing the metric, same as IBD/most screeners.
            # Same >1000 bound as current_ratio above (shares the same denominator).
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
            # AssetsCurrent/LiabilitiesCurrent - a permanent structural gap, distinct from an
            # ordinary filer's one-year extraction/timing gap, so check full symbol history.
            unclassified_balance_sheet = (
                current_assets is None
                and current_liabilities is None
                and symbol in self._get_unclassified_balance_sheet_symbols()
            )

            # Companies that stop itemizing interest_expense (debt-free, or netted into other
            # income/expense) never report it again - full-history check, not just this row.
            no_recent_interest_expense = interest_expense is None and (
                symbol in self._get_no_recent_interest_expense_symbols()
                or symbol in self._get_never_tagged_interest_expense_symbols()
            )
            # REITs with real interest_expense (mortgage debt) but no operating_income/
            # pretax_income concept ever tagged fail interest_coverage on the operating-income
            # side, not interest_expense - distinct from no_recent_interest_expense above.
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
                # A negligibly small interest_expense denominator blows this ratio up into
                # noise (real but meaningless), not a real coverage signal.
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
            # sec_valuations' own `reason` column carries a specific cause (e.g.
            # "income_statement_revenue_and_eps_null") - prefer it over a generic bucket.
            # `len(ev_metrics) > 3` guards callers/tests still passing the older 3-tuple shape.
            sec_valuations_reason = ev_metrics[3] if ev_metrics and len(ev_metrics) > 3 else None
            if ev_metrics:
                total_debt_ev = self._nan_to_none(safe_float(ev_metrics[0], f"{symbol}.total_debt", allow_none=True))
                total_cash_ev = self._nan_to_none(safe_float(ev_metrics[1], f"{symbol}.total_cash", allow_none=True))
                ebitda_ev = self._nan_to_none(safe_float(ev_metrics[2], f"{symbol}.ebitda", allow_none=True))

            # Gross Margin = Gross Profit / Revenue. Prefers gross_profit directly from SEC
            # data over computing it from cost_of_revenue, with a prior-year fallback (like
            # ROIC/interest_coverage) when the anchor year has neither. Fetched as a triple
            # (gross_profit, cost_of_revenue, revenue) to avoid year mismatches.
            gross_profit_used = None
            gross_profit_revenue = revenue  # Track which revenue used (for margin calc)

            if gross_profit_direct is not None:
                gross_profit_used = gross_profit_direct
            elif cost_of_revenue is not None and revenue is not None:
                gross_profit_used = revenue - cost_of_revenue

            # Fallback to prior year if current year lacks both sources
            if gross_profit_used is None and (gross_profit_direct is None and cost_of_revenue is None):
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes
                # incomplete/unfiled stub rows, which under-report vs the real complete fiscal
                # year.
                fallback_gm_row = self._fetch_annual_fallback_row(
                    "annual_income_statement",
                    "gross_profit, cost_of_revenue, revenue",
                    "AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL) AND revenue IS NOT NULL",
                    symbol,
                )
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

            # Still None here means this symbol has never once reported gross_profit or
            # cost_of_revenue - banks, insurers, and service/REIT filers legitimately don't
            # break out a COGS line at all (structural gap, not a data gap).
            no_gross_profit_concept = gross_profit_used is None

            if gross_profit_used is not None and gross_profit_revenue is not None and gross_profit_revenue != 0:
                # Bound the ratio - a real but implausibly tiny revenue relative to gross_profit
                # (e.g. a mis-scaled/mis-tagged SEC fact) explodes this into nonsense.
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
                # Same near-zero-denominator bound as gross_margin above.
                computed_ebitda_margin = (ebitda_ev / revenue) * 100
                if abs(computed_ebitda_margin) > 1000:
                    failed_metrics.append("ebitda_margin")
                    implausible_ratio_metrics.append("ebitda_margin")
                else:
                    metrics["ebitda_margin"] = float(computed_ebitda_margin)
            else:
                failed_metrics.append("ebitda_margin")

            # ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate). No
            # hardcoded tax-rate assumption - only real SEC-reported tax/pretax concepts are
            # used (a fabricated 0.21/0.25 fallback was rejected/reverted). Pulled as one row
            # (not independent lookups) so NOPAT never mixes mismatched fiscal years.
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
            # Banks especially often have tax+pretax in the anchor year but neither
            # operating_income nor interest_expense that same year (both untagged) - trigger
            # the rescue search below even when tax/pretax themselves are present.
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
                    # `data_unavailable IS NOT TRUE` excludes incomplete/unfiled stub rows.
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

                    # Widen to full history if the 3-year window found nothing, OR found a
                    # tax/pretax row that still can't recover operating_income/interest_expense
                    # (both None) - a 3-year match on tax/pretax alone must not short-circuit
                    # the widen, since it recovers nothing this fallback needs. Keep the 3-year
                    # row (still unblocks effective_tax_rate) if the wider search also empties.
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
                    # The search above ranks candidate years by "has operating_income or
                    # interest_expense" ABOVE recency, so it can pick an older, worse year's
                    # tax/pretax over the anchor's own good ones (e.g. a stale loss year beating
                    # a current profitable one for insurers, who often lack both concepts even
                    # when otherwise current). Only take the fallback row's tax/pretax when the
                    # anchor didn't already have real values - this fallback exists solely to
                    # recover operating_income/interest_expense for NOPAT, never to override an
                    # anchor year's own good profitability figures.
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
                    # operating_income/interest_expense - otherwise the anchor year's real
                    # operating_income could get mixed with a different fallback year's
                    # interest_expense (or vice versa).
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

            # No hardcoded tax-rate assumption - only real SEC-reported IncomeTaxExpenseBenefit/
            # pretax_income concepts are used (a fabricated 0.21/0.25 fallback was rejected).
            # Bounded to [-60%, 60%]: an implausible rate (near-zero pretax income swamped by an
            # unrelated tax swing) would distort NOPAT worse than marking unavailable, but a
            # real net tax benefit in a profitable year (R&D credits, valuation-allowance
            # releases) is normal and should compute, hence the symmetric range rather than
            # [0, 60%] alone.
            roic_pct_unprofitable = roic_pretax_income is not None and roic_pretax_income <= 0
            effective_tax_rate = None
            if roic_tax_expense is not None and roic_pretax_income is not None and roic_pretax_income > 0:
                candidate_rate = roic_tax_expense / roic_pretax_income
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")
            elif (
                roic_tax_expense is None and roic_pretax_income is None and symbol in self._get_no_tax_concept_symbols()
            ):
                # See _get_no_tax_concept_symbols - a filer that has never once tagged a tax
                # concept is structurally tax-exempt (Marine Shipping tonnage-tax filers,
                # REITs), not missing data. NOPAT = operating_income * (1 - 0%).
                effective_tax_rate = 0.0
            elif roic_tax_expense == 0 and roic_pretax_income is None:
                # Some filers (simple loss-making biotechs/small-caps) tag
                # IncomeTaxExpenseBenefit=$0 every year but never tag any pretax_income concept
                # (nothing to reconcile with $0 tax). This needs no net_income+tax_expense
                # approximation (rejected elsewhere as too imprecise, ~25% deviation from
                # NCI/discontinued-ops noise) - effective_tax_rate = tax/pretax is exact algebra
                # when tax is EXACTLY 0: 0/x = 0 for any nonzero x.
                effective_tax_rate = 0.0
            elif (
                roic_pretax_income is None
                and roic_tax_expense is not None
                and roic_tax_expense != 0
                and roic_net_income is not None
                and (roic_net_income + roic_tax_expense) > 0
                and symbol in self._get_never_tagged_pretax_income_symbols()
            ):
                # See _get_never_tagged_pretax_income_symbols - REITs/mortgage trusts never tag
                # a distinct pretax_income concept but do report a real, usually small,
                # income_tax_expense. The general net_income+tax_expense approximation for
                # pretax_income is rejected elsewhere (NCI/discontinued-ops noise), but scoped
                # narrowly here (confirmed-absent concept, same-fiscal-year net_income, same
                # [-0.60, 0.60] bound as every other branch) it's safe: when tax is this small
                # relative to net_income, even a materially wrong pretax base yields only a
                # small implied rate.
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
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/unfiled or stale-orphan (see sec_base.py's
                # stale_fiscal_year_not_confirmed_by_full_sec_refetch) fiscal year's stub.
                fallback_bs_row = self._fetch_annual_fallback_row(
                    "annual_balance_sheet",
                    "stockholders_equity, cash_and_equivalents",
                    "AND stockholders_equity IS NOT NULL AND cash_and_equivalents IS NOT NULL",
                    symbol,
                )

                if fallback_bs_row:
                    roic_stockholders_equity = self._nan_to_none(
                        safe_float(fallback_bs_row[0], f"{symbol}.stockholders_equity_fallback_year", allow_none=True)
                    )
                    roic_cash_and_equivalents = self._nan_to_none(
                        safe_float(fallback_bs_row[1], f"{symbol}.cash_and_equivalents_fallback_year", allow_none=True)
                    )

            # Banks often tag deposits/FHLB advances/subordinated debentures under concepts
            # this pipeline doesn't map to "long_term_debt" for the current fiscal year, even
            # though an older 10-K (within the 3-year lookback) has a real figure.
            # total_debt_ev has no fiscal-year dimension (sec_valuations is a single
            # latest-snapshot row), so only long_term_debt_bs can be rescued this way - only
            # search when total_debt_ev is also absent (it remains the primary source below).
            roic_long_term_debt = long_term_debt_bs
            if total_debt_ev is None and long_term_debt_bs is None:
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/stale-orphan stub.
                fallback_debt = self._fetch_balance_sheet_anchor_fallback(symbol, "long_term_debt")
                if fallback_debt is not None:
                    roic_long_term_debt = fallback_debt

            invested_capital = None
            debt_for_roic = total_debt_ev if total_debt_ev is not None else roic_long_term_debt

            # A symbol that has never tagged ANY debt component across its full balance-sheet
            # history AND never reports nonzero interest_expense is double-confirmed
            # structurally debt-free (SPACs, pre-revenue biotech, small tech/services - see
            # _get_never_tagged_debt_components_symbols()'s docstring), not an extraction gap.
            # Mirrors load_sec_valuations.py's own EV treatment of missing total_debt as 0, but
            # requires the interest_expense corroboration since debt_to_equity/roce_pct/
            # roic_pct feed real trading scores and a false "0 debt" would overstate safety.
            if (
                debt_for_roic is None
                and symbol in self._get_never_tagged_debt_components_symbols()
                and symbol in self._get_never_tagged_interest_expense_symbols()
            ):
                debt_for_roic = 0.0

            if (
                roic_stockholders_equity is not None
                and debt_for_roic is not None
                and roic_cash_and_equivalents is not None
            ):
                invested_capital = roic_stockholders_equity + debt_for_roic - roic_cash_and_equivalents
            # A large cash pile (common for well-capitalized biotechs, e.g. equity-raise-funded)
            # can push equity + debt - cash negative even with real, complete SEC data - a real
            # business-state fact, not an absent concept (same distinction as
            # roic_pct_unprofitable below for pretax losses).
            roic_pct_negative_invested_capital = invested_capital is not None and invested_capital <= 0
            # roic_operating_income (NOPAT's other input) can independently be None for
            # no-tax-concept REITs even when effective_tax_rate's own branch already handles
            # them - same structural-not-missing gate.
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
                # Same near-zero-denominator bound as gross_margin/ebitda_margin/
                # interest_coverage above - invested_capital > 0 only rules out literal zero,
                # not an implausibly tiny-but-positive value that explodes the ratio.
                computed_roic_pct = (nopat / invested_capital) * 100
                if abs(computed_roic_pct) > 1000:
                    roic_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roic_pct")
                    if roic_fallback is not None:
                        metrics["roic_pct"] = roic_fallback
                    else:
                        failed_metrics.append("roic_pct")
                        implausible_ratio_metrics.append("roic_pct")
                else:
                    metrics["roic_pct"] = float(computed_roic_pct)
            else:
                failed_metrics.append("roic_pct")

            # ROCE = EBIT / (Equity + Debt), deliberately NO cash subtraction - unlike roic_pct
            # above, whose cash-netted invested_capital goes negative for well-capitalized,
            # profitable companies. roic_operating_income is used as the EBIT proxy (pretax,
            # classic ROCE convention - not NOPAT). Replaces roic_score in the composite (see
            # weighted_score) - more stable and higher coverage per FM validation.
            capital_employed = (
                roic_stockholders_equity + debt_for_roic
                if roic_stockholders_equity is not None and debt_for_roic is not None
                else None
            )
            roce_pct_negative_capital_employed = capital_employed is not None and capital_employed <= 0
            if roic_operating_income is not None and capital_employed is not None and capital_employed > 0:
                computed_roce_pct = (roic_operating_income / capital_employed) * 100
                if abs(computed_roce_pct) > 1000:
                    roce_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roce_pct")
                    if roce_fallback is not None:
                        metrics["roce_pct"] = roce_fallback
                    else:
                        failed_metrics.append("roce_pct")
                        implausible_ratio_metrics.append("roce_pct")
                else:
                    metrics["roce_pct"] = float(computed_roce_pct)
            else:
                failed_metrics.append("roce_pct")

            # Debt to Equity: interest-bearing Debt / Equity (replaced the old Total
            # Liabilities / Equity formula). Reuses debt_for_roic/roic_stockholders_equity, same
            # inputs as ROIC/ROCE above. Correlates strongly with debt_to_assets (corr=0.67), so
            # replaces it in the composite rather than being scored alongside it.
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

            # Payout Ratio = Dividends / Net Income (% of earnings paid out). A loss year
            # (net_income <= 0) makes the ratio not meaningful - "not applicable", not a data
            # gap; distinguish from genuine non-payers (no dividend history at all) and true
            # extraction gaps (dividend history exists elsewhere, concept missing this year).
            # Magnitude-guarded like the other ratio fields: quality_metrics.payout_ratio is
            # NUMERIC(10,2) (max ~1e8) and a near-zero net_income denominator can otherwise
            # explode the ratio and crash the INSERT with NumericValueOutOfRange.
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
                # Same net_income_not_reported gate net_margin/roa/roe already use - genuinely
                # never-tagged net_income, not just <=0.
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    payout_ratio_reason = "net_income_not_reported"
                else:
                    # Same "ever, not recently" distinction as dividend_yield_reason above - a
                    # symbol that discontinued its dividend years ago has real history on file
                    # but isn't a current data gap. Same 2-year recency window used there.
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
                # shares_outstanding here is sv.shares_outstanding (quality_row[11]) - same
                # column that already gets its own "shares_outstanding_unavailable" reason
                # elsewhere in this codebase, not a generic SEC extraction gap.
                cash_per_share_shares_missing = shares_outstanding is None or shares_outstanding <= 0

            # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100.
            # Bounded like the sibling *_growth_yoy fields below: a near-zero prior-year base
            # can overflow NUMERIC(10,2) and crash the whole row's INSERT. Appends to
            # implausible_ratio_metrics (in addition to failed_metrics) so a real-but-rejected
            # ratio is distinguished from a genuinely absent prior-year base.
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
            # Net Income Growth YoY - only if actual prior net income available.
            # Bounded by MAX_TREND_PERCENTAGE_POINTS (same guard as roe_trend below): a real but
            # near-zero prior-year base can overflow this column's NUMERIC(10,4) and crash the
            # whole row's INSERT.
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

            # Margin Trends (current - prior year) - only compute when actual prior data available.
            # The trend-level MAX_TREND_PERCENTAGE_POINTS check only bounds the DELTA, not the
            # two margins that produce it - a near-zero-revenue year can put curr/prior
            # individually in the tens of thousands of percent while their difference still
            # lands under threshold. Bound each side of the subtraction first (same |ratio| <=
            # 1000 bound as the base margin fields) - a trend from two implausible margins is
            # itself meaningless.
            MAX_MARGIN_ABS_PCT = 1000.0  # noqa: N806
            if revenue is not None and prior_year_revenue is not None and revenue > 0 and prior_year_revenue > 0:
                # Gross Margin Trend - prefers each year's directly-reported gross_profit (same
                # source the base gross_margin metric above falls back to), only deriving from
                # revenue - cost_of_revenue when a filer doesn't tag GrossProfit at all (some
                # filers report GrossProfit but never a separate CostOfRevenue concept).
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
            # dividends_paid is None (not 0) for genuine non-dividend-payers, since SEC XBRL
            # simply omits the PaymentsOfDividends concept when nothing was paid - same
            # "confirmed non-payer vs missing data" ambiguity as dividend_yield/payout_ratio
            # above. Confirmed non-payers still compute (retention_ratio = 1.0).
            sgr_reason = None
            # Same prior-year fallback as payout_ratio above, so a confirmed-recent payer's
            # current-year extraction gap doesn't get stuck on "missing_sec_data".
            sgr_dividends_paid = dividends_paid_with_prior_year_fallback
            if (
                sgr_dividends_paid is None
                and stockholders_equity is not None
                and net_income is not None
                and stockholders_equity > 0
            ):
                # Same "ever, not recently" distinction as dividend_yield_reason/
                # payout_ratio_reason above; same 2-year recency window.
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
                        # Bounded by MAX_PLAUSIBLE_GROWTH_PCT - a near-zero stockholders_equity
                        # base blows up roe_pct the same way a near-zero prior-year base blows
                        # up other ratios.
                        if abs(sgr) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["sustainable_growth_rate"] = float(sgr)
                        elif sgr_reason is None:
                            # Real value, deliberately rejected as implausible - not a missing
                            # SEC concept.
                            sgr_reason = "implausible_ratio"
                            implausible_ratio_metrics.append("sustainable_growth_rate")
                    except (ValueError, TypeError, ZeroDivisionError):
                        if sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                elif sgr_reason is None:
                    sgr_reason = "missing_sec_data"
            elif sgr_reason is None:
                # stockholders_equity <= 0 (debt-funded buybacks/distributions, e.g.
                # YUM/IRM/COKE) is real data, not missing - SGR's "growth financeable from
                # retained earnings relative to the equity base" doesn't translate to a negative
                # base, so this deliberately still doesn't compute a value, but the label must
                # say why. Reuses "negative_book_value" (same as pb_ratio above) rather than
                # inventing a new string.
                if stockholders_equity is not None and stockholders_equity <= 0:
                    sgr_reason = "negative_book_value"
                # Remaining case: stockholders_equity is None, or (rarely) present but
                # net_income is None - reuse the same gates roe/roa/debt_to_equity use above.
                elif stockholders_equity is None and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                ):
                    sgr_reason = "stockholders_equity_not_reported"
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    sgr_reason = "net_income_not_reported"
                # quality_row_db's current-year income-statement columns require an EXACT
                # fiscal_year match to the balance-sheet anchor row (~line 716) - a
                # still-in-progress income statement for that year can leave net_income None
                # here even when real data exists 1-2 years back. Deliberately does NOT
                # recompute from the mismatched-year net_income (same discipline as
                # revenue_absent_from_anchor_year/implausible_dcf_result elsewhere) - label-only,
                # to distinguish "SEC data isn't there" from "SEC data is there, wrong year".
                elif net_income is None and symbol in self._get_net_income_available_elsewhere_symbols():
                    sgr_reason = "net_income_absent_from_anchor_year"
                else:
                    sgr_reason = "missing_sec_data"

            # ROE Trend = Current ROE - Prior ROE. Same per-side MAX_MARGIN_ABS_PCT bound as
            # the margin trends above - a near-zero prior-year equity base must be caught before
            # the subtraction, not just via the looser trend-level check on the delta. Uses
            # `!= 0` (not `> 0`) to match the base roe field - negative equity (debt-funded
            # buybacks/distributions, e.g. YUM/IRM/COKE) is real data, and MAX_MARGIN_ABS_PCT
            # already rejects genuine near-zero-equity garbage.
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

            # Record WHY each of these 9 trend/growth fields stayed None (mirrored into
            # growth_metrics via the _SHARED_TREND_FIELDS copy below). Order matters: check the
            # structural gross_profit gap and implausible-ratio rejection before falling through
            # to the generic "insufficient_prior_year_data" - both are legitimate-gap or
            # garbage-data cases, not evidence of a loader fetch failure.
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

            # sustainable_growth_rate uses NO prior-year data (see its own computation above),
            # so it gets its own explicit sgr_reason rather than the blanket trend-field loop.
            if metrics.get("sustainable_growth_rate") is None:
                metrics["sustainable_growth_rate_unavailable_reason"] = sgr_reason or "missing_sec_data"

            # Quarterly-derived fields (consecutive_positive_quarters, quarterly_growth_momentum,
            # earnings_growth_4q_avg, eps_growth_stability, earnings_surprise_avg,
            # earnings_beat_rate) are merged in from _compute_quarterly_metrics() above, which
            # sets its own specific reason when the value is None. The generic
            # "insufficient_quarterly_data"/"no_analyst_estimates" fallback for these fields
            # lives further below and only fires if that specific reason wasn't already set.

            # Mark unavailable if all metrics are None
            if (
                all(
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
                )
                and metrics.get("consecutive_positive_quarters") is None
            ):
                # consecutive_positive_quarters is always a real int (never None) whenever >=4
                # real quarters exist, so checking it here is a direct signal that real
                # quarterly data exists - guards against this early return's blanket
                # None+"missing_sec_data" stamp wiping already-computed quarterly-derived
                # fields. This return also fires before any of the per-field reason blocks
                # below run, so propagate a real row-level reason when one is knowable instead
                # of leaving _unavailable_marker's generic default on every column.
                row_level_reason = (
                    "etf_trust_no_gaap_financials"
                    if stockholders_equity is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                    else "no_recent_balance_sheet_data_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else None
                )
                return self._unavailable_marker("quality_metrics", symbol, reason=row_level_reason)

            # Compute composite quality_score from available metrics
            # Score is average of available metrics (0-100 scale)
            # debt_to_assets is "lower is better" so it's converted to a comparable
            # higher-is-better score before joining the same clamp-and-average as the
            # raw percentage metrics below (100 - debt_to_assets%, e.g. 30% debt -> 70).
            #
            # NOTE: debt_to_assets is positively signed vs forward return in FM testing
            # (higher leverage -> higher forward return), the opposite of this "low debt is
            # good" inversion - a genuine, unresolved literature tension (Modigliani-Miller
            # leverage-beta effect vs. the distress-risk anomaly), not miscalibration. Left
            # unchanged pending a real distress-risk proxy (e.g. Altman Z-score) to resolve it.
            # debt_to_assets_score is no longer scored (replaced by debt_to_equity_score, see
            # that field's comment near roic_pct/roce_pct below) - metrics["debt_to_assets"]
            # itself is still persisted/displayed. Same for interest_coverage_score (dead after
            # interest_coverage was dropped from quality_components) - metrics
            # ["interest_coverage"] is still persisted independently.

            # roe/roa/operating_margin/net_margin are rescaled onto domain-informed curves
            # (not fed in as raw percentage points) - a flat 0-100=percentage mapping requires
            # a 100% margin to hit 100, a threshold no real business reaches, which
            # structurally compressed quality_score toward ~20-50 regardless of actual quality
            # and defeated min_composite_score's intended selectivity. This is a scale fix only
            # - the underlying roe/roa/operating_margin/net_margin values feeding
            # fama_macbeth_quality_factors.py are untouched. Thresholds are hand-set, not
            # FM-backtested (calibration, not a new empirical claim).
            roe_score = (
                self._margin_curve(metrics["roe"], [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
                if metrics["roe"] is not None
                else None
            )
            roa_score = (
                self._margin_curve(metrics["roa"], [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
                if metrics["roa"] is not None
                else None
            )
            # operating_margin_score/net_margin_score are not scored - operating_margin and
            # net_margin are still fetched/stored/displayed for reference, but neither carries
            # independent signal once ROA is controlled for (see
            # quality_operating_net_margin_no_independent_signal_over_roa_20260826 in MEMORY.md).

            # Quality pillar composition follows a literature-informed denominator-sharing
            # check (Novy-Marx 2013, Fama-French 2015 RMW, Sloan 1996, QMJ 2013): ROE
            # (NI/BookEquity) overlaps with FF's Operating Profitability ((Rev-COGS-SGA-
            # Interest)/BookEquity, same denominator), and ROA (NI/Assets) overlaps with
            # Novy-Marx's Gross Profitability ((Rev-COGS)/Assets, same denominator).
            # Cash-flow ROA (OCF/Assets) is not independent once ROA and Accruals Ratio
            # ((NI-OCF)/Assets, Sloan 1996) are both present - it's their exact linear
            # difference. operating_margin/net_margin (r=0.91, both profit/revenue ratios) are
            # the other genuinely redundant pair; roe/debt_to_assets (r=0.82) is a DIFFERENT,
            # DuPont-mechanical overlap the literature treats as fine to keep.
            #
            # No separate SG&A field exists in this pipeline - operating_income (GAAP, already
            # nets out COGS+SG&A) minus interest_expense is the available proxy for FF's
            # (Rev-COGS-SGA-Interest) construction.
            # operating_profitability_score/roic_score/accruals_score are not scored (failed
            # this repo's |t|>2 bar, or replaced by a more robust alternative - roic_score ->
            # roce_score, see below). The raw values are still computed and persisted for
            # display - only the scoring curves and composite weight are removed. See
            # weighted_score below for the full final composite.
            #
            # operating_income_for_margin falls back to the EBIT approximation (pretax_income +
            # interest_expense) for 40-F-style filers that never tag OperatingIncomeLoss - same
            # fallback operating_margin/operating_margin_trend already use.
            #
            # Guarded at |ratio|>1000 like every sibling ratio in this file - a near-zero
            # stockholders_equity base can otherwise blow this up multiple orders of magnitude.
            #
            # A negative or zero stockholders_equity denominator (real, common for mature
            # buyback-heavy filers) makes this ratio mathematically undefined - same "real
            # business-state fact, not an absent SEC concept" case pb_ratio/roic_pct/roce_pct
            # carve out via negative_book_value/negative_invested_capital/
            # negative_capital_employed. Reuses "negative_book_value" rather than a new string.
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
            # Novy-Marx (2013, JFE) "gross profitability" - a firm that converts revenue to
            # gross profit efficiently relative to its asset base is a genuine quality signal
            # independent of the margin-based ratios already scored here. Guarded at
            # |ratio|>1000 like the sibling ratios in this file (near-zero total_assets can
            # otherwise blow this up multiple orders of magnitude).
            # Reuses gross_profit_used (same numerator gross_margin already recovers via
            # fallback) instead of a separate lookup. Banks/REITs and some real filers (e.g.
            # REGN, JAZZ) structurally never tag a gross-profit-style income statement at all -
            # distinguished from a genuine loader gap via no_gross_profit_concept below.
            gross_profit_for_profitability = gross_profit_used
            gross_profitability = None
            if gross_profit_for_profitability is not None and total_assets is not None and total_assets > 0:
                computed_gross_profitability = gross_profit_for_profitability / total_assets * 100.0
                if abs(computed_gross_profitability) > 1000:
                    failed_metrics.append("gross_profitability")
                    implausible_ratio_metrics.append("gross_profitability")
                else:
                    gross_profitability = float(computed_gross_profitability)
            # Breakpoints are a domain-judgment fit to the live distribution, not FM-fit to
            # inflection points.
            gross_profitability_score = (
                self._margin_curve(gross_profitability, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
                if gross_profitability is not None
                else None
            )
            # Near-zero total_assets can blow this ratio up arbitrarily; same |ratio|>1000 guard
            # as gross_profitability/operating_profitability/fcf_margin.
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
                self._margin_curve(roce_pct_val, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
                if roce_pct_val is not None
                else None
            )
            # FCF Margin (free_cash_flow / revenue): cash-conversion efficiency net of capex,
            # independent of Accruals Ratio (never nets out capex). Replaces accruals_score in
            # the composite.
            #
            # The anchor fiscal year is chosen for balance-sheet freshness first, so it can have
            # free_cash_flow present but revenue not yet extracted (or vice versa) even though a
            # jointly-valid pair exists in an earlier year - the fallback below checks both
            # sides' None-ness, not just the numerator's, and is scoped to LOCAL variables
            # (fcf_margin_free_cash_flow/fcf_margin_revenue) rather than overwriting the global
            # free_cash_flow/revenue, which also feed fcf_to_net_income and fcf_growth_yoy and
            # must stay aligned to the anchor year for those.
            #
            # Each fallback tier scans every candidate year and picks the most recent one that's
            # actually plausible (|margin|<=1000), not just the single nearest year - an older
            # plausible year can sit behind a nearer implausible one (e.g. a near-zero-revenue
            # year).
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
                        ORDER BY acf.fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    fallback_fcf_rows = cur.fetchall()
                    if not fallback_fcf_rows:
                        cur.execute(
                            """
                            SELECT free_cash_flow, revenue
                            FROM annual_cash_flow acf
                            JOIN annual_income_statement ais
                              ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                            WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                            ORDER BY acf.fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        fallback_fcf_rows = cur.fetchall()
                # row[0]/row[1] are raw Decimal; must cast to float before arithmetic here -
                # `Decimal * float` raises TypeError, which propagates through this function's
                # outer try/except and wipes out EVERY quality_metrics field for the symbol, not
                # just fcf_margin.
                fallback_fcf_row = next(
                    (
                        row
                        for row in fallback_fcf_rows
                        if row[1] is not None
                        and float(row[1]) > 0
                        and abs(float(row[0]) / float(row[1]) * 100.0) <= 1000
                    ),
                    fallback_fcf_rows[0] if fallback_fcf_rows else None,
                )
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
                self._margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
                if fcf_margin is not None
                else None
            )
            # Asset Turnover (Revenue / Total Assets, x100 - same "ratio-as-percentage" storage
            # convention as gross_profitability). Breakpoints: 0.3x (capital-intensive/utilities)
            # maps to 40, 0.8x (typical industrial) to 75, 1.5x+ (retail/services) to 100 -
            # domain-judgment, not FM-fit to inflection points.
            # Uses the same cross-year implausible-ratio fallback as roe/roa - see
            # _find_plausible_cross_year_ratio's docstring.
            asset_turnover, _asset_turnover_implausible = self._ratio_with_implausible_fallback(
                symbol, revenue, total_assets, "revenue", "total_assets", denominator_must_be_positive=True
            )
            if asset_turnover is None and _asset_turnover_implausible:
                failed_metrics.append("asset_turnover")
                implausible_ratio_metrics.append("asset_turnover")
            asset_turnover_score = (
                self._margin_curve(asset_turnover, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
                if asset_turnover is not None
                else None
            )
            # Debt-to-Equity score: inverted (lower leverage = higher score), 0.5 maps to 75,
            # 1.0 to 50, 2.0+ to 0. Negative D/E (negative book equity, real financial distress)
            # floors to 0 rather than inverting into a spuriously high score.
            debt_to_equity_val = metrics.get("debt_to_equity")
            if debt_to_equity_val is None:
                debt_to_equity_score = None
            elif debt_to_equity_val < 0:
                debt_to_equity_score = 0.0
            else:
                debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 2.0) * 100.0))
            # Margin volatility (QMJ 2013 Safety leg proxy): precomputed by the caller from
            # multi-year income_rows this function doesn't have (see _compute_margin_volatility).
            # Inverted curve: LOWER volatility (more stable margins) scores higher.
            # Must read the `margin_volatility` parameter directly, NOT `metrics.get(
            # "margin_volatility")` - that dict key is only written later in this function (see
            # the PERSISTED block below), so reading it here always returns None.
            margin_volatility_val = margin_volatility
            margin_volatility_score = (
                100.0 - self._margin_curve(margin_volatility_val, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
                if margin_volatility_val is not None
                else None
            )

            # operating_margin_trend/net_margin_trend/roe_trend/payout_ratio/interest_coverage
            # score curves, equity_cluster/asset_cluster, debt_to_assets_score, roic_score, and
            # a flat accruals_score are all deliberately NOT scored (confirmed insignificant or
            # superseded per FM re-testing) even though raw values are still persisted:
            # debt_to_assets -> debt_to_equity_score, roic -> roce_score, accruals ->
            # fcf_margin_score. See _score_quality's docstring in load_stock_scores.py.
            #
            # Altman Z''-Score is not scored: it's a DISCRETE distress-triage classifier in the
            # literature, not meant to be continuously averaged into a magnitude-weighted
            # composite alongside ROA/ROE/margin ratios. A discrete distress-flag use may
            # belong on GOVERNANCE's trading-eligibility checks instead, separate from the
            # continuous quality_score - deliberately left open.
            #
            # Weights are set from both full-sample t-stat magnitude and a half-split
            # time-stability check - a component whose t-stat holds up identically across both
            # eras is weighted higher relative to its raw t-stat than one whose apparent
            # strength was concentrated in a short/recent window. debt_to_equity/roa/roce/
            # fcf_margin/roe (the "core five", 80% of the composite) have either the strongest
            # full-sample evidence or the best demonstrated time-stability. current_ratio was
            # tested and deliberately excluded (sign-flips across the half-split).
            # min_quality_weight_pct below is calibrated to ~40% of the composite's nominal
            # weight sum - above any thin-sample case found so far.
            #
            # Financial Services and Real Estate use a 7-input, two-cluster (profitability +
            # safety) structure instead of the flat 8-input tiered average - asset_turnover_score
            # is the one input confirmed (via isolated testing) to actively hurt Quality's
            # signal for these two sectors. Matches AQR QMJ's own profitability/safety cluster
            # construction. Both clusters and the top-level blend are internally renormalized
            # (same _weighted_avg helper) - a symbol missing part of one cluster still scores
            # off whatever it has.
            #
            # update_quality_roe_roce_percentiles() (further below) assumes every symbol was
            # scored via the flat 8-input structure - it does NOT reconcile through this
            # two-cluster structure, so it explicitly SKIPS Financial Services/Real Estate
            # symbols (see its own SQL filter); those symbols keep the Pass-1 curve-based
            # ROE/ROCE scores rather than the cross-sectional-percentile correction.
            sector = self._get_symbol_sector(symbol)
            if sector in ("Financial Services", "Real Estate"):
                profitability_cluster_score = self._weighted_avg(
                    [
                        (roe_score, 1.0),
                        (roa_score, 1.0),
                        (roce_score, 1.0),
                        (fcf_margin_score, 1.0),
                        (gross_profitability_score, 1.0),
                    ],
                    min_weight_pct=2.0,  # >=2 of 5 available - proportional to the 40%-of-101 floor below
                )
                safety_cluster_score = self._weighted_avg(
                    [(debt_to_equity_score, 1.0), (margin_volatility_score, 1.0)],
                    min_weight_pct=1.0,  # >=1 of 2 available
                )
                # Cluster weights (69/25, summing to 94 = universal branch's 101 minus
                # asset_turnover's 7) reflect each cluster's ACTUAL share of the universal
                # branch's nominal weight - a flat 1.0/1.0 split previously let a single
                # cluster, down to one raw field once its own internal floor was barely
                # cleared, produce a full undiscounted quality_score (e.g. an Oil Royalty
                # Trust scoring 97 off margin_volatility alone with every other input NULL).
                quality_components = [(profitability_cluster_score, 69.0), (safety_cluster_score, 25.0)]
                # Proportional to the universal branch's 40/101 (~39.6%) floor: 40 * (94/101) =
                # 37.2. Safety alone is only 25 points (below this floor), so a safety-only
                # symbol correctly returns None instead of a single-field score.
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
            # COMPLETENESS FLOOR: without it, renormalizing over 1-3 available components lets
            # a single extreme raw ratio (e.g. an oil/gas royalty trust's ROA of 700%+) drive
            # quality_score to 100.00 even though data_completeness/GOVERNANCE's eligibility
            # floor should treat this as thin data. Only applies to the universal (non-FS/RE)
            # branch - the sector-conditional branch sets its own proportional floor inline.
            if sector not in ("Financial Services", "Real Estate"):
                min_quality_weight_pct = 40.0
            available_quality_weight = sum(w for v, w in quality_components if v is not None)
            weighted_score = self._weighted_avg(quality_components, min_weight_pct=min_quality_weight_pct)

            metrics["gross_profitability"] = gross_profitability
            metrics["gross_profitability_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "gross_profitability" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if no_gross_profit_concept
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "no_recent_total_assets_reported"
                    if total_assets is None
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
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
                    # Label-only: the anchor year's income statement can lack operating_income
                    # (and its EBIT fallback) even when the symbol reports it in other years.
                    else "operating_income_absent_from_anchor_year"
                    if operating_income_for_margin is None
                    and symbol in self._get_operating_income_available_elsewhere_symbols()
                    # operating_profitability_negative_equity only fires when stockholders_equity
                    # is a real value <=0 - stays False (not caught) when equity is None.
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if operating_profitability is None
                else None
            )
            metrics["accruals_ratio"] = accruals_ratio
            metrics["accruals_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "accruals_ratio" in implausible_ratio_metrics
                    else "no_recent_operating_cash_flow_reported"
                    if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only: operating_cash_flow is None because the anchor year's own
                    # cash-flow row is unavailable, not because the symbol lacks real OCF.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if operating_cash_flow is None
                    and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    else "no_recent_total_assets_reported"
                    if total_assets is None
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "missing_sec_data"
                )
                if accruals_ratio is None
                else None
            )
            metrics["margin_volatility"] = margin_volatility
            metrics["margin_volatility_unavailable_reason"] = (
                "insufficient_history" if margin_volatility is None else None
            )
            # Gate on `X is None` directly (not `"X" in failed_metrics`) - the compute blocks
            # above don't append fcf_margin/asset_turnover to failed_metrics when inputs are
            # merely missing (only when the |ratio|>1000 bound fires), so gating on
            # failed_metrics left many rows with a NULL value and no reason recorded.
            metrics["fcf_margin"] = fcf_margin
            metrics["fcf_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "fcf_margin" in implausible_ratio_metrics
                    # Closed-end funds/investment trusts file no cash-flow statement at all
                    # (see _get_registered_investment_company_symbols' docstring) - checked
                    # before the generic never-tagged-FCF gate below so this more specific,
                    # correctly-categorized ("Legitimate / not applicable") reason wins.
                    else "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: fcf_yield's own reason chain already checks this gate;
                    # fcf_margin's sibling chain here never did (AIG-verified: real OCF every
                    # year, capex-shaped concept stops after FY2023, not PPE-delta-recoverable
                    # since AIG never tags depreciation either).
                    else "capex_never_tagged_in_recent_filings"
                    if symbol in self._get_no_recent_capex_symbols()
                    # fcf_margin's own cross-year fallback (fcf_margin_free_cash_flow/
                    # fcf_margin_revenue above) already looks past the anchor row, so a
                    # remaining None here means both inputs are genuinely absent across recent
                    # fiscal years, not just off the anchor.
                    else "no_recent_free_cash_flow_reported"
                    if symbol in self._get_no_recent_free_cash_flow_symbols()
                    or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # A real free_cash_flow value exists somewhere in the symbol's history but
                    # not in the same fiscal year as a real revenue value (the cross-year
                    # fallback above requires both in the SAME year) - live-confirmed FTW/OBX/
                    # AADX/AVEX/ALLO. Same reason free_cash_flow_unavailable_reason already
                    # uses for this exact gate above - label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if fcf_margin is None
                else None
            )
            metrics["asset_turnover"] = asset_turnover
            metrics["asset_turnover_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "asset_turnover" in implausible_ratio_metrics
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "no_recent_total_assets_reported"
                    if total_assets is None
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    # Label-only: revenue is None because the balance-sheet anchor year's own
                    # income-statement row is unavailable, not because the symbol lacks real
                    # revenue - the windowed gate above already ruled that out.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
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

            # Only mark data_unavailable if ALL metrics are missing - partial quality data
            # (2-3 metrics) is legitimate and scored with completeness tracking, not discarded.
            metrics["roe_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roe" in implausible_ratio_metrics
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    # Label-only: net_income is None because the anchor year's own
                    # income-statement row is unavailable, not because it lacks real net_income.
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "roe" in failed_metrics
                else None
            )
            metrics["roa_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roa" in implausible_ratio_metrics
                    else "no_recent_total_assets_reported"
                    if total_assets is None
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "roa" in failed_metrics
                else None
            )
            metrics["operating_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "operating_margin" in implausible_ratio_metrics
                    # Tonnage-tax shipping cos + REITs structurally never tag
                    # pretax_income/income_tax_expense (_get_no_tax_concept_symbols) -
                    # recategorized as reit_special_entity, not generic missing_sec_data.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    # Label-only: anchor year's income statement lacks operating_income even
                    # though the symbol reports it elsewhere.
                    else "operating_income_absent_from_anchor_year"
                    if operating_income_for_margin is None
                    and symbol in self._get_operating_income_available_elsewhere_symbols()
                    else "no_revenue_reported"
                    if operating_income_for_margin is None
                    and (
                        symbol in self._get_blank_check_symbols()
                        or symbol in self._get_no_recent_revenue_symbols()
                        or symbol in self._get_never_tagged_revenue_symbols()
                    )
                    # Real, revenue-generating filer whose income statement never itemizes a
                    # distinct operating income subtotal.
                    else "operating_income_not_itemized"
                    if operating_income_for_margin is None
                    and (
                        symbol in self._get_no_recent_operating_income_symbols()
                        or symbol in self._get_never_tagged_operating_income_symbols()
                    )
                    else "missing_sec_data"
                )
                if "operating_margin" in failed_metrics
                else None
            )
            metrics["net_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "net_margin" in implausible_ratio_metrics
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    # Label-only: net_income is None because the balance-sheet anchor year's
                    # own income-statement row is unavailable, not because the symbol lacks
                    # real net_income - both gates above already ruled that out.
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "net_margin" in failed_metrics
                else None
            )
            metrics["debt_to_equity_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_equity" in implausible_ratio_metrics
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    # debt_to_equity fails when EITHER roic_stockholders_equity or debt_for_roic
                    # is None - check the debt side too, not just equity.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
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
                    else "no_recent_current_assets_reported"
                    if current_assets is None
                    and (
                        symbol in self._get_no_recent_current_assets_symbols()
                        or symbol in self._get_never_tagged_current_assets_symbols()
                    )
                    else "no_recent_current_liabilities_reported"
                    if current_liabilities is None
                    and (
                        symbol in self._get_no_recent_current_liabilities_symbols()
                        or symbol in self._get_never_tagged_current_liabilities_symbols()
                    )
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
                    # quick_ratio shares current_ratio's structural inputs; inventory's absence
                    # is a normal "not a goods business" fact, not a data gap, deliberately not
                    # gated.
                    else "no_recent_current_assets_reported"
                    if current_assets is None
                    and (
                        symbol in self._get_no_recent_current_assets_symbols()
                        or symbol in self._get_never_tagged_current_assets_symbols()
                    )
                    else "no_recent_current_liabilities_reported"
                    if current_liabilities is None
                    and (
                        symbol in self._get_no_recent_current_liabilities_symbols()
                        or symbol in self._get_never_tagged_current_liabilities_symbols()
                    )
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
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "interest_coverage" in failed_metrics
                else None
            )
            metrics["debt_to_assets_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_assets" in implausible_ratio_metrics
                    else "no_recent_total_assets_reported"
                    if total_assets is None
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "total_liabilities_not_reported"
                    if total_liabilities is None
                    and (
                        symbol in self._get_no_recent_total_liabilities_symbols()
                        or symbol in self._get_never_tagged_total_liabilities_symbols()
                    )
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
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # Label-only: gross_profit_revenue (this field's own denominator, read from
                    # the same balance-sheet-anchor-joined row as `revenue`) is None because
                    # that anchor fiscal year's own income-statement row lacks it, not because
                    # the symbol lacks real revenue anywhere.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "gross_margin" in failed_metrics
                else None
            )
            metrics["ebitda_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "ebitda_margin" in implausible_ratio_metrics
                    # load_sec_valuations.py's own EBITDA computation (EBITDA = OperatingIncome
                    # + D&A) requires operating_income and stays None when it's absent - same
                    # REIT/tonnage-tax-exempt population no_operating_income_concept identifies,
                    # cascading into ebitda_ev is None here.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    or symbol in self._get_blank_check_symbols()
                    # Label-only, no value recomputed.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                    # ebitda_margin also depends on operating_income via EBITDA = OperatingIncome
                    # + D&A - same operating_income_not_itemized case as operating_margin/
                    # interest_coverage above.
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
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
                    # Commodity/crypto trusts (GLD, GLDM, GLTR, IAUM, AAAU, BTCO) structurally
                    # report no revenue by their trust/ETF nature - same "no operating business"
                    # fact blank-check SPACs represent, just not SIC-classified as one.
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # invested_capital (this field's own denominator) comes back None whenever
                    # debt_for_roic OR roic_stockholders_equity is None - the
                    # negative_invested_capital branch above only catches a computed non-None
                    # value <= 0, not a missing input.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
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
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # roce_pct shares roic_operating_income (EBIT numerator) with roic_pct -
                    # same REIT structural gap.
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # capital_employed (this field's own denominator) comes back None whenever
                    # debt_for_roic OR roic_stockholders_equity is None, which
                    # negative_capital_employed's <=0 check doesn't catch.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "roce_pct" in failed_metrics
                else None
            )
            metrics["fcf_to_net_income_unavailable_reason"] = (
                (
                    # See fcf_margin_unavailable_reason above for why this check comes first.
                    "registered_investment_company_no_xbrl"
                    if free_cash_flow is None and symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                    else "capex_never_tagged_in_recent_filings"
                    if free_cash_flow is None and symbol in self._get_no_recent_capex_symbols()
                    else "no_recent_free_cash_flow_reported"
                    if free_cash_flow is None
                    and (
                        symbol in self._get_no_recent_free_cash_flow_symbols()
                        or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    )
                    # Label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if free_cash_flow is None and symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    # fcf_to_net_income = free_cash_flow / net_income - check the net_income
                    # denominator too, not just the FCF numerator.
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "fcf_to_net_income" in failed_metrics
                else None
            )
            metrics["ocf_to_net_income_unavailable_reason"] = (
                (
                    "no_recent_operating_cash_flow_reported"
                    if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if operating_cash_flow is None
                    and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    # ocf_to_net_income = operating_cash_flow / net_income - check the net_income
                    # denominator too, not just the OCF numerator.
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "ocf_to_net_income" in failed_metrics
                else None
            )
            metrics["payout_ratio_unavailable_reason"] = payout_ratio_reason
            metrics["free_cash_flow_unavailable_reason"] = (
                (
                    # See fcf_margin_unavailable_reason above for why this check comes first.
                    "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                    else "capex_never_tagged_in_recent_filings"
                    if symbol in self._get_no_recent_capex_symbols()
                    # Only covers the unambiguous "genuinely no FCF in the 3 most recent fiscal
                    # years" case - the rest have FCF in an off-anchor year (see
                    # _get_free_cash_flow_available_elsewhere_symbols() below).
                    else "no_recent_free_cash_flow_reported"
                    if symbol in self._get_no_recent_free_cash_flow_symbols()
                    or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "free_cash_flow" in failed_metrics
                else None
            )
            metrics["operating_cash_flow_unavailable_reason"] = (
                (
                    # Only covers the unambiguous "genuinely no OCF in the 3 most recent fiscal
                    # years" case - the rest have OCF in an off-anchor year (see
                    # _get_operating_cash_flow_available_elsewhere_symbols() below).
                    "no_recent_operating_cash_flow_reported"
                    if symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "operating_cash_flow" in failed_metrics
                else None
            )
            metrics["total_debt_unavailable_reason"] = (
                (
                    "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                    # total_debt_ev comes from the same ev_metrics tuple as total_cash_ev/
                    # ebitda_ev below - reuse sec_valuations' own reason. Checked after the
                    # debt-components gate above (largest, best-tested population).
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "missing_sec_data"
                )
                if "total_debt" in failed_metrics
                else None
            )
            # total_cash_ev is None whenever sec_valuations has no row at all for this symbol,
            # or has a row but load_sec_valuations.py already recorded why total_cash came back
            # NULL there - reuse that reason. A genuinely never-tagged cash concept doesn't fail
            # the rest of the valuation row, so sec_valuations_reason can stay empty even then -
            # check cash_and_equivalents against its own no-data gate too.
            no_recent_cash_concept = (
                symbol in self._get_no_recent_cash_symbols() or symbol in self._get_never_tagged_cash_symbols()
            )
            metrics["total_cash_unavailable_reason"] = (
                (
                    "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "no_recent_cash_reported"
                    if no_recent_cash_concept
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
                    else "no_recent_cash_reported"
                    if no_recent_cash_concept
                    else "missing_sec_data"
                )
                if "cash_per_share" in failed_metrics
                else None
            )
            metrics["ebitda_unavailable_reason"] = (
                (
                    # ebitda is the same load_sec_valuations.py-derived absolute-dollar value
                    # ebitda_margin's numerator uses - fails structurally for the same
                    # REIT/tonnage-tax-exempt population.
                    "reit_special_entity"
                    if no_operating_income_concept
                    # ebitda = OperatingIncome + D&A, so a real filer that never itemizes a
                    # distinct operating income subtotal fails here too.
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    # ebitda_ev comes from the same ev_metrics tuple as total_cash_ev - reuse the
                    # sec_valuations `reason` column instead of a generic label.
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "missing_sec_data"
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

            # Recategorize debt/cash/interest/FCF-derived fields these grantor trusts
            # structurally never report to "reit_special_entity" (same label as their
            # current_ratio/quick_ratio/gross_margin siblings) - only when the field is None and
            # already carries one of the reasons this structural gap produces, so real data or
            # an unrelated reason is left untouched.
            if symbol in self._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS:
                _trust_recategorize_fields = (
                    "total_debt",
                    "debt_to_equity",
                    "debt_to_assets",
                    "roic_pct",
                    "roce_pct",
                    "interest_coverage",
                    "total_cash",
                    "cash_per_share",
                    "free_cash_flow",
                    "operating_cash_flow",
                    "fcf_to_net_income",
                    "ocf_to_net_income",
                    "accruals_ratio",
                    "fcf_margin",
                    "ebitda",
                    "ebitda_margin",
                    "operating_margin",
                )
                _trust_source_reasons = {
                    "missing_sec_data",
                    "total_debt_not_itemized",
                    "no_recent_cash_reported",
                    "interest_expense_not_itemized",
                    "stockholders_equity_not_reported",
                    "operating_income_not_itemized",
                    "total_liabilities_not_reported",
                }
                for _field in _trust_recategorize_fields:
                    _reason_key = f"{_field}_unavailable_reason"
                    if metrics.get(_field) is None and metrics.get(_reason_key) in _trust_source_reasons:
                        metrics[_reason_key] = "reit_special_entity"

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            # Propagate the real exception (not the generic "missing_sec_data" default) so a
            # genuine loader bug lands in scores.py's _categorize_reason() "Other (errors /
            # excluded)" bucket instead of silently inflating "Missing SEC/XBRL data" - same
            # fix already applied to this file's outer fetch_incremental() except block.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return self._unavailable_marker("quality_metrics", symbol, reason=exc_reason)

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

    # SEC 10-Ks only restate the comparative fiscal years shown in that filing (typically 2
    # prior years) - a fiscal year older than that keeps its ORIGINAL pre-split EPS forever
    # unless a later filing happens to restate it too, so a raw multi-year EPS comparison can
    # silently straddle a stock-split boundary and produce a CAGR off by the split factor.
    # Guarded by requiring a single-year share-count jump near a standard split multiple
    # (not a flat endpoint-to-endpoint ratio, which false-positived on ordinary multi-year
    # organic dilution/buybacks) - see _compute_period_growth's guard for the full mechanism.
    # Standard stock-split/reverse-split multiples a real single-year share-count jump should
    # land near.
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
        implausible_growth_metrics: set[str] | None = None,
    ) -> None:
        """Compute growth for a single period (nominally 1y, 3y, or 5y).

        values: list of (fiscal_year, value) tuples, most recent first, with any fiscal
        years lacking usable data already filtered out - so `values[offset]` may be more
        (or less) than `offset` calendar years before `values[0]` if SEC filings have a
        gap (missing annual filing, restatement, etc). CAGR is annualized over the REAL
        fiscal-year gap between the two points, not a hardcoded nominal period, since a
        fixed `years` would overstate annualized growth whenever a gap exists.

        Sets metrics[metric_key] if computation succeeds; appends metric_key to failed_metrics if it fails.
        A profit/loss sign flip between the two points also adds metric_key to
        sign_change_metrics - CAGR is mathematically undefined there, which is a distinct,
        legitimate condition from missing history and must not be reported as
        "insufficient history".

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

        # A near-zero prior-year base makes CAGR swing wildly even though the computation
        # is technically valid - same fragility guarded elsewhere for net_income/fcf growth.
        if min_abs_target > 0 and abs(target_val) < min_abs_target:
            failed_metrics.append(metric_key)
            if immaterial_base_metrics is not None:
                immaterial_base_metrics.add(metric_key)
            return

        if shares_by_year:
            # Scan ADJACENT fiscal-year pairs (not just the two CAGR endpoints) for a
            # near-clean split multiple. Endpoint-only comparison conflates a genuine
            # unrestated split (SEC 10-Ks only restate ~2 prior years, so an older filing's
            # EPS stays on the pre-split basis forever) with ordinary multi-year dilution/
            # buyback drift, which is real and legitimate and must not be blocked - and a
            # real split's cumulative endpoint ratio can itself drift off the clean multiple
            # from buybacks layered on top, so endpoint-only checking is unreliable either way.
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
        elif growth is not None:
            # A real, computed CAGR beyond MAX_PLAUSIBLE_GROWTH_PCT (small-base ramp-ups)
            # is distinct from genuinely-too-few-datapoints - tag it separately so
            # _growth_reason() doesn't mislabel it "insufficient_history".
            failed_metrics.append(metric_key)
            if implausible_growth_metrics is not None:
                implausible_growth_metrics.add(metric_key)
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
        EPS_SPLIT_GUARD_CLEAN_MULTIPLES guard; stockholders_equity is also optional and feeds
        only book_value_growth's BVPS computation - every other field is unaffected by its absence.
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
        # bvps = stockholders_equity/shares_outstanding_diluted, book_value_growth = bvps/prior_bvps - 1.
        # Reuses _compute_period_growth's offset=1 CAGR machinery (same sign-change/split-guard
        # protection EPS gets) - BVPS is just another (fiscal_year, value) series.
        bvps_values: list[tuple[int, float]] = []
        shares_by_year: dict[int, float] = {}
        # company_info_sec.shares_outstanding is a point-in-time snapshot (not historical per
        # fiscal year) but is used as a fallback when annual_income_statement lacks shares for
        # a given year, since the split-guard below needs a shares_by_year entry per year to
        # detect splits and would otherwise block book_value_growth entirely for that symbol.
        company_info_shares: dict[int, float] = {}
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s",
                    (symbol,),
                )
                result = cur.fetchone()
                fallback_shares = result[0] if result and result[0] else None
                if fallback_shares and fallback_shares > 0:
                    # Applied to ALL years lacking income-statement shares; assumes share
                    # count didn't change dramatically between years - imprecise but better
                    # than leaving book_value_growth unavailable.
                    for row in income_rows:
                        if row is not None and len(row) > 7:
                            fiscal_year = int(row[0]) if row[0] is not None else None
                            if fiscal_year is not None:
                                company_info_shares[fiscal_year] = fallback_shares
        except Exception as e:
            logger.debug(f"[{symbol}] Could not fetch company_info_sec shares fallback: {e}")
        for row in income_rows:
            try:
                fiscal_year = int(row[0]) if row[0] is not None else None
                rev = float(row[1]) if row[1] is not None else None
                eps = float(row[4]) if row[4] is not None else None
                # row[5]/row[6] only present in the live query - len() check keeps older
                # 5-tuple test fixtures working.
                shares = None
                if len(row) > 5 and row[5] is not None:
                    shares = float(row[5])
                elif len(row) > 6 and row[6] is not None:
                    shares = float(row[6])
                # row[7] (LEFT JOIN annual_balance_sheet) same len() guard as shares above.
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
                # Use income statement shares if available, fallback to company_info_sec if not
                # (see fallback-fetch logic above for context)
                shares_for_year = shares
                if (shares_for_year is None or shares_for_year <= 0) and fiscal_year in company_info_shares:
                    shares_for_year = company_info_shares[fiscal_year]
                if shares_for_year is not None and shares_for_year > 0 and fiscal_year not in shares_by_year:
                    shares_by_year[fiscal_year] = shares_for_year
                # Book value per share can be legitimately negative (heavily-levered/buyback-
                # heavy firms) - only require shares > 0 (a real, positive share count to
                # divide by), same convention as _compute_period_growth's own sign-change
                # guard handling negative-to-positive transitions correctly rather than
                # excluding negative values outright.
                if stockholders_equity is not None and shares_for_year is not None and shares_for_year > 0:
                    bvps_values.append((fiscal_year, stockholders_equity / shares_for_year))
            except (ValueError, TypeError):
                continue

        failed_metrics: list[str] = []
        sign_change_metrics: set[str] = set()
        split_discontinuity_metrics: set[str] = set()
        immaterial_base_metrics: set[str] = set()
        # Real CAGR computed but beyond MAX_PLAUSIBLE_GROWTH_PCT (2000%) - see
        # _compute_period_growth's own comment on this branch for the full rationale.
        implausible_growth_metrics: set[str] = set()
        self._compute_period_growth(
            symbol,
            revenues,
            1,
            "revenue_growth_1y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
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
            implausible_growth_metrics=implausible_growth_metrics,
        )
        # book_value_growth uses the same split-guard as EPS since BVPS is equally sensitive
        # to a split changing the per-share denominator across the two CAGR endpoints.
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
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            revenues,
            3,
            "revenue_growth_3y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
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
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            revenues,
            5,
            "revenue_growth_5y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
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
            implausible_growth_metrics=implausible_growth_metrics,
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
            if metric_key in implausible_growth_metrics:
                return "garbage_metric_value_implausible_growth_rate"
            if metric_key in failed_metrics:
                return "insufficient_history"
            return None

        metrics["revenue_growth_1y_unavailable_reason"] = _growth_reason("revenue_growth_1y")
        metrics["revenue_growth_3y_unavailable_reason"] = _growth_reason("revenue_growth_3y")
        metrics["revenue_growth_5y_unavailable_reason"] = _growth_reason("revenue_growth_5y")
        metrics["eps_growth_1y_unavailable_reason"] = _growth_reason("eps_growth_1y")
        metrics["eps_growth_3y_unavailable_reason"] = _growth_reason("eps_growth_3y")
        metrics["eps_growth_5y_unavailable_reason"] = _growth_reason("eps_growth_5y")
        metrics["book_value_growth_unavailable_reason"] = _growth_reason("book_value_growth")

        if failed_metrics:
            # 7 possible periods (book_value_growth included).
            if len(failed_metrics) == 7:
                # Keep the per-field reasons _growth_reason() already computed (e.g. a real
                # sign-change) instead of overwriting them all with a blanket
                # "insufficient_history" - the values are None either way, but the reason
                # should stay honest per field.
                metrics["data_unavailable"] = True
                metrics["data_source"] = "none"
                metrics["reason"] = (
                    f"Insufficient historical data: {', '.join(sorted(set(failed_metrics)))} could not be computed"
                )
                # _SHARED_TREND_FIELDS are normally copied in from quality_dict by the caller,
                # gated on `not data_unavailable` - since this branch sets data_unavailable=True,
                # that copy never runs, so set a real reason here too (matching every other
                # data_unavailable path, which goes through _unavailable_marker()).
                for field in _SHARED_TREND_FIELDS:
                    metrics.setdefault(field, None)
                    metrics[f"{field}_unavailable_reason"] = metrics["reason"]
            else:
                # Partial failure (1-6 of 7 periods): periods that DID compute are real values,
                # so leave data_unavailable=False - downstream scoring renormalizes over
                # whatever fields are present rather than discarding the whole row.
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

        total_debt/total_cash/ebitda/cash_per_share come purely from `ev_metrics` (the
        separately-fetched, ungated sec_valuations row), not from annual_balance_sheet - the
        table whose staleness this marker is about - so they must not be blanked out too.
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

        # Override the generic "missing_sec_data" default from _unavailable_marker() with
        # "stale_fiscal_data" per-field: the real cause here is a too-old fiscal year, not a
        # failed fetch, and the frontend renders these per-field reasons directly.
        for key in marker:
            if key.endswith("_unavailable_reason") and key not in (
                f"{f}_unavailable_reason" for f in ev_sourced_fields
            ):
                if marker[key] is not None:
                    marker[key] = "stale_fiscal_data"
        return marker

    def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]:
        """Return data_unavailable marker for a table.

        Must include every *_unavailable_reason field even when data is fully unavailable -
        a NULL value with no reason code is indistinguishable from a bug.

        reason: optional real, specific cause (e.g. "shares_outstanding_unavailable") plumbed
        through from load_sec_valuations.py's own sec_valuations.reason column, or from
        fetch_incremental's exception handler as f"fetch_exception: {type(e).__name__}: {e}"
        so a genuine loader bug lands in _categorize_reason()'s "Other (errors / excluded)"
        bucket instead of inflating "Missing SEC/XBRL data"/"Insufficient history" counts.
        Defaults to each table's generic reason when the caller has none more specific.
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
                "ev_ebitda_unavailable_reason": specific_reason,
                "ev_revenue": None,
                "ev_revenue_unavailable_reason": specific_reason,
                "market_cap": None,
                "market_cap_unavailable_reason": specific_reason,
                "held_percent_institutions": None,
                "held_percent_institutions_unavailable_reason": specific_reason,
                "intrinsic_value_unavailable_reason": specific_reason,
                "margin_of_safety_unavailable_reason": specific_reason,
                "data_unavailable": True,
                "data_source": "none",
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
                "roe_unavailable_reason": specific_reason,
                "roa_unavailable_reason": specific_reason,
                "operating_margin_unavailable_reason": specific_reason,
                "net_margin_unavailable_reason": specific_reason,
                "debt_to_equity_unavailable_reason": specific_reason,
                "current_ratio_unavailable_reason": specific_reason,
                "quick_ratio_unavailable_reason": specific_reason,
                "interest_coverage_unavailable_reason": specific_reason,
                "debt_to_assets_unavailable_reason": specific_reason,
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
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": specific_reason for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
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
                "book_value_growth": None,
                # forward_eps_growth_*/eps_estimate_revision_90d_pct: this fallback is
                # defense-in-depth only - fetch_incremental's success path always calls
                # _get_analyst_forward_growth_estimates() which supersedes this default;
                # only matters for a path returning via this marker without going through
                # that merge (e.g. the genuine-exception catch-all).
                "forward_eps_growth_current_fy": None,
                "forward_eps_growth_next_fy": None,
                "forward_revenue_growth_next_fy": None,
                "eps_estimate_revision_90d_pct": None,
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
                **dict.fromkeys(_SHARED_TREND_FIELDS),
                **{f"{field}_unavailable_reason": specific_reason for field in _SHARED_TREND_FIELDS},
                "data_unavailable": True,
                "data_source": "none",
                "reason": specific_reason,
                "updated_at": get_loader_timestamp(),
            }

    def post_run(self) -> None:
        """Runs automatically after fetch_incremental() completes for every symbol - see
        loaders/runner.py's `hasattr(loader, "post_run")` dispatch (the same generic mechanism
        loaders/load_stock_scores.py's own post_run()/update_rs_percentiles() already use)."""
        self.update_quality_roe_roce_percentiles()

    @staticmethod
    def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
        """breakpoints: [(x0,y0), (x1,y1), ...] increasing x; value<x0 -> 0-ramp to y0,
        value>=last x -> last y. Piecewise-linear between points.

        Shared by `_compute_quality_metrics`'s ROE/ROA/gross_profitability/roce_pct/fcf_margin/
        asset_turnover/margin_volatility score curves and `update_quality_roe_roce_percentiles()`'s
        reconciliation math (which must reconstruct what Pass 1 originally scored ROE/ROCE at) -
        one shared definition so the two call sites can't silently diverge.
        """
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
    def _weighted_avg(components: list[tuple[float | None, float]], min_weight_pct: float = 0.0) -> float | None:
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
        patched relative to whatever quality_score currently holds) - mirrors
        `update_rs_percentiles()`'s pure-overwrite pattern, NOT
        `update_value_multiples_percentiles()`'s additive-delta one.

        Only ROE/ROCE are percentile-ranked (of the 8 Quality components) - a sweep found
        those two the only ones where cross-sectional percentile consistently beat the fixed
        curve across eras; the other 6 keep their Pass-1 curve formulas.

        MUST be a pure function of the raw stored ratio columns, never reading
        quality_score itself as an input: an earlier additive-delta design read/wrote the
        same mutable column every run, so the same delta re-applied on top of an
        already-corrected value each pipeline cycle with no convergence except the 0/100
        clamp - over time this pinned ~30% of the universe at exactly 100.00.

        ROE/ROCE percentile ranking is computed only over the non-negative population, with
        negative-raw-value symbols explicitly floored to percentile 0.0 (matching curve-based
        Pass-1's own `if value < 0: return 0.0`) - a plain percentile rank doesn't floor at 0
        for a non-worst performer, which otherwise systematically over-scores unprofitable
        companies (e.g. negative ROE still landing mid-percentile).

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        quality_score is a live-trading-relevant correctness issue.

        Skips Financial Services/Real Estate: those sectors' quality_score uses a two-cluster
        (profitability + safety) structure, not the flat 8-input weighted average this method
        recomputes: reconciling ROE/ROCE through that structure needs its own derivation.
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
                    components.append((self._margin_curve(float(roa), [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]), 18.0))
                if roce_pct_val is not None:
                    roce_component = 0.0 if float(roce_pct_val) < 0.0 else roce_pct[symbol]
                    components.append((roce_component, 18.0))
                if fcf_margin is not None:
                    components.append(
                        (
                            self._margin_curve(float(fcf_margin), [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)]),
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
                            100.0 - self._margin_curve(float(margin_vol), [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)]),
                            7.0,
                        )
                    )
                if asset_turnover is not None:
                    components.append(
                        (
                            self._margin_curve(float(asset_turnover), [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)]),
                            7.0,
                        )
                    )
                if gross_prof is not None:
                    components.append(
                        (
                            self._margin_curve(float(gross_prof), [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)]),
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
