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
from datetime import date
from math import isnan
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# GOVERNANCE: quality/growth metrics previously stamped updated_at=today() regardless of
# how old the underlying SEC fiscal-year data was - verified live examples scoring stocks
# off 13-17 year old financials as if freshly updated (LPL/SID fiscal_year 2009-2012). The
# universe's actual fiscal-year-age distribution has a sharp cliff at 2 years (156 symbols
# at age=2, only 6 at age=3) - real active filers report annually with at most ~2 years of
# lag through this pipeline, so anything older is either delisted/inactive or a genuine
# data gap that must be flagged, not silently scored as current.
MAX_FISCAL_YEAR_AGE_YEARS = 3

# Computed once in _compute_quality_metrics (needs balance-sheet data _compute_growth_metrics
# doesn't have), then mirrored into growth_dict in fetch_incremental - see that call site for
# why quality_metrics and growth_metrics each carry their own copy of the same 11 values.
_SHARED_TREND_FIELDS = (
    "net_income_growth_yoy", "operating_income_growth_yoy", "gross_margin_trend",
    "operating_margin_trend", "net_margin_trend", "roe_trend", "sustainable_growth_rate",
    "quarterly_growth_momentum", "fcf_growth_yoy", "ocf_growth_yoy", "asset_growth_yoy",
)


class ValueQualityGrowthMetricsLoader(OptimalLoader):
    """Consolidated value + quality + growth metrics from SEC + valuations.

    Writes to 3 output tables in single per-symbol transaction:
    - value_metrics (PE, PB, PS, PEG, FCF, dividend yield from SEC)
    - quality_metrics (ROE, margins, debt ratios from SEC)
    - growth_metrics (revenue/EPS growth from SEC)
    """

    table_name = "value_metrics"  # Primary table for watermarking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0  # CRITICAL: Fail-fast if >20% of liquid stocks lack SEC data (data source issue). Foreign/OTC/microcaps expected to fail.
    exclude_etfs_from_symbols = True

    def run(self, symbols: list[str], parallelism: int | None = None, backfill_days: int | None = None) -> dict[str, Any]:  # type: ignore[override]  # noqa: C901
        """Override run() to write to 3 tables instead of 1.

        backfill_days: accepted for interface parity with runner.py's generic --backfill-days/
        BACKFILL_DAYS CLI/env path (loaders/runner.py calls loader.run(symbols, parallelism=...,
        backfill_days=...) whenever either is set) - unused here since fetch_incremental() always
        recomputes from the latest SEC/sec_valuations rows rather than filtering by date.
        """
        from utils.loaders.config import get_default_parallelism

        value_inserts = 0
        quality_inserts = 0
        growth_inserts = 0
        symbols_succeeded = 0
        symbols_failed = 0

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
                        continue

                    # Debug: check metrics structure before unpacking
                    if not isinstance(metrics, list) or not metrics[0]:
                        logger.error(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: metrics is {type(metrics)}, metrics[0] is {type(metrics[0]) if metrics else 'None'} (CRITICAL BUG)"
                        )
                        symbols_failed += 1
                        continue

                    metric_tuple = metrics[0]
                    if not isinstance(metric_tuple, tuple) or len(metric_tuple) != 3:
                        logger.error(
                            f"[VALUE_QUALITY_GROWTH] {symbol}: metric_tuple is {type(metric_tuple)}, len={len(metric_tuple) if hasattr(metric_tuple, '__len__') else 'unknown'} (expected tuple of 3)"
                        )
                        symbols_failed += 1
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
                            else:
                                logger.warning(
                                    f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics unavailable: {quality_row.get('reason')}"
                                )

                        # Insert growth metrics (same reasoning as quality metrics above).
                        if growth_row:
                            self._insert_growth_metrics(cur, growth_row)
                            if not growth_row.get("data_unavailable"):
                                growth_inserts += 1
                            else:
                                logger.warning(
                                    f"[VALUE_QUALITY_GROWTH] {symbol}: Growth metrics unavailable: {growth_row.get('reason')}"
                                )

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

            # VERIFY: Confirm all 3 tables actually have TODAY's data before claiming success (FAIL-FAST)
            today_iso = date.today().isoformat()
            with DatabaseContext("read") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    safe_table = assert_safe_table(table)
                    cur.execute(f"SELECT COUNT(*) FROM {safe_table} WHERE updated_at::date = %s", (today_iso,))
                    result = cur.fetchone()
                    today_count = result[0] if result else 0
                    if today_count == 0:
                        raise RuntimeError(
                            f"[VALUE_QUALITY_GROWTH VERIFICATION FAILED] {table}: "
                            f"0 rows with today's date ({today_iso}) found after load. "
                            f"Data was NOT persisted. This is a CRITICAL DATA INTEGRITY issue."
                        )
                    logger.info(f"[VALUE_QUALITY_GROWTH VERIFIED] {table}: {today_count} rows with today's date")

            # Mark all 3 tables as ok via LoaderStatusManager (uses advisory locks)
            with DatabaseContext("write") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    # Query the actual MAX(date) from each table
                    safe_table = assert_safe_table(table)
                    cur.execute(f"SELECT MAX(updated_at)::date FROM {safe_table}")
                    result = cur.fetchone()
                    actual_latest_date = result[0] if result and result[0] else None

            for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                manager = managers.get(table) or LoaderStatusManager(table)
                # Update progress to mark all symbols as loaded (this loader loads all at once, not per-symbol)
                manager.update_progress(symbols_loaded=len(symbols), symbol_count=len(symbols), completion_pct=100.0)
                manager.mark_completed()

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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:  # type: ignore[override]
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
                            WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1) as prior_year_stockholders_equity
                    FROM annual_balance_sheet abs
                    LEFT JOIN annual_income_statement ais ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year AND ais.data_unavailable = FALSE
                    LEFT JOIN annual_cash_flow acf ON abs.symbol = acf.symbol AND abs.fiscal_year = acf.fiscal_year AND acf.data_unavailable = FALSE
                    LEFT JOIN (
                        SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                        FROM sec_valuations
                        ORDER BY symbol, updated_at DESC
                    ) sv ON abs.symbol = sv.symbol
                    WHERE abs.symbol = %s AND abs.data_unavailable = FALSE
                    ORDER BY abs.fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol, symbol, symbol, symbol, symbol, symbol, symbol, symbol, symbol, symbol),
                )
                quality_row_db = cur.fetchone()

                # Get annual income statement history for growth computation (not from growth_metrics table)
                # NOTE: Filters by revenue IS NOT NULL - companies without revenue will be skipped
                cur.execute(
                    """
                    SELECT fiscal_year, revenue, operating_income, net_income, earnings_per_share
                    FROM annual_income_statement
                    WHERE symbol = %s AND revenue IS NOT NULL AND data_unavailable = FALSE
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
                    quality_dict = self._unavailable_marker("quality_metrics", symbol)
                    quality_dict["reason"] = stale_reason

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
            if not growth_dict.get("data_unavailable") and not quality_dict.get("data_unavailable"):
                for field in _SHARED_TREND_FIELDS:
                    if quality_dict.get(field) is not None:
                        growth_dict[field] = quality_dict[field]

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

        # forward_pe = current_price / consensus forward EPS (migration 1179: load_sec_valuations.py
        # itself stays SEC-only by design, so this joins analyst_earnings_estimates - the real
        # yfinance-sourced forward-EPS consensus, since SEC filings never carry forward estimates).
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
        core_metrics = [pe, pb, ps, fcf_yield]
        if all(m is None for m in core_metrics):
            return self._unavailable_marker("value_metrics", symbol)

        # Track which fields are unavailable (Session 389)
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
            "value_score": None,  # Computed in load_stock_scores, copied here for convenience
            "pe_ratio_unavailable_reason": "missing_sec_data" if pe is None else None,
            "pb_ratio_unavailable_reason": "missing_sec_data" if pb is None else None,
            "ps_ratio_unavailable_reason": "missing_sec_data" if ps is None else None,
            "peg_ratio_unavailable_reason": "missing_sec_data" if peg is None else None,
            "dividend_yield_unavailable_reason": "missing_sec_data" if dividend_yield is None else None,
            "fcf_yield_unavailable_reason": "missing_sec_data" if fcf_yield is None else None,
            "forward_pe_unavailable_reason": "no_analyst_estimates" if forward_pe is None else None,
            "ev_ebitda_unavailable_reason": "depreciation_amortization_not_loaded" if ev_ebitda is None else None,
            "ev_revenue_unavailable_reason": "missing_sec_data" if ev_revenue is None else None,
            "market_cap_unavailable_reason": None,  # Market cap in stock_symbols, not here
            "held_percent_insiders_unavailable_reason": None,  # In positioning_metrics, not here
            "held_percent_institutions_unavailable_reason": None,  # In positioning_metrics, not here
            "data_unavailable": False,
            "data_source": "sec_audited",
            "updated_at": date.today().isoformat(),
        }

    @staticmethod
    def _nan_to_none(value: float | None) -> float | None:
        """Convert NaN to None for data integrity. NaN should never be stored in DB."""
        if value is not None and isinstance(value, float) and isnan(value):
            return None
        return value

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
            pretax_income = self._nan_to_none(
                safe_float(quality_row[23], f"{symbol}.pretax_income", allow_none=True)
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
                "updated_at": date.today().isoformat(),
            }

            failed_metrics: list[str] = []

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
            if operating_income is not None and revenue is not None and revenue != 0:
                metrics["operating_margin"] = float((operating_income / revenue) * 100)
            else:
                failed_metrics.append("operating_margin")

            # Net Margin = Net Income / Revenue
            if net_income is not None and revenue is not None and revenue != 0:
                metrics["net_margin"] = float((net_income / revenue) * 100)
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

            # Interest Coverage = Operating Income / Interest Expense. Higher is better
            # (ability to service debt from operating earnings). Column existed on
            # quality_metrics (migration predates this loader) and is already displayed by
            # the frontend/API, but no loader ever computed it - annual_income_statement had
            # no interest_expense column until migration 1145. Only computed when
            # interest_expense > 0 (zero debt service is a real "not applicable" case, not
            # an infinite/undefined ratio to fake a max score for).
            if interest_expense is not None and interest_expense > 0 and operating_income is not None:
                metrics["interest_coverage"] = float(operating_income / interest_expense)
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
            gross_profit_used = None
            if gross_profit_direct is not None:
                gross_profit_used = gross_profit_direct
            elif cost_of_revenue is not None:
                gross_profit_used = revenue - cost_of_revenue if revenue is not None else None

            if gross_profit_used is not None and revenue is not None and revenue != 0:
                metrics["gross_margin"] = float((gross_profit_used / revenue) * 100)
            else:
                failed_metrics.append("gross_margin")

            # EBITDA Margin = EBITDA / Revenue
            if ebitda_ev is not None and revenue is not None and revenue != 0:
                metrics["ebitda_margin"] = float((ebitda_ev / revenue) * 100)
            else:
                failed_metrics.append("ebitda_margin")

            # ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate)
            # FIXED (migration 1178): previously always unavailable - a hardcoded 25% tax-rate
            # assumption was correctly rejected as synthetic (real effective rates vary 5-35%+
            # by jurisdiction/structure), but no real source was wired up either. Now uses the
            # real SEC-reported IncomeTaxExpenseBenefit/pretax_income concepts. Bounded to
            # [0%, 60%]: a real but implausible rate (pretax income near zero from a one-time
            # NOL/credit swing) would distort NOPAT worse than marking unavailable.
            effective_tax_rate = None
            if income_tax_expense is not None and pretax_income is not None and pretax_income > 0:
                candidate_rate = income_tax_expense / pretax_income
                if 0.0 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate

            # Invested Capital = Stockholders' Equity + Long-Term Debt - Cash & Equivalents
            # CRITICAL: Require ALL three components; do not default missing debt/cash to 0
            # ROIC calculation needs complete balance sheet data, not partial guesses
            invested_capital = None
            if (
                stockholders_equity is not None
                and long_term_debt_bs is not None
                and cash_and_equivalents_bs is not None
            ):
                invested_capital = stockholders_equity + long_term_debt_bs - cash_and_equivalents_bs

            if (
                effective_tax_rate is not None
                and operating_income is not None
                and invested_capital is not None
                and invested_capital > 0
            ):
                nopat = operating_income * (1 - effective_tax_rate)
                metrics["roic_pct"] = float((nopat / invested_capital) * 100)
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
            if dividends_paid is not None and net_income is not None and net_income > 0:
                metrics["payout_ratio"] = float((dividends_paid / net_income) * 100)
            else:
                failed_metrics.append("payout_ratio")

            # Absolute cash flow values
            if free_cash_flow is not None:
                metrics["free_cash_flow"] = float(free_cash_flow)
            else:
                failed_metrics.append("free_cash_flow")

            if operating_cash_flow is not None:
                metrics["operating_cash_flow"] = float(operating_cash_flow)
            else:
                failed_metrics.append("operating_cash_flow")

            # Absolute balance sheet values from sec_valuations
            if total_debt_ev is not None:
                metrics["total_debt"] = float(total_debt_ev)
            else:
                failed_metrics.append("total_debt")

            if total_cash_ev is not None:
                metrics["total_cash"] = float(total_cash_ev)
            else:
                failed_metrics.append("total_cash")

            if ebitda_ev is not None:
                metrics["ebitda"] = float(ebitda_ev)
            else:
                failed_metrics.append("ebitda")

            # Cash per Share = Total Cash / Shares Outstanding
            if total_cash_ev is not None and shares_outstanding is not None and shares_outstanding > 0:
                metrics["cash_per_share"] = float(total_cash_ev / shares_outstanding)
            else:
                failed_metrics.append("cash_per_share")

            # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100
            if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
                try:
                    yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                    metrics["earnings_growth_yoy"] = float(round(yoy_growth, 2))
                except (ValueError, TypeError):
                    failed_metrics.append("earnings_growth_yoy")
            else:
                failed_metrics.append("earnings_growth_yoy")

            # Revenue Growth YoY = (Current Revenue - Prior Year Revenue) / Prior Year Revenue * 100
            if revenue is not None and prior_year_revenue is not None and prior_year_revenue != 0:
                try:
                    yoy_growth = ((revenue - prior_year_revenue) / abs(prior_year_revenue)) * 100
                    metrics["revenue_growth_yoy"] = float(round(yoy_growth, 2))
                except (ValueError, TypeError):
                    failed_metrics.append("revenue_growth_yoy")
            else:
                failed_metrics.append("revenue_growth_yoy")

            # TREND FIELDS (new fields for enhanced scoring)
            # Net Income Growth YoY - only if actual prior net income available
            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:
                try:
                    ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100
                    metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(
                        f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "
                        f"Metric marked data_unavailable."
                    )

            # Operating Income Growth YoY - only if actual prior data available
            if operating_income is not None and prior_year_operating_income is not None and prior_year_operating_income != 0:
                try:
                    oi_growth = ((operating_income - prior_year_operating_income) / abs(prior_year_operating_income)) * 100
                    metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Margin Trends (current - prior year) - only compute when actual prior data available
            if revenue is not None and prior_year_revenue is not None and revenue > 0 and prior_year_revenue > 0:
                # Gross Margin Trend - now can compute with prior-year cost_of_revenue
                if cost_of_revenue is not None and prior_year_cost_of_revenue is not None:
                    curr_gm = ((revenue - cost_of_revenue) / revenue) * 100 if revenue > 0 else None
                    prior_gm = ((prior_year_revenue - prior_year_cost_of_revenue) / prior_year_revenue) * 100 if prior_year_revenue > 0 else None
                    if curr_gm is not None and prior_gm is not None:
                        try:
                            metrics["gross_margin_trend"] = float(round(curr_gm - prior_gm, 2))
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass

                # Operating Margin Trend - only if actual prior operating income available
                if operating_income is not None and prior_year_operating_income is not None and prior_year_revenue > 0:
                    curr_om = (operating_income / revenue) * 100
                    prior_om = (prior_year_operating_income / prior_year_revenue) * 100
                    try:
                        metrics["operating_margin_trend"] = float(round(curr_om - prior_om, 2))
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

                # Net Margin Trend - only if actual prior net income available
                if net_income is not None and prior_year_net_income is not None and prior_year_revenue > 0:
                    curr_nm = (net_income / revenue) * 100
                    prior_nm = (prior_year_net_income / prior_year_revenue) * 100
                    try:
                        metrics["net_margin_trend"] = float(round(curr_nm - prior_nm, 2))
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Sustainable Growth Rate = ROE * Retention Ratio - only with real data
            if stockholders_equity is not None and net_income is not None and stockholders_equity > 0:
                if dividends_paid is not None and net_income != 0:
                    # Actual retention ratio = (earnings - dividends) / earnings
                    roe_pct = (net_income / stockholders_equity)
                    retention_ratio = 1.0 - (dividends_paid / abs(net_income)) if net_income != 0 else 0.0
                    try:
                        metrics["sustainable_growth_rate"] = float(round(roe_pct * retention_ratio * 100, 2))
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # ROE Trend = Current ROE - Prior ROE (now can compute with prior-year equity)
            if (stockholders_equity is not None and net_income is not None and stockholders_equity > 0 and
                prior_year_stockholders_equity is not None and prior_year_net_income is not None and prior_year_stockholders_equity > 0):
                curr_roe = (net_income / stockholders_equity) * 100
                prior_roe = (prior_year_net_income / prior_year_stockholders_equity) * 100
                try:
                    metrics["roe_trend"] = float(round(curr_roe - prior_roe, 2))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # FCF Growth YoY - only if actual prior FCF available
            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:
                try:
                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100
                    metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # OCF Growth YoY - only if actual prior OCF available
            if operating_cash_flow is not None and prior_year_operating_cash_flow is not None and prior_year_operating_cash_flow != 0:
                try:
                    ocf_growth = ((operating_cash_flow - prior_year_operating_cash_flow) / abs(prior_year_operating_cash_flow)) * 100
                    metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Asset Growth YoY - now can compute with prior-year total assets
            if total_assets is not None and prior_year_total_assets is not None and prior_year_total_assets != 0:
                try:
                    asset_growth = ((total_assets - prior_year_total_assets) / abs(prior_year_total_assets)) * 100
                    metrics["asset_growth_yoy"] = float(round(asset_growth, 2))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Initialize missing trend fields as None
            for field in [
                "net_income_growth_yoy", "operating_income_growth_yoy", "gross_margin_trend",
                "operating_margin_trend", "net_margin_trend", "roe_trend", "sustainable_growth_rate",
                "quarterly_growth_momentum", "fcf_growth_yoy", "ocf_growth_yoy", "asset_growth_yoy",
                "earnings_surprise_avg", "eps_growth_stability", "earnings_beat_rate",
                "consecutive_positive_quarters", "estimate_revision_direction", "revision_activity_30d",
                "estimate_momentum_60d", "estimate_momentum_90d", "revision_trend_score", "earnings_growth_4q_avg"
            ]:
                if field not in metrics:
                    metrics[field] = None

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
                "missing_sec_data" if "operating_margin" in failed_metrics else None
            )
            metrics["net_margin_unavailable_reason"] = "missing_sec_data" if "net_margin" in failed_metrics else None
            metrics["debt_to_equity_unavailable_reason"] = (
                "missing_sec_data" if "debt_to_equity" in failed_metrics else None
            )
            metrics["current_ratio_unavailable_reason"] = (
                "missing_sec_data" if "current_ratio" in failed_metrics else None
            )
            metrics["quick_ratio_unavailable_reason"] = "missing_sec_data" if "quick_ratio" in failed_metrics else None
            metrics["interest_coverage_unavailable_reason"] = (
                "missing_sec_data" if "interest_coverage" in failed_metrics else None
            )
            metrics["debt_to_assets_unavailable_reason"] = (
                "missing_sec_data" if "debt_to_assets" in failed_metrics else None
            )
            # Phase 3 Expansion (Session 357+): New metrics - initialize their _unavailable_reason fields
            metrics["gross_margin_unavailable_reason"] = "missing_sec_data" if "gross_margin" in failed_metrics else None
            metrics["ebitda_margin_unavailable_reason"] = "missing_sec_data" if "ebitda_margin" in failed_metrics else None
            metrics["roic_pct_unavailable_reason"] = "missing_sec_data" if "roic_pct" in failed_metrics else None
            metrics["fcf_to_net_income_unavailable_reason"] = (
                "missing_sec_data" if "fcf_to_net_income" in failed_metrics else None
            )
            metrics["ocf_to_net_income_unavailable_reason"] = (
                "missing_sec_data" if "ocf_to_net_income" in failed_metrics else None
            )
            metrics["payout_ratio_unavailable_reason"] = "missing_sec_data" if "payout_ratio" in failed_metrics else None
            metrics["free_cash_flow_unavailable_reason"] = "missing_sec_data" if "free_cash_flow" in failed_metrics else None
            metrics["operating_cash_flow_unavailable_reason"] = (
                "missing_sec_data" if "operating_cash_flow" in failed_metrics else None
            )
            metrics["total_debt_unavailable_reason"] = "missing_sec_data" if "total_debt" in failed_metrics else None
            metrics["total_cash_unavailable_reason"] = "missing_sec_data" if "total_cash" in failed_metrics else None
            metrics["cash_per_share_unavailable_reason"] = "missing_sec_data" if "cash_per_share" in failed_metrics else None
            metrics["ebitda_unavailable_reason"] = "missing_sec_data" if "ebitda" in failed_metrics else None
            metrics["earnings_growth_yoy_unavailable_reason"] = (
                "missing_sec_data" if "earnings_growth_yoy" in failed_metrics else None
            )
            metrics["revenue_growth_yoy_unavailable_reason"] = (
                "missing_sec_data" if "revenue_growth_yoy" in failed_metrics else None
            )
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
        if not income_rows or len(income_rows) < 2:
            return self._unavailable_marker("growth_metrics", symbol)

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "revenue_growth_5y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "eps_growth_5y": None,
            "updated_at": date.today().isoformat(),
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
        self._compute_period_growth(symbol, revenues, 1, "revenue_growth_1y", metrics, failed_metrics)
        self._compute_period_growth(symbol, eps_values, 1, "eps_growth_1y", metrics, failed_metrics)
        self._compute_period_growth(symbol, revenues, 3, "revenue_growth_3y", metrics, failed_metrics)
        self._compute_period_growth(symbol, eps_values, 3, "eps_growth_3y", metrics, failed_metrics)
        self._compute_period_growth(symbol, revenues, 5, "revenue_growth_5y", metrics, failed_metrics)
        self._compute_period_growth(symbol, eps_values, 5, "eps_growth_5y", metrics, failed_metrics)

        if not revenues and not eps_values:
            return self._unavailable_marker("growth_metrics", symbol)

        # Initialize all *_unavailable_reason fields (Session 389)
        metrics["revenue_growth_1y_unavailable_reason"] = (
            "insufficient_history" if "revenue_growth_1y" in failed_metrics else None
        )
        metrics["revenue_growth_3y_unavailable_reason"] = (
            "insufficient_history" if "revenue_growth_3y" in failed_metrics else None
        )
        metrics["revenue_growth_5y_unavailable_reason"] = (
            "insufficient_history" if "revenue_growth_5y" in failed_metrics else None
        )
        metrics["eps_growth_1y_unavailable_reason"] = (
            "insufficient_history" if "eps_growth_1y" in failed_metrics else None
        )
        metrics["eps_growth_3y_unavailable_reason"] = (
            "insufficient_history" if "eps_growth_3y" in failed_metrics else None
        )
        metrics["eps_growth_5y_unavailable_reason"] = (
            "insufficient_history" if "eps_growth_5y" in failed_metrics else None
        )

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
            "net_income_growth_yoy", "operating_income_growth_yoy", "gross_margin_trend",
            "operating_margin_trend", "net_margin_trend", "roe_trend", "sustainable_growth_rate",
            "quarterly_growth_momentum", "fcf_growth_yoy", "ocf_growth_yoy", "asset_growth_yoy",
        ]:
            if field not in metrics:
                metrics[field] = None

        return metrics

    def _insert_value_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert value_metrics row."""
        cur.execute(
            """
            INSERT INTO value_metrics
            (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, forward_pe, enterprise_value, ev_ebitda, ev_revenue, value_score, data_unavailable, data_source, updated_at,
             pe_ratio_unavailable_reason, pb_ratio_unavailable_reason, ps_ratio_unavailable_reason, peg_ratio_unavailable_reason,
             dividend_yield_unavailable_reason, fcf_yield_unavailable_reason, forward_pe_unavailable_reason, ev_ebitda_unavailable_reason, ev_revenue_unavailable_reason,
             market_cap_unavailable_reason, held_percent_insiders_unavailable_reason, held_percent_institutions_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                data_unavailable = EXCLUDED.data_unavailable,
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
                row.get("value_score"),
                row["data_unavailable"],
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
             estimate_revision_direction, revision_activity_30d, estimate_momentum_60d, estimate_momentum_90d,
             revision_trend_score, earnings_growth_4q_avg,
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
             fcf_growth_yoy_unavailable_reason, ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                estimate_revision_direction = EXCLUDED.estimate_revision_direction,
                revision_activity_30d = EXCLUDED.revision_activity_30d,
                estimate_momentum_60d = EXCLUDED.estimate_momentum_60d,
                estimate_momentum_90d = EXCLUDED.estimate_momentum_90d,
                revision_trend_score = EXCLUDED.revision_trend_score,
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
                row.get("estimate_revision_direction"),
                row.get("revision_activity_30d"),
                row.get("estimate_momentum_60d"),
                row.get("estimate_momentum_90d"),
                row.get("revision_trend_score"),
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
                None,  # net_income_growth_yoy_unavailable_reason
                None,  # operating_income_growth_yoy_unavailable_reason
                None,  # gross_margin_trend_unavailable_reason
                None,  # operating_margin_trend_unavailable_reason
                None,  # net_margin_trend_unavailable_reason
                None,  # roe_trend_unavailable_reason
                None,  # sustainable_growth_rate_unavailable_reason
                None,  # quarterly_growth_momentum_unavailable_reason
                None,  # fcf_growth_yoy_unavailable_reason
                None,  # ocf_growth_yoy_unavailable_reason
                None,  # asset_growth_yoy_unavailable_reason
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
             data_unavailable, reason, data_source, updated_at,
             revenue_growth_1y_unavailable_reason, revenue_growth_3y_unavailable_reason, revenue_growth_5y_unavailable_reason,
             eps_growth_1y_unavailable_reason, eps_growth_3y_unavailable_reason, eps_growth_5y_unavailable_reason,
             net_income_growth_yoy_unavailable_reason, operating_income_growth_yoy_unavailable_reason, gross_margin_trend_unavailable_reason,
             operating_margin_trend_unavailable_reason, net_margin_trend_unavailable_reason, roe_trend_unavailable_reason,
             sustainable_growth_rate_unavailable_reason, quarterly_growth_momentum_unavailable_reason, fcf_growth_yoy_unavailable_reason,
             ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            ),
        )

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
                "ev_ebitda_unavailable_reason": "depreciation_amortization_not_loaded",
                "market_cap_unavailable_reason": None,
                "held_percent_insiders_unavailable_reason": None,
                "held_percent_institutions_unavailable_reason": None,
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient SEC valuation data",
                "updated_at": date.today().isoformat(),
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
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient SEC financial data",
                "updated_at": date.today().isoformat(),
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
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient historical data",
                "updated_at": date.today().isoformat(),
            }


if __name__ == "__main__":
    sys.exit(run_loader(ValueQualityGrowthMetricsLoader, description="Consolidated value + quality + growth metrics"))
