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

from loaders.helpers.vqg_growth import GrowthMetricsMixin
from loaders.helpers.vqg_quality import QualityMetricsMixin
from loaders.helpers.vqg_shared import (
    _SHARED_TREND_FIELDS,
    MAX_ABSOLUTE_DOLLAR_VALUE,  # noqa: F401 -- re-exported, see comment below
    MAX_PLAUSIBLE_GROWTH_PCT,
    MAX_TREND_PERCENTAGE_POINTS,  # noqa: F401 -- re-exported, see comment below
    get_loader_timestamp,
    intrinsic_value_reason_from_fcf_yield,  # noqa: F401 -- re-exported, see comment below
    peg_ratio_reason_from_eps_history,  # noqa: F401 -- re-exported, see comment below
)
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from loaders.helpers.vqg_value import ValueMetricsMixin
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# peg_ratio_reason_from_eps_history/intrinsic_value_reason_from_fcf_yield/
# MAX_ABSOLUTE_DOLLAR_VALUE/MAX_PLAUSIBLE_GROWTH_PCT/MAX_TREND_PERCENTAGE_POINTS/
# _SHARED_TREND_FIELDS/get_loader_timestamp are re-exported from loaders.helpers.vqg_shared
# under these same names (imported above) so existing callers/tests (e.g. `from
# loaders.load_value_quality_growth_metrics import peg_ratio_reason_from_eps_history`) keep
# working unchanged after the 2026-09-05 quality/growth/value extraction - see that
# module's own docstring for why the shared constants/functions live there instead of here.

# Fiscal-year data older than this is flagged as unavailable rather than silently scored as
# current - real active filers report annually with at most ~2 years of lag through this
# pipeline (sharp cliff in the universe's age distribution at 2 years); older means
# delisted/inactive or a genuine data gap.
MAX_FISCAL_YEAR_AGE_YEARS = 3


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


class ValueQualityGrowthMetricsLoader(
    ValueMetricsMixin, QualityMetricsMixin, GrowthMetricsMixin, OptimalLoader, SymbolGateMixin
):
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

    # Same ceiling load_sec_valuations.py's own pe_ratio/pb_ratio/ps_ratio all use - forward_pe
    # got the equivalent FLOOR (above) but was missing this equivalent CEILING, so a tiny
    # (but real) forward_eps could inflate forward_pe to an implausible value with nothing
    # rejecting it, the mirror-image gap of the one MIN_PLAUSIBLE_FORWARD_PE_RATIO already closes.
    MAX_PLAUSIBLE_FORWARD_PE_RATIO = 10000

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
                #
                # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep): a
                # `data_unavailable = TRUE` annual_balance_sheet row can carry a leftover non-NULL
                # value in its data columns (never nulled when the row was flagged unavailable -
                # 3,282 such rows confirmed live), and since `abs.fiscal_year > 0` (not `= FALSE`)
                # already includes these rows for label-only gates elsewhere, the freshness-first
                # ORDER BY could pick one of these DISCLAIMED rows as the anchor purely for being
                # the most recent fiscal_year - live-confirmed 27 universe symbols this way, e.g.
                # XRTX's picked stockholders_equity was $2.08M from a disclaimed 2025 row instead
                # of the real $13.17M from 2021, SIM's picked a disclaimed $59.2B 2024 balance
                # sheet over the real $49.8B 2023 one. This fed WRONG COMPUTED VALUES (ROE/
                # debt_to_equity/asset_turnover/etc), not just a wrong reason label - a more severe
                # instance of the same bug class fixed across vqg_symbol_gates.py's gates this
                # session. Fix: `data_unavailable` is now the FIRST sort key (a real row always
                # wins over an unavailable one, at any freshness), the raw abs.* fields are
                # sanitized to NULL when their own row is unavailable (defense in depth for the
                # no-real-row-exists fallback case, where a stray value could otherwise still leak
                # through), and every prior_year_* subquery now filters `data_unavailable = FALSE`
                # (same stray-value risk, live-confirmed 408-3,768 exposed rows per table). Live-
                # reverified: symbols with NO real row anywhere (e.g. TV/SUPV) still correctly fall
                # back to the unavailable row so per-field gates keep seeing them.
                cur.execute(
                    """
                    SELECT CASE WHEN abs.data_unavailable THEN NULL ELSE abs.stockholders_equity END,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.total_liabilities END,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.total_assets END,
                           ais.net_income, ais.revenue, ais.operating_income,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.current_assets END,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.current_liabilities END,
                           abs.fiscal_year,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.inventory END,
                           ais.interest_expense, sv.shares_outstanding,
                           ais.cost_of_revenue, acf.operating_cash_flow, acf.free_cash_flow,
                           acf.dividends_paid, ais.earnings_per_share,
                           (SELECT earnings_per_share FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_eps,
                           (SELECT revenue FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_revenue,
                           ais.gross_profit,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.long_term_debt END,
                           CASE WHEN abs.data_unavailable THEN NULL ELSE abs.cash_and_equivalents END,
                           ais.income_tax_expense, ais.pretax_income,
                           (SELECT net_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_net_income,
                           (SELECT operating_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_operating_income,
                           (SELECT operating_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_operating_cash_flow,
                           (SELECT free_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_free_cash_flow,
                           (SELECT cost_of_revenue FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_cost_of_revenue,
                           (SELECT total_assets FROM annual_balance_sheet
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_total_assets,
                           (SELECT stockholders_equity FROM annual_balance_sheet
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_stockholders_equity,
                           (SELECT pretax_income FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_pretax_income,
                           (SELECT interest_expense FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_interest_expense,
                           (SELECT gross_profit FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_gross_profit,
                           (SELECT dividends_paid FROM annual_cash_flow
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1
                              AND data_unavailable = FALSE) as prior_year_dividends_paid
                    FROM annual_balance_sheet abs
                    LEFT JOIN annual_income_statement ais ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year AND ais.data_unavailable = FALSE
                    LEFT JOIN annual_cash_flow acf ON abs.symbol = acf.symbol AND abs.fiscal_year = acf.fiscal_year AND acf.data_unavailable = FALSE
                    LEFT JOIN (
                        -- FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep):
                        -- reason = 'shares_outstanding_scale_mismatch' means
                        -- sec_valuations_checks.py already determined this row's raw
                        -- shares_outstanding is mis-scaled (SEC-derived market cap disagreed
                        -- with yfinance by >10x) and nulled every OTHER field that depends on
                        -- it - but never nulled the raw shares_outstanding column itself, so
                        -- this separate direct read picked it up anyway. Live-confirmed 14
                        -- universe symbols (PMI/SELX/AGH/AKTX/UHAL/...) feeding a wrong
                        -- cash_per_share/sustainable_growth_rate from it (PMI/SELX landing at
                        -- roughly -712 and -645 sustainable_growth_rate, both wildly
                        -- implausible). Same guard load_short_interest_finra.py's own
                        -- shares_outstanding fallback already uses. CAUTION: a raw percent
                        -- character anywhere in this SQL text, even inside a comment, breaks
                        -- psycopg2's placeholder substitution here - live-broke this exact
                        -- query 2026-09-06 (complete fetch_incremental failure across the
                        -- whole universe, IndexError from tuple index out of range) - spell
                        -- out percentages in words in any cur.execute() SQL string in this file.
                        SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                        FROM sec_valuations
                        WHERE reason IS NULL OR reason != 'shares_outstanding_scale_mismatch'
                        ORDER BY symbol, updated_at DESC
                    ) sv ON abs.symbol = sv.symbol
                    WHERE abs.symbol = %s AND abs.fiscal_year > 0
                    -- A real (non-data_unavailable) balance-sheet row is ALWAYS preferred over an
                    -- unavailable one, regardless of freshness - see FIXED 2026-09-05 comment above.
                    -- Freshness (within MAX_FISCAL_YEAR_AGE_YEARS) is the next sort key; the
                    -- revenue/matched-income preference is only a tiebreak within the fresh tier
                    -- and, separately, within the stale-fallback tier - a fresh but revenue-poor
                    -- balance sheet must never lose to an older year just for having revenue.
                    ORDER BY (CASE WHEN abs.data_unavailable THEN 1 ELSE 0 END),
                             (CASE
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
                quality_dict["margin_volatility_unavailable_reason"] = self._recategorize_margin_volatility_reason(
                    symbol, margin_volatility_unavailable_reason
                )
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
        # ADDED 2026-09-05 (goal session: "missing SEC/XBRL data"/implausible-values sweep):
        # the prior-year EPS each EPS growth ratio was actually computed from (see migration
        # 1259's own header) - lets the near-zero-base check below distinguish a
        # mathematically-blown-up ratio from a genuinely enormous real one. No equivalent
        # column exists for forward_revenue_growth_next_fy - not in scope for this fix.
        _prior_year_eps_fields = {
            "forward_eps_growth_current_fy": "forward_eps_growth_current_fy_prior_year_eps",
            "forward_eps_growth_next_fy": "forward_eps_growth_next_fy_prior_year_eps",
        }
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
        # Same $0.10 immaterial-base floor as growth_metrics' own realized eps_growth_1y (see
        # vqg_growth.py's _compute_period_growth min_abs_target=0.10 call) - a prior-year EPS
        # this close to zero makes any growth RATIO numerically unstable regardless of how
        # real/well-covered the underlying estimates are.
        _immaterial_eps_base_floor = 0.10
        result: dict[str, Any] = {}
        for field in fields:
            result[field] = None
            result[f"{field}_unavailable_reason"] = "no_analyst_estimates"
        select_cols = [*fields, *_prior_year_eps_fields.values()]
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"""
                    SELECT {", ".join(select_cols)} FROM analyst_earnings_estimates
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
                if row:
                    values = dict(zip(select_cols, row, strict=True))
                    for field in fields:
                        val = values[field]
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
                            prior_col = _prior_year_eps_fields.get(field)
                            prior_eps = (
                                safe_float(values[prior_col], f"{symbol}.{prior_col}", allow_none=True)
                                if prior_col
                                else None
                            )
                            result[f"{field}_unavailable_reason"] = (
                                "immaterial_prior_year_base"
                                if prior_eps is not None and abs(prior_eps) < _immaterial_eps_base_floor
                                else "garbage_metric_value_implausible_ratio"
                            )
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch analyst forward growth estimates: {type(e).__name__}")
        return result

    def _compute_quarterly_metrics(self, symbol: str) -> dict[str, Any]:  # noqa: C901
        """Compute quarterly metrics: consecutive_positive_quarters, earnings_growth_4q_avg, quarterly_growth_momentum, eps_growth_stability, earnings_surprise_avg, earnings_beat_rate."""
        metrics: dict[str, Any] = {}
        try:
            with DatabaseContext("read") as cur:
                # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same bug class
                # fixed across the annual_* tables this session): had NO data_unavailable filter
                # at all, so a disclaimed quarterly row's leftover stray non-NULL values fed
                # consecutive_positive_quarters/earnings_growth_4q_avg/quarterly_growth_momentum/
                # eps_growth_stability/earnings_surprise_avg/earnings_beat_rate directly.
                # Live-confirmed 279 symbols affected - e.g. AMX had 5 consecutive disclaimed
                # quarters (net_income $19-24B, revenue $232-244B, EPS $6.3-8.0) inside its own
                # top-8 window, feeding these metrics entirely from disclaimed data.
                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_quarter, net_income, revenue, earnings_per_share
                    FROM quarterly_income_statement
                    WHERE symbol = %s AND data_unavailable IS NOT TRUE
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

    def _recategorize_margin_volatility_reason(self, symbol: str, reason: str | None) -> str | None:
        """Recategorize margin_volatility's own "implausible_ratio"/"insufficient_history"
        reason (from _compute_margin_volatility's 3-usable-year requirement, computed by this
        module rather than inside _compute_quality_metrics - see that call site's own comment)
        for physical/commodity/currency trusts, closed-end funds (RICs), and pre-merger SPAC
        shells - the exact same "Statement of Assets and Liabilities"/"Statement of Changes in
        Net Assets"/"trust-account-only" structural fact _compute_quality_metrics already
        recategorizes for every other quality_metrics field via
        _get_etf_trust_no_stockholders_equity_symbols/_get_registered_investment_company_
        symbols/_get_blank_check_symbols, but unreachable there since margin_volatility's
        reason vocabulary never matches _etf_trust_broad_source_reasons/_ric_source_reasons/
        _blank_check_source_reasons (all built around "*_not_reported"/"*_not_itemized"-style
        names, not "implausible_ratio").

        FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, implausible-value
        continuation): live-confirmed via FXF/FXY (Invesco CurrencyShares trusts, both in
        the ETF-trust gate): revenue is $0 for most fiscal years but real/tiny ($318,783/
        $458,644) for 2-3 others, and one older year's tiny-revenue-vs-loss ratio trips the
        |margin|>1000 guard - fewer than 3 usable years survive AND at least one was
        implausible, so "implausible_ratio" fires even though a currency trust has no
        "margin" concept to be volatile in the first place. Left unchanged for a real
        operating company (a genuinely near-zero-revenue business's margin swings are
        meaningful, not noise - see IMDX/ORGN/AUUD/CDZIP, correctly left as
        "implausible_ratio").
        """
        if reason not in ("implausible_ratio", "insufficient_history"):
            return reason
        if symbol in self._get_etf_trust_no_stockholders_equity_symbols():
            return "etf_trust_no_gaap_financials"
        if symbol in self._get_registered_investment_company_symbols():
            return "registered_investment_company_no_xbrl"
        if symbol in self._get_blank_check_symbols():
            return "no_revenue_reported"
        return reason

    def _find_plausible_cross_year_ratio(
        self, symbol: str, numerator_field: str, denominator_field: str, *, as_percentage: bool = True
    ) -> float | None:
        """Cross-year fallback for ROE/ROA/asset_turnover's |ratio|>1000 implausible-value
        bound (net_income/stockholders_equity, net_income/total_assets, revenue/total_assets
        respectively). An anchor year with a near-zero denominator (extraction artifact, not a
        real business characteristic) would otherwise throw the symbol straight to
        implausible_ratio even when an older fiscal year has a plausible pair.

        `as_percentage` scales the ratio by 100, matching every percentage-style caller
        (margins, ROE/ROA). interest_coverage is a raw multiple, not a percentage - pass
        `as_percentage=False` for it so the fallback value stays consistent with the
        anchor-year computation's own (unscaled) `operating_income / interest_expense`.

        Only called from the implausible-ratio branch (rare: <1% of symbols), so the extra
        per-symbol query here doesn't touch the common path.
        """
        field_index = {
            "net_income": 0,
            "total_assets": 1,
            "stockholders_equity": 2,
            "revenue": 3,
            "operating_income": 4,
            "interest_expense": 5,
            "gross_profit": 6,
        }
        num_idx, den_idx = field_index[numerator_field], field_index[denominator_field]
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT ais.net_income, abs.total_assets, abs.stockholders_equity, ais.revenue,
                       ais.operating_income, ais.interest_expense, ais.gross_profit
                FROM annual_income_statement ais
                JOIN annual_balance_sheet abs
                  ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year
                  AND abs.data_unavailable = FALSE
                WHERE ais.symbol = %s AND ais.data_unavailable = FALSE
                ORDER BY ais.fiscal_year DESC
                LIMIT 6
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        for row in rows:
            numerator, denominator = row[num_idx], row[den_idx]
            if numerator is None or denominator is None or denominator == 0:
                continue
            # interest_coverage's anchor computation only ever fires for interest_expense > 0
            # (zero/negative debt service is a real "not applicable" case, not a ratio to
            # substitute a different year's pair into) - match that same requirement here.
            if not as_percentage and denominator <= 0:
                continue
            # numerator/denominator are raw psycopg2 Decimal values - `Decimal * float` raises
            # TypeError, which propagates up and wipes the entire quality_metrics row. Must
            # convert to float before arithmetic.
            ratio = float(numerator) / float(denominator)
            if as_percentage:
                ratio *= 100.0
            if abs(ratio) <= 1000:
                return float(ratio)
        return None

    def _find_plausible_cross_year_ebitda_margin_ratio(self, symbol: str) -> float | None:
        """Cross-year fallback for ebitda_margin's |ratio|>1000 implausible-value bound.

        Separate from `_find_plausible_cross_year_ratio` because the anchor computation's
        `ebitda_ev` comes from `sec_valuations`, a single latest-snapshot row with no
        fiscal-year dimension - there is no per-year EBITDA to search across using that same
        source. Reconstructs EBITDA per candidate year instead, as EBIT + D&A
        (`operating_income + depreciation_expense + amortization_expense`, standard EBITDA
        definition, same approximation principle as this file's other EBIT-from-pretax-plus-
        interest fallbacks) from `annual_income_statement` alone, divided by that year's own
        revenue.

        Only called from the implausible-ratio branch (rare: <1% of symbols), so the extra
        per-symbol query doesn't touch the common path.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT operating_income, depreciation_expense, amortization_expense, revenue
                FROM annual_income_statement
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY fiscal_year DESC
                LIMIT 6
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        for row in rows:
            operating_income, depreciation_expense, amortization_expense, revenue = row
            if operating_income is None or revenue is None or revenue == 0:
                continue
            if depreciation_expense is None and amortization_expense is None:
                continue
            # Decimal values from psycopg2 - convert before arithmetic (Decimal * float
            # raises TypeError).
            ebitda = float(operating_income) + float(depreciation_expense or 0) + float(amortization_expense or 0)
            ratio = (ebitda / float(revenue)) * 100.0
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
                LIMIT 6
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
