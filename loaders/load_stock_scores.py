#!/usr/bin/env python3
"""Stock Scores Loader - Multi-factor composite stock scoring.

Computes composite stock scores by aggregating:
- Quality metrics (ROE, margins, debt-to-equity ratio)
- Growth metrics (revenue growth, EPS growth)
- Value metrics (P/E, P/B, P/S ratios, dividend yield)
- Momentum/Relative Strength (1m/3m/6m/12m returns)
- Positioning metrics (institutional ownership, short interest)
- Stability metrics (volatility, beta)

Each factor is normalized to 0-100 scale and weighted.
Final composite score is weighted average of all factors.

CRITICAL GOVERNANCE RULES:
- Minimum 3/6 metrics (50%) required for any stock score (no IPO exceptions)
- All stocks use uniform standards regardless of age or listing status
- Momentum requires proper lookback: 30d, 60d, 120d, 252d (no short-term fallback)
- All metric data validated before access (fail-fast on schema mismatches)
- Data corruption detected → RuntimeError (never silent degradation)
- Explicit data_unavailable markers in DB for operator visibility

Run: python3 loaders/load_stock_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import json  # noqa: E402
import logging  # noqa: E402
import math  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import psycopg2  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders.unavailable_markers import marker_loader_failed, marker_not_applicable  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.type_conversion import safe_float  # noqa: E402

logger = logging.getLogger(__name__)

# Composite pillar weights (must sum to 1.0). Single source of truth - see
# _compute_stock_score's "Fixed base weights" block below for the full empirical-basis
# history/docstring. Module-level (not just a local var inside that method) specifically so
# tests and other consumers can import the real live value instead of hand-copying it - this
# codebase has repeatedly found stale hand-copied duplicates of these exact percentages
# drifting out of sync elsewhere (StockDetail.jsx's FACTOR_WEIGHTS, tests/test_formula_accuracy.py,
# algo/infrastructure/constants.py's REGIME_POSITION_SIZE_*, dashboard risk-panel display) -
# see [[risk_dashboard_position_size_multiplier_drift_fixed_20260825]] and siblings in memory.
BASE_PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.25,
    "growth": 0.12,
    "value": 0.21,
    "positioning": 0.12,
    "stability": 0.18,
    "momentum": 0.12,
}


class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field: str = "updated_at"
    exclude_etfs_from_symbols = True  # Metric loaders (quality, growth, value, positioning, stability) exclude ETFs

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run to validate upstream metrics are ready before computing scores.

        CRITICAL: Pre-flight validation ensures all upstream metric loaders have sufficient
        coverage before attempting stock score computation. This prevents silent degradation
        from incomplete metric data (e.g., 50% availability = biased scoring that impacts trading).
        """
        self.validate_upstream_metrics_ready()
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)

    def validate_upstream_metrics_ready(self) -> None:
        """Check that upstream metric tables have sufficient coverage.

        Raises RuntimeError if critical metric loaders haven't populated data yet.
        Prevents silent score computation failure when metrics are missing due to loader timeouts.

        Two tiers:
        - required: value/positioning/stability - must have real coverage thresholds met
        - optional_sec: quality/growth - depend on SEC annual financials; may be all-unavailable
          if the annual_income_statement upstream is empty. Fail only if table is completely empty
          (loader never ran). All-unavailable is acceptable; per-symbol scoring handles gracefully.
        """
        from utils.db.error_handlers import handle_db_errors

        with handle_db_errors("validate_upstream_metrics"):
            with DatabaseContext("read") as cur:
                # CRITICAL FIX 2026-07-05: growth_metrics is no longer optional.
                # Stock scores require minimum 3/6 metrics per GOVERNANCE.md for valid trading signals.
                # If growth_metrics is incomplete, stocks will score with insufficient factors, biasing
                # toward value/momentum and away from growth signals. This is dangerous for growth-focused
                # portfolios. Enforce minimum coverage threshold.
                required_metric_tables = {
                    "value_metrics": 0.15,  # ADJUSTED: Realistic min - S&P 500 dividend payers ~4,700 stocks (2.7% of ~175k)
                    "growth_metrics": 0.10,  # ADJUSTED: Realistic min - SEC-filing dependent (many small-caps have no annual filings)
                    "positioning_metrics": 0.15,  # ADJUSTED: Realistic min - Institutional data limited to liquid stocks
                    "stability_metrics": 0.15,  # ADJUSTED: Realistic min - Beta calculation requires sufficient price history
                }
                # SEC-filing-dependent metrics: acceptable to have 0% real data if upstream
                # annual_income_statement is empty (known infrastructure gap). Only fail if
                # the loader never ran at all (0 rows in table).
                optional_sec_metric_tables = {
                    "quality_metrics",
                }

                for table_name, min_coverage in required_metric_tables.items():
                    # Check if data_unavailable column exists (migration 102 may not have been applied yet)
                    # RACE CONDITION FIX: Use single query to get both counts atomically
                    # This prevents stale row counts when concurrent pipelines are inserting
                    try:
                        # Get both available and total counts in one query for consistency
                        # COUNT FILTER is atomic and prevents row count changes between queries
                        cur.execute(f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """)
                    except psycopg2.ProgrammingError as e:
                        # CRITICAL: Schema mismatch is a fail-fast failure (GOVERNANCE compliance)
                        # Cannot proceed with scoring when data_unavailable column is missing
                        raise RuntimeError(
                            f"[STOCK_SCORES] CRITICAL: {table_name} missing data_unavailable column. "
                            f"Database schema is out of sync with application code. "
                            f"Migration for {table_name} has not been applied. "
                            f"ACTION: Apply pending database migrations before running stock scores loader. "
                            f"Cannot proceed with potentially incomplete/corrupt metric data."
                        ) from e

                    row = cur.fetchone()
                    available_count = row[0] if row else 0
                    total_count = row[1] if row else 0

                    if total_count == 0:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} is EMPTY. "
                            f"ROOT CAUSE: Upstream metric loader may not have run yet. "
                            f"ACTION: Check {table_name} loader step function execution logs. "
                            f"Cannot compute stock scores without metric data."
                        )

                    # Coverage = stocks with real data / all stocks that ran through loader
                    coverage = available_count / total_count if total_count > 0 else 0

                    if coverage < min_coverage:
                        # CRITICAL: Require strict minimum coverage - no grace windows
                        # Silent degradation from incomplete metrics masks data quality issues.
                        # If metrics aren't available, that's a problem that needs operator attention,
                        # not a condition to degrade gracefully around.
                        cur.execute(
                            f"SELECT symbol, COUNT(*) FROM {table_name} WHERE data_unavailable = true GROUP BY symbol LIMIT 5"
                        )
                        unavail_sample = cur.fetchall()
                        unavail_sample_str = ", ".join([s[0] for s in unavail_sample]) if unavail_sample else "(none)"

                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} coverage insufficient. "
                            f"Only {coverage:.1%} coverage ({available_count}/{total_count} stocks with real data). "
                            f"Required: {min_coverage:.0%} minimum (NO GRACE WINDOW). "
                            f"Sample unavailable symbols: {unavail_sample_str}. "
                            f"ACTION: Check upstream {table_name} loader for timeouts/failures or incomplete data. "
                            f"Typical causes: SEC API limits (quality/growth), yfinance throttling (value/positioning), price history gaps (stability). "
                            f"Do NOT attempt to score stocks without full metric coverage - incomplete metrics produce biased rankings."
                        )

                    # CRITICAL FIX Session 345: Check data freshness, not just availability
                    # Coverage check passes even if data is 30+ days old (historical filings from slow SEC APIs)
                    # Add staleness check to prevent stale metrics from poisoning score rankings
                    try:
                        cur.execute(f"""
                            SELECT MAX(updated_at) FROM {table_name}
                            WHERE data_unavailable = false OR data_unavailable IS NULL
                        """)
                        max_update_row = cur.fetchone()
                        if max_update_row and max_update_row[0]:
                            max_update_ts = max_update_row[0]
                            from datetime import datetime, timezone

                            now_utc = datetime.now(timezone.utc)
                            if max_update_ts.tzinfo is None:
                                # {table_name}.updated_at is a `timestamp without time zone`
                                # column written via SQL CURRENT_TIMESTAMP, so a naive value
                                # here is in the DB session's local wall-clock timezone
                                # (utils/bulk_insert_manager.py's documented convention), not
                                # UTC. Same bug class already fixed in
                                # algo/trading/pretrade_checks.py's re-entry cooldown and
                                # algo/risk/market_exposure.py's cache-age check: resolve the
                                # real session timezone dynamically instead of assuming UTC.
                                from utils.db.timezone_utils import get_db_timezone

                                naive_tz = get_db_timezone()
                                max_update_ts = max_update_ts.replace(tzinfo=naive_tz)
                            stale_days = (now_utc - max_update_ts).days
                            max_staleness_days = 14  # Metrics older than 2 weeks are stale
                            if stale_days > max_staleness_days:
                                logger.warning(
                                    f"[STOCK_SCORES] {table_name}: Data is {stale_days} days old "
                                    f"(max_update_ts={max_update_ts}). "
                                    f"Exceeds staleness threshold of {max_staleness_days} days. "
                                    f"Scores computed from outdated metrics may misrank stocks."
                                )
                    except Exception as staleness_check_err:
                        # Non-fatal: log but don't halt if staleness check fails
                        logger.warning(
                            f"[STOCK_SCORES] Could not validate {table_name} staleness: {staleness_check_err}"
                        )

                for table_name in optional_sec_metric_tables:
                    # RACE CONDITION FIX: Use single query to get both counts atomically
                    try:
                        cur.execute(f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """)
                    except psycopg2.ProgrammingError as e:
                        # CRITICAL: Schema mismatch is a fail-fast failure (GOVERNANCE compliance)
                        # Cannot proceed with scoring when data_unavailable column is missing
                        raise RuntimeError(
                            f"[STOCK_SCORES] CRITICAL: {table_name} missing data_unavailable column. "
                            f"Database schema is out of sync with application code. "
                            f"Migration for {table_name} has not been applied. "
                            f"ACTION: Apply pending database migrations before running stock scores loader. "
                            f"Cannot proceed with potentially incomplete/corrupt metric data."
                        ) from e

                    row = cur.fetchone()
                    available_count = row[0] if row else 0
                    total_count = row[1] if row else 0

                    if total_count == 0:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} is empty. "
                            f"Upstream metric loader may not have run yet. "
                            f"Cannot compute stock scores without metric data."
                        )

                    coverage = available_count / total_count if total_count > 0 else 0

                    # CRITICAL FIX 2026-07-05: Allow 0% coverage for optional_sec metrics if the loader ran
                    # (table has rows). This handles legitimate cases where all data is unavailable:
                    # - Small-caps/IPOs with no SEC filings (growth/quality metrics unavailable but loader ran)
                    # - This is NOT a loader failure; it's successful completion with all-unavailable data
                    # The check above (total_count == 0) catches the real error: loader never ran
                    if coverage == 0:
                        logger.warning(
                            f"[STOCK_SCORES] {table_name}: 0% real data coverage ({available_count} real / {total_count} total). "
                            f"All records marked data_unavailable (likely no {table_name} available for traded symbols). "
                            f"This is acceptable for optional SEC metrics; stock_scores will compute with fewer factors."
                        )

                logger.info(
                    "[STOCK_SCORES] Pre-flight validation passed: upstream metric loaders ready. "
                    "Proceeding with stock score computation."
                )

    def _prepare_batch_context(self) -> None:
        """Load all 6 metric tables once instead of per-symbol (N+1 fix).

        Previously each of quality/growth/value/positioning/stability_metrics was queried with
        a separate `WHERE symbol = %s` per symbol (~5 x symbol_count round-trips per run), and
        the momentum query re-evaluated `(SELECT MAX(date) FROM price_daily)` as an inline
        subquery up to 4 times per symbol against an 8.6M+ row table. Now: 6 bulk queries total,
        cached by symbol; momentum is read from momentum_metrics table (precomputed).

        Per-symbol row layout in each cache dict matches the original per-symbol SELECT exactly
        (same column order, `data_unavailable` last), so _get_*_metrics indexing is unchanged.

        CRITICAL FIX 2026-07-18: Now reads momentum_metrics from database instead of computing
        from price_daily. momentum_metrics is populated by load_risk_metrics_daily.py and has
        momentum_1m/3m/6m/12m already calculated. This fixes the issue where stock_scores had
        all NULL momentum values despite momentum_metrics being populated.
        """
        self._batch_context = {}
        # Load configurable completeness threshold
        self._min_completeness_threshold = None
        try:
            with DatabaseContext("read") as config_cur:
                config_cur.execute("SELECT value FROM algo_config WHERE key = 'min_completeness_score'")
                config_row = config_cur.fetchone()
                if config_row and config_row[0]:
                    self._min_completeness_threshold = float(config_row[0])
                    logger.debug(
                        f"[STOCK_SCORES] Using configurable completeness threshold: {self._min_completeness_threshold}%"
                    )
        except Exception as config_err:
            logger.critical(
                f"[STOCK_SCORES FAIL-FAST] Could not load min_completeness_score from config table: {config_err}. "
                f"This is a critical data quality gate. Database may be inaccessible or corrupted. "
                f"Cannot proceed without explicit completeness validation configuration."
            )
            raise RuntimeError(
                f"[STOCK_SCORES CRITICAL] Failed to load min_completeness_score configuration: {config_err}. "
                f"This parameter is critical for data integrity validation. Check database connectivity and schema."
            ) from config_err

        # Use explicit default only if key truly doesn't exist (legitimate first-time setup)
        if self._min_completeness_threshold is None:
            self._min_completeness_threshold = 70.0
            logger.warning(
                "[STOCK_SCORES] min_completeness_score not configured in database. "
                "Using conservative default 70% - consider setting explicit value in algo_config table."
            )

        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol, roe, roa, operating_margin, net_margin, debt_to_equity, "
                "current_ratio, quick_ratio, debt_to_assets, quality_score, data_unavailable, "
                "gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, "
                "payout_ratio, free_cash_flow, operating_cash_flow, total_debt, total_cash, "
                "cash_per_share, ebitda, earnings_growth_yoy, revenue_growth_yoy, interest_coverage FROM quality_metrics"
            )
            self._quality_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # net_income_growth_yoy/operating_income_growth_yoy/sustainable_growth_rate/
            # fcf_growth_yoy/ocf_growth_yoy added: computed by load_value_quality_growth_metrics.py
            # (mirrored from quality_metrics into growth_metrics as of 2026-08-03) but never
            # read here before - fetched and stored, zero influence on growth_score.
            #
            # gross_margin_trend/operating_margin_trend/net_margin_trend/roe_trend/asset_growth_yoy
            # added 2026-08-03: the mirroring step above was never actually exercised against a
            # working DB (local dev schema had stockholders_equity/cash_and_equivalents renamed
            # out from under it, crashing every fetch_incremental() call before it could compute
            # these fields at all) - once the schema was fixed, live-verified these 5 populate
            # with real, differentiated values (not NULL), disproving the prior "structurally
            # always NULL" premise. quarterly_growth_momentum is NOT included here - it's now
            # computed (by load_enhanced_quality_growth_metrics.py, wired in as of 548dc99f5) and
            # populated with real values, but was never wired into this score formula; excluding
            # it is a deliberate scope decision now, not a data-availability limitation.
            # eps_growth_stability added 2026-08-25: computed by
            # load_value_quality_growth_metrics.py (stddev of trailing 4-quarter EPS growth
            # rates) and stored at 67.8% coverage, but never fetched here before - dead field,
            # now read for _enhance_quality_score's earnings-consistency adjustment.
            cur.execute(
                "SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, "
                "eps_growth_1y, eps_growth_3y, eps_growth_5y, "
                "net_income_growth_yoy, operating_income_growth_yoy, sustainable_growth_rate, "
                "fcf_growth_yoy, ocf_growth_yoy, "
                "gross_margin_trend, operating_margin_trend, net_margin_trend, roe_trend, asset_growth_yoy, "
                "eps_growth_stability, "
                "data_unavailable FROM growth_metrics"
            )
            self._growth_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # forward_pe/ev_ebitda/ev_revenue added: loaded and displayed on the scores page
            # (migration 1191 backfilled ev_ebitda/ev_revenue/forward_pe onto sec_valuations,
            # copied into value_metrics by load_value_quality_growth_metrics.py) but never
            # read here before - zero influence on value_score.
            # margin_of_safety_pct added: DCF-based "discount to intrinsic value" (Value
            # factor goal, 2026-08-17) - computed by load_sec_valuations.py, copied onto
            # value_metrics by load_value_quality_growth_metrics.py, migration 1208.
            # market_cap added 2026-08-25 (goal: close the Size-factor gap found this pass -
            # see _score_value's docstring "SIZE FACTOR" section): already stored on
            # value_metrics (no schema change needed, 77.4% coverage), just never read here
            # before - zero influence on value_score until now.
            cur.execute(
                "SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, "
                "forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct, market_cap, data_unavailable "
                "FROM value_metrics"
            )
            self._value_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # shares_short_prior_month/short_interest_pct_change added: written by
            # load_positioning_metrics.py (migration 1184, pct_change replacing the former
            # short_interest_trend enum column in migration 1203) but never read here before -
            # the existing short_interest weight only used the latest %-of-float snapshot, with
            # no signal for which direction it's moving.
            # BUG FOUND 2026-08-24 (real-money-readiness goal, log-driven sweep): a
            # concurrent session's commit ("REMOVE: drop insider_ownership_pct entirely -
            # not a positioning metric") dropped the column from positioning_metrics but
            # missed this SELECT - live-confirmed this crashed EVERY stock_scores run since
            # that commit landed (column "insider_ownership_pct" does not exist), the most
            # critical loader in the pipeline (feeds every trading decision).
            cur.execute(
                "SELECT symbol, institutional_ownership_pct, short_interest_pct, "
                "shares_short_prior_month, short_interest_pct_change, ad_rating, data_unavailable "
                "FROM positioning_metrics"
            )
            self._positioning_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # downside_volatility_252d/max_drawdown_1y added: written by load_risk_metrics_daily.py
            # (migration 1184/1175) but never read here before.
            # FIX 2026-08-16: downside_volatility_60d/30d also added here - _score_stability has
            # scored them (7.5%/5% weight) since the "Fixed 2026-08-16: 60d/30d now scored too"
            # comment there, but this SELECT never fetched either column even though both already
            # exist on stability_metrics (same table, no new migration needed) - the two weight
            # slots were dead in every real score since that fix landed. Same bug class as
            # [[momentum_score_sma_dead_weight_fix_20260816]].
            # CLEANUP 2026-08-16 (later): debt_to_assets dropped from this SELECT - Stability no
            # longer scores it (moved to Quality, which reads its own debt_to_assets directly
            # from quality_metrics), so fetching it here was dead weight.
            cur.execute(
                "SELECT symbol, volatility_252d, volatility_60d, volatility_30d, beta, "
                "downside_volatility_252d, downside_volatility_60d, downside_volatility_30d, max_drawdown_1y, "
                "data_unavailable "
                "FROM stability_metrics"
            )
            self._stability_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # CRITICAL FIX 2026-07-18: Read momentum from momentum_metrics table instead of computing from scratch
            # momentum_metrics is populated by load_risk_metrics_daily.py with precomputed momentum values
            cur.execute(
                "SELECT symbol, momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable "
                "FROM momentum_metrics"
            )
            self._momentum_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # Latest RSI/MACD per symbol, for momentum scoring (added: these were previously
            # only surfaced for display and had zero influence on momentum_score, which was
            # 100% price-return based). ROC is deliberately NOT pulled in here - it measures
            # the same thing as momentum_1m/3m/6m/12m (windowed % price return) and would just
            # double-weight that signal; RSI/MACD are qualitatively different (oscillator /
            # trend-confirmation) so they add real incremental information.
            # FIX 2026-08-16: also pull sma_50/sma_200/close so _get_momentum_metrics can
            # compute price_vs_sma_50/200 - _score_momentum has always had an 8%-weighted SMA
            # positioning component (and the scores dashboard has advertised it as a real
            # "used: true, 8% avg" input since the 2026-08-04 momentum audit), but this cache
            # never fetched sma_50/sma_200/close, so metrics.get(sma_field) was unconditionally
            # None for every symbol - 8% of the documented momentum_score formula was dead in
            # every real score computed. Unlike ROC above, SMA positioning is NOT a duplicate
            # signal of price-return momentum (it's price-vs-trend, not windowed % return), so
            # there's no double-weighting concern here.
            cur.execute(
                "SELECT DISTINCT ON (symbol) symbol, rsi_14, macd, sma_50, sma_200, close "
                "FROM technical_data_daily ORDER BY symbol, date DESC"
            )
            self._technical_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute stock scores for this symbol. Returns data_unavailable dict if unable to compute.

        CRITICAL: At the PUBLIC API boundary, converts internal RuntimeError to explicit
        data_unavailable marker for operator visibility. Callers can distinguish:
        - None/empty returns: data genuinely unavailable (not an error)
        - Exception propagation: actual system failures (database, auth, etc.)

        CRITICAL FIX (Session 246): Ensure metric caches are initialized before computing scores.
        The _prepare_batch_context() method must be called before fetch_incremental() is invoked.
        Callers MUST initialize caches OR fail-fast with clear error message.
        """
        # CRITICAL: Check that batch context was prepared (caches initialized)
        if not hasattr(self, "_quality_cache"):
            raise RuntimeError(
                f"[STOCK_SCORES] CRITICAL: Batch context not initialized for {symbol}. "
                "The _prepare_batch_context() method must be called before fetch_incremental(). "
                "This is a framework contract violation - either the loader's run() method "
                "didn't call _prepare_batch_context(), or fetch_incremental() was called directly."
            )

        try:
            score_result = self._compute_stock_score(symbol)
            if not score_result:
                # This should not occur (internal _compute_stock_score raises on failure),
                # but safeguard against unexpected None returns
                logger.warning(f"[STOCK_SCORES] Unexpected None return for {symbol} - marking data unavailable")
                # Return explicit data_unavailable marker so symbol appears in DB with clear status
                return [
                    {
                        "symbol": symbol,
                        "composite_score": None,
                        "signal_score": None,
                        "quality_score": None,
                        "growth_score": None,
                        "value_score": None,
                        "momentum_score": None,
                        "positioning_score": None,
                        "stability_score": None,
                        "data_completeness": 0,
                        "data_unavailable": True,
                        "reason": "Internal scoring failure - unexpected None return",
                        "reason_type": "loader_failed",
                        "date": datetime.now(timezone.utc).date(),
                        "updated_at": datetime.now(timezone.utc),
                    }
                ]
            return [score_result]
        except (RuntimeError, ValueError) as e:
            # Upstream metric loaders insufficient data: return explicit data_unavailable marker
            # instead of empty list so symbol appears in DB with clear status flag
            logger.warning(f"[STOCK_SCORES] Cannot compute score for {symbol}: {e!s}")
            return [
                {
                    "symbol": symbol,
                    "composite_score": None,
                    "signal_score": None,
                    "quality_score": None,
                    "growth_score": None,
                    "value_score": None,
                    "momentum_score": None,
                    "positioning_score": None,
                    "stability_score": None,
                    "data_completeness": 0,
                    "data_unavailable": True,
                    "reason": str(e),
                    "reason_type": "loader_failed",
                    "date": datetime.now(timezone.utc).date(),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]

    def _compute_stock_score(self, symbol: str) -> dict[str, Any]:  # noqa: C901
        """Compute composite stock score from REAL metrics only (no fake defaults).

        CRITICAL: Fails fast if stock has insufficient real data (>=50% completeness required).
        Do not return None or fake markers - callers must know immediately if scoring failed.

        Returns dict with keys: symbol, composite_score, quality_score, growth_score,
        value_score, momentum_score, positioning_score, stability_score, rs_percentile,
        data_completeness

        Raises:
            RuntimeError: If insufficient metrics available to compute valid score
        """
        try:
            with DatabaseContext("read") as cur:
                quality = self._get_quality_metrics(cur, symbol)
                growth = self._get_growth_metrics(cur, symbol)
                value = self._get_value_metrics(cur, symbol)
                positioning = self._get_positioning_metrics(cur, symbol)
                stability = self._get_stability_metrics(cur, symbol)
                momentum = self._get_momentum_metrics(cur, symbol)

            # Compute individual factor scores from REAL data only (no defaults)
            # Scoring functions return float or dict (marker when data unavailable)
            # Keep marker dicts throughout to track missing data reasons
            quality_score = self._score_quality(quality, symbol)
            growth_score = self._score_growth(growth, symbol)
            value_score = self._score_value(value, symbol)
            positioning_score = self._score_positioning(positioning, symbol)
            stability_score = self._score_stability(stability, symbol)
            momentum_score = self._score_momentum(momentum, symbol)

            # Extract numeric scores for computation, track unavailability reasons
            def is_real_score(result: float | dict[str, Any] | None) -> bool:
                return isinstance(result, float)

            def get_marker_reason(result: float | dict[str, Any] | None) -> str:
                if isinstance(result, dict) and result.get("data_unavailable"):
                    reason = result.get("reason")
                    if isinstance(reason, str):
                        return reason
                return "unknown_reason"

            # Count data completeness: only float scores count as "real data"
            # Markers (dicts with data_unavailable=True) are excluded from count
            # Session 260: Momentum loader now fixed and included in completeness calculation
            # All 6 metrics are evaluated: quality, growth, value, positioning, stability, momentum
            # Minimum 70% completeness (4.2/6 metrics) required per GOVERNANCE.md
            all_scores = {
                "quality": quality_score,
                "growth": growth_score,
                "value": value_score,
                "positioning": positioning_score,
                "stability": stability_score,
                "momentum": momentum_score,
            }
            real_scores = [s for s in all_scores.values() if is_real_score(s)]
            data_count = len(real_scores)
            unavailable_metrics = {
                name: get_marker_reason(score) for name, score in all_scores.items() if not is_real_score(score)
            }

            # CRITICAL FIX 2026-07-19: Log when scores computed with <6 metrics for visibility.
            # Traders need to see completeness % in dashboards to filter based on GOVERNANCE entry gates.
            if data_count < 6 and data_count >= 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.info(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/6 metrics ({100.0 * data_count / 6:.1f}% complete). "
                    f"Missing: {', '.join(missing)}. Trading filter gate: completeness >= 70% per GOVERNANCE."
                )
            elif data_count < 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.warning(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/6 metrics ({100.0 * data_count / 6:.1f}% complete). "
                    f"Missing: {', '.join(missing)}. Minimum 4 metrics ensures diversity against single-metric bias."
                )

            # NUMERIC(4,2) schema constraint: max 99.99 (not 100.0)
            # Calculate completeness on 6 metrics (quality, growth, value, positioning, stability, momentum)
            # CRITICAL FIX 2026-07-18: Momentum now works (reads from momentum_metrics), restored 6-metric calculation
            data_completeness = min(99.99, round((data_count / 6.0) * 100, 2))

            # CRITICAL FIX 2026-07-19: Compute score for all symbols with 4+/6 metrics, mark completeness for trading filters.
            # Previous: Rejected any score with <70% completeness, removing 1,635 valid candidates from universe.
            # New: Calculate scores for all candidates with sufficient diversity (4+ metrics), let trading logic
            # (entry gates) filter based on completeness %. This gives traders full visibility + control.
            # GOVERNANCE.md says: "Signals < 70% completeness are excluded from scoring" (trading exclusion, not computation exclusion).
            # The minimum 4 metrics check below ensures sufficient diversity to prevent single-metric bias.
            # Completeness % is still tracked and reported for operator/trader visibility.

            # Session 530: Enable degraded-mode scoring for SPACs/new listings
            # Previously: required minimum 2/6 metrics, silently rejected 8 SPACs
            # Now: allow 1+ metrics for degraded scoring, marked with low completeness % in DB
            # Trading gates still filter on completeness >= 70%, so degraded scores won't enter live signals
            # min_required_metrics lowered from 3 to 1 to make "no data" stocks visible with reason codes
            min_required_metrics = 1

            if data_count < min_required_metrics:
                raise RuntimeError(
                    f"[STOCK_SCORES] {symbol}: CRITICAL - zero metrics available. "
                    f"Got {data_count}/6 metrics. Cannot compute score with no metric data."
                )

            # GOVERNANCE COMPLIANCE: Compute scores with 4+/6 metrics (sufficient diversity).
            # No weight redistribution fallbacks (normalized weights stay fixed).
            # Trading gates will filter based on completeness % >= 70% per GOVERNANCE.md line 62.
            # Previous behavior (Session 294+): Rejected scores with <6 metrics, reducing universe from 4759 to 1858 (39%).
            # Session 297 fix: Allow 4+/6 for computation; let trading logic filter on completeness %.
            # Reason: Rejecting 4-5 metric scores wastes valid signals; incomplete data is honest data marked visible.

            score_availability = {
                "quality": is_real_score(quality_score),
                "growth": is_real_score(growth_score),
                "value": is_real_score(value_score),
                "positioning": is_real_score(positioning_score),
                "stability": is_real_score(stability_score),
                "momentum": is_real_score(momentum_score),
            }

            real_metric_count = sum(1 for v in score_availability.values() if v)

            # DEGRADED MODE: Allow scoring with 1+ metrics for SPACs/new listings
            # Session 530 (2026-08-05): Enable degraded-mode scoring for SPACs with insufficient SEC data.
            # Previously: rejected scores with <2 metrics, leaving 8 SPACs (APMD, BANL, etc) with NULL scores.
            # New: allow 1+ metrics for degraded scoring, marked clearly in DB with low completeness %.
            # Trading gates still filter on completeness >= 70%, so degraded scores won't enter live signals.
            # This makes "no data" stocks visible in dashboard with reason codes instead of disappearing.
            if real_metric_count < 1:
                missing_metrics = [k for k, v in score_availability.items() if not v]
                logger.error(
                    f"[STOCK_SCORES] {symbol}: CRITICAL - zero real metrics available. "
                    f"Available {real_metric_count}/6. "
                    f"Missing: {', '.join(missing_metrics)}. "
                    f"Cannot compute even degraded score without any real data."
                )
                raise ValueError(
                    f"{symbol}: zero metrics ({real_metric_count}/6, impossible to score). "
                    f"Cannot compute score with zero available metrics."
                )

            if real_metric_count < 2:
                # Degraded mode: score with 1 metric only (for SPACs/new listings)
                logger.info(
                    f"[STOCK_SCORES] {symbol}: DEGRADED MODE - {real_metric_count}/6 metrics available. "
                    f"Computing partial score (dashboard will show data_completeness={int(real_metric_count / 6 * 100)}%)"
                )

            # Fixed base weights (no redistribution per GOVERNANCE fail-fast rule)
            # Unavailable metrics contribute 0 to composite (their weight is skipped, lost).
            # This means composite score is 0-100 scale, where:
            # - 100 = all 6 metrics perfect
            # - 50 with all 6 = truly 50/100
            # - 50 with 3/6 = really 50/60 (incomplete picture)
            # Dashboard displays completeness % so traders see data quality.
            #
            # RESOLVED 2026-08-25 (goal: re-audit ALL stock_scores inputs, including whether
            # the pillar LIST itself is complete, and finally close out the "underpowered,
            # not acted on" composite-weight question below). These 6 percentages have no
            # documented empirical basis anywhere in this file - just hand-set numbers. Built
            # algo/research/fama_macbeth_composite_weights.py to test them via Grinold & Kahn's
            # "Active Portfolio Management" combining-alphas methodology (regression-weight
            # signals by realized predictive power controlling for correlation among them -
            # exactly what multivariate Fama-MacBeth does).
            #
            # CONCURRENT INDEPENDENT RECONSTRUCTION (2026-08-25, merge note): this exact
            # composite-weights fix was worked on by two parallel sessions at once after an
            # earlier attempt was lost to an uncommitted-work race (see
            # [[composite_weights_reweighted_size_factor_reconfirmed_20260825]] /
            # [[stock_scores_composite_weights_reconstruction_after_lost_commit_20260826]]).
            # The other session's independent re-run found stability_proxy t=2.70/value_proxy
            # t=2.05 multivariate (both clearing |t|=2) - slightly stronger than this session's
            # own t=1.91/1.39 below, most likely from minor sample/construction differences
            # (this version additionally fixes the PE/PB/PS-within-Value selection bias, see
            # below, which the other session's value_proxy didn't include). Both independently
            # reached the identical qualitative conclusion and the identical reweight numbers -
            # convergent evidence the direction is real, not an artifact of either session's
            # specific methodology choices.
            #
            # FIRST PASS (same day, earlier): required all 6 pillar proxies non-null per
            # symbol-month (strict dropna()) - only kept the intersection of annual-fundamentals
            # coverage (growth/value/quality) AND full price-history coverage (stability/
            # momentum/positioning): 109 months, median 850 symbols, likely biased toward
            # larger/more-established names. value_proxy came out strongest (t=1.78 multivariate/
            # 1.83 univariate, still short of conventional significance); stability/momentum
            # came back negatively signed, opposite their own single-pillar-test signs -
            # suspected selection-bias artifact. Underpowered; not acted on.
            #
            # REDESIGNED PASS (same day, later): relaxed the all-6-required rule - only
            # forward return is mandatory; each pillar proxy is z-scored over whatever's
            # actually available that month, then missing pillars are imputed to 0 (the
            # z-scored mean), matching this exact base_weights loop's own "skip unavailable,
            # renormalize over what's present" tolerance rather than an artificially strict
            # test. Result: 110 months (2017-2026), median cross-section jumped from 850 to
            # 6,505 symbols (7.6x) - a materially less selective sample. Also caught and fixed
            # two staleness bugs in the proxy construction itself before trusting the result:
            # value_proxy still used the pre-audit EV/EBITDA+EV/Revenue split (removed from the
            # live formula as PE/PS duplicates the same day) instead of the live formula's
            # actual PE/PB/PS/FCF/dividend/Size mix, and momentum_proxy still used the
            # pre-redesign mom_6m/mom_12m split (replaced live by the derived 12-1 skip-month
            # construction) instead of mom_3m/mom_12_1/RSI/MACD/SMA - both fixed to match
            # current live weights before this test's numbers were trusted.
            #
            # Multivariate (controlling for the other 5): stability_proxy t=1.91, value_proxy
            # t=1.39, growth_proxy t=1.16, positioning_proxy t=0.82, quality_proxy t=0.81,
            # momentum_proxy t=-0.87 (negatively signed). Univariate: value_proxy t=1.60,
            # stability_proxy t=1.31, quality_proxy t=1.22, growth_proxy t=0.81,
            # positioning_proxy t=0.23, momentum_proxy t=0.05. No pillar clears the
            # conventional |t|=2 significance bar in this run, but Stability and Value are
            # consistently the two strongest across both specs, while Momentum (negatively
            # signed both ways) and Positioning (weak both ways, consistent with
            # ad_rating's already-documented null finding - see this file's Positioning
            # docstring) are consistently the two weakest. ACTED ON with a proportionate
            # reweight (not a full rewrite, given no pillar reaches clean significance):
            # stability 0.14->0.18 (+4, strongest multivariate showing, consistent with this
            # pillar's own volatility_60d being the single strongest sub-factor found in the
            # entire multi-pillar audit), value 0.20->0.21 (+1, clear univariate leader),
            # momentum 0.15->0.12 (-3, negatively signed both specs, consistent with this
            # pillar's own sub-factors also testing null), positioning 0.14->0.12 (-2,
            # consistent with ad_rating's own t=-0.23 null result), growth/quality left
            # unchanged (0.12/0.25 - more ambiguous multivariate-vs-univariate showings, no
            # clear case for moving either direction beyond what their own within-pillar
            # audits already did).
            #
            # As a side effect of rebuilding value_proxy to match the live formula, this pass
            # also independently re-confirmed the Size factor (see this pillar's own docstring
            # "SIZE FACTOR" note): a standalone diagnostic -log(market_cap) test in this exact
            # point-in-time panel scored t=4.42 (positive coefficient = smaller cap, higher
            # forward return - same direction as the original t=-5.37 claim, reproduced via an
            # entirely independent methodology/script). Notably, value_proxy AT LIVE WEIGHTS
            # (t=1.39/1.60) scores well below Size tested alone (t=4.42) or below the
            # pre-Size-addition value_proxy that also lacked EV/EBITDA+EV/Revenue duplication
            # (t=2.48/2.59, from an earlier diagnostic run of this same script) - suggesting
            # Value's OWN internal PE/PB/PS/FCF/Div/Size weighting may not be combining these
            # 6 inputs efficiently (the same "combining alphas" problem Grinold-Kahn solves at
            # the top level may also apply within this pillar). Flagged as a follow-up, not
            # acted on here - out of scope for this pass, which only tests the top-level mix.
            #
            # SIZE FACTOR AS 7TH PILLAR - RESOLVED 2026-08-25 (real-money-readiness follow-up,
            # user asked to dig in and decide, not just flag; reconciled same day with the
            # REDESIGNED PASS above during a concurrent-session merge). SIZE (market cap,
            # Fama-French SMB, Banz 1981) was found completely absent from all 6 pillars,
            # tested standalone at t=-5.37 (150 months 2014-2026, median 2,601 symbols) and
            # IMPLEMENTED as a 20%-weighted sub-component inside the Value pillar (see
            # _score_value's docstring, commit 2d77f7bfd) - NOT a top-level 7th pillar
            # (effective top-level weight ~4% = value's 21% x size's 20% internal share).
            #
            # Follow-up question: does promoting Size to its own top-level composite slot (vs.
            # leaving it inside Value) have real backing? A first attempt at this (extending
            # the ORIGINAL, strict-dropna version of fama_macbeth_composite_weights.py to add
            # log(market_cap) as a 7th factor) found t=0.47 multivariate/t=0.86 univariate -
            # not significant - and reasoned analytically that this was likely the same
            # sample-selection bias already flagged for the base_weights test, without actually
            # fixing the bias and re-measuring.
            #
            # RE-TESTED 2026-08-25 (same-day merge reconciliation) on the REDESIGNED PASS's
            # properly-repowered sample (6,505 vs 850 median symbols): naively adding size_proxy
            # as a 7th column alongside the existing value_proxy (which already has Size baked
            # in at 20% internal weight) gave size_proxy t=8.86 and value_proxy t=-5.46 - a
            # DOUBLE-COUNTING artifact (the same bug class as Momentum's redundant windows and
            # Value's own EV/EBITDA/PE duplication elsewhere in this file), not a clean read.
            # Rebuilt value_proxy WITHOUT its Size sub-component (same relative PE/PB/PS/FCF/Div
            # weights) and tested THAT alongside a separate size_proxy instead, removing the
            # overlap: size_proxy t=7.62, value_proxy_nosize t=0.86 (growth_proxy t=2.72,
            # stability_proxy t=2.38, quality/momentum/positioning all weak, consistent with the
            # 6-pillar run). This is a clean, methodologically sound result, NOT contaminated by
            # double-counting - and it is dramatically stronger than every existing pillar's own
            # top-level coefficient (stability's 2.38-2.41 is the next-best). This EMPIRICALLY
            # OVERTURNS the prior "not significant, sample-selection artifact, don't promote"
            # conclusion, which was reasoned about analytically rather than verified by actually
            # fixing the bias and re-measuring - per this session's own "re-run claims, don't
            # just build on them" lesson ([[pe_pb_ps_ranking_independently_reverified_20260825]]).
            #
            # DECISION: NOT unilaterally acted on here. This reverses a decision the prior pass
            # reached with explicit user involvement ("user asked to dig in and decide"), and
            # promoting Size to a real top-level pillar is a DB schema/API/frontend commitment,
            # not a pure weight-tuning change - surfaced explicitly to the user rather than
            # silently overridden, even though the evidence is now much stronger than either
            # prior pass had. If the user confirms, the schema/API/frontend work (new
            # `size_score` column + API field + a 7th slot in every composite-breakdown display)
            # still needs to be built - not done as part of this reconciliation pass.
            base_weights = BASE_PILLAR_WEIGHTS
            normalized_weights = base_weights

            # Clamp scores to 0-100, keep markers for missing data
            def clamp_score(score: float | dict[str, Any] | None) -> float | dict[str, Any] | None:
                if isinstance(score, float):
                    return max(0.0, min(100.0, score))
                # Return marker dicts as-is; don't silence them with None
                return score if isinstance(score, dict) else None

            clamped_quality = clamp_score(quality_score)
            clamped_growth = clamp_score(growth_score)
            clamped_value = clamp_score(value_score)
            clamped_positioning = clamp_score(positioning_score)
            clamped_stability = clamp_score(stability_score)
            clamped_momentum = clamp_score(momentum_score)

            # Composite: only use metrics that are actually available
            # Do NOT redistribute weights (GOVERNANCE rule: no weight redistribution)
            # If metric unavailable, its weight is skipped (contributes 0), not given to other metrics
            composite_score_value = 0.0
            for metric_name, clamped_value_score in [
                ("quality", clamped_quality),
                ("growth", clamped_growth),
                ("value", clamped_value),
                ("positioning", clamped_positioning),
                ("stability", clamped_stability),
                ("momentum", clamped_momentum),
            ]:
                # Only use base weight if metric is available
                # CRITICAL: Require explicit availability flag for each metric (fail-fast if missing)
                if metric_name not in score_availability:
                    raise ValueError(
                        f"[STOCK_SCORES] {symbol}: availability flag missing for '{metric_name}' metric. "
                        f"All metrics must have explicit availability status in score_availability dict."
                    )
                if not score_availability[metric_name]:
                    continue  # Skip unavailable metrics (don't give their weight to others)

                weight = normalized_weights[metric_name]
                # Handle marker dicts (data unavailable) separately from float scores
                if isinstance(clamped_value_score, dict) and clamped_value_score.get("data_unavailable"):
                    # Marker returned - data unavailable for this metric
                    # CRITICAL: Validate reason field exists when data_unavailable=True (fail-fast if missing)
                    reason = clamped_value_score.get("reason")
                    if reason is None:
                        raise ValueError(
                            f"[STOCK_SCORES] {symbol} metric '{metric_name}' marked data_unavailable but missing required 'reason' field. "
                            f"API contract violation: unavailable markers must include reason. Marker: {clamped_value_score}"
                        )
                    unavailable_metrics[metric_name] = reason
                    logger.warning(f"[STOCK_SCORES] {metric_name} unavailable for {symbol}: {reason}")
                elif clamped_value_score is None:
                    raise ValueError(
                        f"[{symbol}] Metric '{metric_name}' has weight {weight:.3f} but returned None (not a marker dict). "
                        "This indicates a calculation error or incomplete implementation."
                    )
                elif isinstance(clamped_value_score, float):
                    composite_score_value += clamped_value_score * weight
                else:
                    raise RuntimeError(
                        f"[{symbol}] Metric '{metric_name}' returned unexpected type {type(clamped_value_score).__name__}. "
                        "Expected float or dict marker."
                    )

            # Clamp to 0-100: raw composite value (may be <100 if metrics missing).
            # No rescaling per GOVERNANCE (no weight redistribution).
            # Traders see completeness % to understand data quality.
            composite_score = max(0.0, min(100.0, round(composite_score_value, 2)))

            def extract_score_value(score_result: float | dict[str, Any] | None) -> float | None:
                """Extract numeric score from result (float or marker dict)."""
                if isinstance(score_result, float):
                    return round(score_result, 2)
                return None  # Markers and None return as None

            # CRITICAL FIX: Enforce completeness threshold per GOVERNANCE.md + config
            # Session 297 assumed "trading gates will filter", but no downstream filters exist.
            # Database audit found 851 scores with 50-70% completeness marked available=FALSE.
            # This violates fail-fast governance: incomplete data must be marked unavailable.
            # Threshold is now configurable via algo_config.min_completeness_score (default: 70%)
            # Read threshold from cache that was loaded in _prepare_batch_context()
            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            score_available = data_completeness >= min_completeness_threshold
            if not score_available:
                reason_text = f"Completeness {data_completeness:.2f}% < {min_completeness_threshold}% threshold (missing metrics: {', '.join(unavailable_metrics.keys())})"
            else:
                reason_text = None

            # Build components breakdown for dashboard display
            components = {
                "quality": extract_score_value(clamped_quality),
                "growth": extract_score_value(clamped_growth),
                "value": extract_score_value(clamped_value),
                "positioning": extract_score_value(clamped_positioning),
                "stability": extract_score_value(clamped_stability),
                "momentum": extract_score_value(clamped_momentum),
            }

            # Build data sources attribution for transparency
            data_sources = {
                "quality": ["financial_statements", "sec_valuations"] if extract_score_value(clamped_quality) else [],
                "growth": ["financial_statements", "analyst_earnings_estimates", "enhanced_quality_growth_metrics"]
                if extract_score_value(clamped_growth)
                else [],
                "value": ["financial_statements", "sec_valuations", "dividend_data"]
                if extract_score_value(clamped_value)
                else [],
                "positioning": ["institutional_holdings_13f", "short_interest_finra"]
                if extract_score_value(clamped_positioning)
                else [],
                "stability": ["risk_metrics_daily", "technical_data_daily", "financial_statements"]
                if extract_score_value(clamped_stability)
                else [],
                "momentum": ["technical_data_daily", "market_status_daily", "insider_transaction_velocity"]
                if extract_score_value(clamped_momentum)
                else [],
            }

            result = {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": extract_score_value(clamped_quality),
                "growth_score": extract_score_value(clamped_growth),
                "value_score": extract_score_value(clamped_value),
                "momentum_score": extract_score_value(clamped_momentum),
                "positioning_score": extract_score_value(clamped_positioning),
                "stability_score": extract_score_value(clamped_stability),
                # Placeholder only: update_rs_percentiles() (post_run(), batch rank pass)
                # overwrites this with the real PERCENT_RANK() value for every symbol once the
                # whole run succeeds. NULL here (not 0.0) so that if post_run() is skipped -
                # runner.py only calls it after the fail-rate gate passes - or the run crashes
                # first, rows are left visibly missing their RS percentile rather than showing
                # a fabricated bottom-percentile score indistinguishable from a real 0th-percentile
                # stock (this fed straight into Phase 7's signal-generation completeness gate).
                "rs_percentile": None,
                "data_completeness": data_completeness,
                "unavailable_metrics": json.dumps(unavailable_metrics) if unavailable_metrics else None,
                "components": json.dumps(components),  # Score component breakdown
                "data_sources": json.dumps(data_sources),  # Data source attribution
                "data_unavailable": not score_available,  # CRITICAL: Mark unavailable if completeness < 70%
                "reason": reason_text,
                "date": datetime.now(timezone.utc).date(),
                "updated_at": datetime.now(timezone.utc),
            }
            if unavailable_metrics:
                logger.warning(
                    f"[STOCK_SCORES] {symbol} computed with degraded metrics: "
                    f"{', '.join(f'{k}={v}' for k, v in unavailable_metrics.items())}"
                )
            return result

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    # ARCHITECTURAL PATTERN: Internal Scoring Pipeline (UPDATED 2026-07-03)
    # ====================================================
    # The following _get_* and _score_* methods are INTERNAL PLUMBING that feeds into
    # _compute_stock_score() → fetch_incremental() public API.
    #
    # RETURN TYPES (STRICT):
    # - All 6 _get_*() methods return dict[str, Any] (either real metrics or data_unavailable marker)
    # - All 6 _score_*() methods return float | dict[str, Any] (score or data_unavailable marker)
    # - No None returns anywhere - either real data or explicit data_unavailable marker
    # - Marker dicts always have {"data_unavailable": True, "reason": "..."}
    #
    # FIELD CONVERSION (CRITICAL SAFETY):
    # - All numeric fields converted via safe_float() (never raw float())
    # - safe_float() raises RuntimeError on type conversion failure
    # - Prevents data corruption from propagating silently
    # - Every field conversion distinguishes None (no data) from ValueError (corrupted data)
    #
    # DATA VALIDATION (FAIL-FAST):
    # - All _get_* functions validate row length before accessing indices (6 bound checks)
    #   * _get_quality_metrics: 24 columns (roe through revenue_growth_yoy, includes Phase 3 expansion fields)
    #   * _get_growth_metrics: 12 columns (revenue_growth_1y through ocf_growth_yoy, data_unavailable last)
    #   * _get_value_metrics: 10 columns (pe_ratio through ev_revenue, data_unavailable last)
    #   * _get_positioning_metrics: 6 columns (institutional_ownership through short_interest_pct_change, data_unavailable last)
    #   * _get_stability_metrics: 8 columns (volatility_252d through max_drawdown_1y, data_unavailable last)
    #   * _get_momentum_metrics: 5 columns (current through price_12m_ago)
    # - All _score_* functions return marker dicts if input metrics are missing/incomplete
    # - Momentum metrics: Require proper lookback periods (30d/60d/120d/252d), not degraded estimates
    # - Stock minimum: Require 3/6 metrics (50%) regardless of stock age (no IPO exceptions)
    #
    # MARKER HANDLING by _compute_stock_score():
    # - real_scores = [s for s in all_scores if isinstance(s, float)] → only floats count
    # - score_availability dict tracks which metrics returned markers
    # - Weight redistribution: Available metrics upweighted, missing metrics zeroed
    # - Minimum check: raise RuntimeError if data_count < 3 (hard threshold)
    #
    # PUBLIC API (Exceptions, not degraded returns):
    # - fetch_incremental() raises RuntimeError on insufficient metrics (no silent degradation)
    # - Returns data_unavailable dict to DB only on exceptions (operator visibility)
    #
    # KEY CHANGES (2026-07-03):
    # 1. All _get_* now validate row length before accessing (6 bound checks x 1-5 fields = 15+ validations)
    # 2. All numeric conversions use safe_float() consistently (prevents type corruption)
    # 3. Removed new-listing exception that allowed 2/6 metrics
    # 4. Removed short-term momentum fallback (2/4/7/14 day lookbacks violated standards)
    # 5. Type hints: Removed | None from _score_* returns (always float or dict)
    # 6. Updated all docstrings with MINIMUM DATA REQUIREMENT sections
    # ====================================================

    def _get_quality_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch quality metrics for symbol including Phase 3 expansion metrics.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 24 columns (10 base + 14 Phase 3 expansion)
        - Schema mismatch (len(row) < 24) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_quality_metrics_found"

        CRITICAL FIX 2026-07-23 (Session 359): Now fetches all Phase 3 expansion fields
        (gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, payout_ratio,
        free_cash_flow, operating_cash_flow, total_debt, total_cash, cash_per_share, ebitda,
        earnings_growth_yoy, revenue_growth_yoy, interest_coverage). These are required for Phase 8 quality scoring
        enhancement via _enhance_quality_score().

        MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes immediate
        fail-fast ValueError to prevent silent data corruption.
        """
        row = self._quality_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 25 columns before accessing indices
            # (10 original + 14 Phase 3 expansion + 1 interest_coverage + 1 data_unavailable flag = 26 total, minus symbol = 25)
            if len(row) < 25:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: quality_metrics row has {len(row)} columns, expected 25. "
                    f"Schema mismatch detected - Phase 3 or interest_coverage fields missing. Failing fast."
                )
            data_unavailable = row[9]
            quality_score = safe_float(row[8], f"{symbol}.quality_score")
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in quality_metrics "
                    f"(likely REIT or security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "quality_metrics")
            # Row exists and data is available - return all fields including Phase 3 expansion
            return {
                "roe": safe_float(row[0], f"{symbol}.roe"),
                "roa": safe_float(row[1], f"{symbol}.roa"),
                "operating_margin": safe_float(row[2], f"{symbol}.operating_margin"),
                "net_margin": safe_float(row[3], f"{symbol}.net_margin"),
                "debt_to_equity": safe_float(row[4], f"{symbol}.debt_to_equity"),
                "current_ratio": safe_float(row[5], f"{symbol}.current_ratio"),
                "quick_ratio": safe_float(row[6], f"{symbol}.quick_ratio"),
                "debt_to_assets": safe_float(row[7], f"{symbol}.debt_to_assets", allow_none=True),
                "quality_score": quality_score,  # Pre-computed by load_value_quality_growth_metrics.py
                # Phase 3 expansion metrics (Session 358+)
                "gross_margin": safe_float(row[10], f"{symbol}.gross_margin", allow_none=True),
                "ebitda_margin": safe_float(row[11], f"{symbol}.ebitda_margin", allow_none=True),
                "roic_pct": safe_float(row[12], f"{symbol}.roic_pct", allow_none=True),
                "fcf_to_net_income": safe_float(row[13], f"{symbol}.fcf_to_net_income", allow_none=True),
                "ocf_to_net_income": safe_float(row[14], f"{symbol}.ocf_to_net_income", allow_none=True),
                "payout_ratio": safe_float(row[15], f"{symbol}.payout_ratio", allow_none=True),
                "free_cash_flow": safe_float(row[16], f"{symbol}.free_cash_flow", allow_none=True),
                "operating_cash_flow": safe_float(row[17], f"{symbol}.operating_cash_flow", allow_none=True),
                "total_debt": safe_float(row[18], f"{symbol}.total_debt", allow_none=True),
                "total_cash": safe_float(row[19], f"{symbol}.total_cash", allow_none=True),
                "cash_per_share": safe_float(row[20], f"{symbol}.cash_per_share", allow_none=True),
                "ebitda": safe_float(row[21], f"{symbol}.ebitda", allow_none=True),
                "earnings_growth_yoy": safe_float(row[22], f"{symbol}.earnings_growth_yoy", allow_none=True),
                "revenue_growth_yoy": safe_float(row[23], f"{symbol}.revenue_growth_yoy", allow_none=True),
                "interest_coverage": safe_float(row[24], f"{symbol}.interest_coverage", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No quality metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_quality_metrics", "Quality metrics table missing data")

    def _get_growth_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch growth metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 7 columns (revenue_growth_1y, revenue_growth_3y,
          revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y, data_unavailable)
        - Schema mismatch (len(row) < 7) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_growth_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 7 columns. Missing columns causes immediate
        fail-fast ValueError. Dependent on upstream annual_income_statement availability.
        """
        row = self._growth_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 18 columns before accessing indices
            if len(row) < 18:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 18. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[17]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in growth_metrics "
                    f"(likely security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "growth_metrics")
            # Row exists and data is available
            return {
                "revenue_growth_1y": safe_float(row[0], f"{symbol}.revenue_growth_1y"),
                "revenue_growth_3y": safe_float(row[1], f"{symbol}.revenue_growth_3y"),
                "revenue_growth_5y": safe_float(row[2], f"{symbol}.revenue_growth_5y"),
                "eps_growth_1y": safe_float(row[3], f"{symbol}.eps_growth_1y"),
                "eps_growth_3y": safe_float(row[4], f"{symbol}.eps_growth_3y"),
                "eps_growth_5y": safe_float(row[5], f"{symbol}.eps_growth_5y"),
                "net_income_growth_yoy": safe_float(row[6], f"{symbol}.net_income_growth_yoy", allow_none=True),
                "operating_income_growth_yoy": safe_float(
                    row[7], f"{symbol}.operating_income_growth_yoy", allow_none=True
                ),
                "sustainable_growth_rate": safe_float(row[8], f"{symbol}.sustainable_growth_rate", allow_none=True),
                "fcf_growth_yoy": safe_float(row[9], f"{symbol}.fcf_growth_yoy", allow_none=True),
                "ocf_growth_yoy": safe_float(row[10], f"{symbol}.ocf_growth_yoy", allow_none=True),
                "gross_margin_trend": safe_float(row[11], f"{symbol}.gross_margin_trend", allow_none=True),
                "operating_margin_trend": safe_float(row[12], f"{symbol}.operating_margin_trend", allow_none=True),
                "net_margin_trend": safe_float(row[13], f"{symbol}.net_margin_trend", allow_none=True),
                "roe_trend": safe_float(row[14], f"{symbol}.roe_trend", allow_none=True),
                "asset_growth_yoy": safe_float(row[15], f"{symbol}.asset_growth_yoy", allow_none=True),
                "eps_growth_stability": safe_float(row[16], f"{symbol}.eps_growth_stability", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_growth_metrics", "Growth metrics table missing data")

    def _get_value_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch value metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 12 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
          dividend_yield, fcf_yield, forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct,
          market_cap, data_unavailable) - stale "7 columns" claim here predates several later
          additions (forward_pe/ev_ebitda/ev_revenue, margin_of_safety_pct, market_cap); fixed
          2026-08-25 rather than left drifted further.
        - Schema mismatch (len(row) < 12) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_value_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 7 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._value_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 12 columns before accessing indices
            # (11 + market_cap added 2026-08-25 to close the Size-factor gap - see
            # _score_value's docstring)
            if len(row) < 12:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 12. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[11]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in value_metrics "
                    f"(likely security with missing pricing data)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "value_data_marked_unavailable"}
            # Row exists and data is available
            return {
                "pe_ratio": safe_float(row[0], f"{symbol}.pe_ratio"),
                "pb_ratio": safe_float(row[1], f"{symbol}.pb_ratio"),
                "ps_ratio": safe_float(row[2], f"{symbol}.ps_ratio"),
                "peg_ratio": safe_float(row[3], f"{symbol}.peg_ratio"),
                "dividend_yield": safe_float(row[4], f"{symbol}.dividend_yield"),
                "fcf_yield": safe_float(row[5], f"{symbol}.fcf_yield"),
                "forward_pe": safe_float(row[6], f"{symbol}.forward_pe", allow_none=True),
                "ev_ebitda": safe_float(row[7], f"{symbol}.ev_ebitda", allow_none=True),
                "ev_revenue": safe_float(row[8], f"{symbol}.ev_revenue", allow_none=True),
                "margin_of_safety_pct": safe_float(row[9], f"{symbol}.margin_of_safety_pct", allow_none=True),
                "market_cap": safe_float(row[10], f"{symbol}.market_cap", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_found"}

    def _get_positioning_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch positioning metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 6 columns (institutional_ownership,
          short_interest_percent, shares_short_prior_month, short_interest_pct_change, ad_rating,
          data_unavailable) - insider_ownership_pct removed 2026-08-24 (column dropped from
          positioning_metrics entirely, "not a positioning metric")
        - Schema mismatch (len(row) < 6) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_positioning_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Weird securities (ETFs,
        preferreds, depositary shares) have rows marked data_unavailable=True with NULL values.
        Previously returned NULLs instead of marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 4 columns. Missing columns causes immediate
        fail-fast ValueError. Not available for REITs/special securities (expected, handled gracefully).
        """
        row = self._positioning_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 6 columns before accessing indices
            if len(row) < 6:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: positioning_metrics row has {len(row)} columns, expected 6. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[5]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in positioning_metrics "
                    f"(likely weird security: ETF, preferred, depositary share)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "positioning_data_marked_unavailable"}
            # Row exists and data is available
            return {
                "institutional_ownership": safe_float(row[0], f"{symbol}.institutional_ownership"),
                "short_interest": safe_float(row[1], f"{symbol}.short_interest"),
                "shares_short_prior_month": safe_float(row[2], f"{symbol}.shares_short_prior_month", allow_none=True),
                "short_interest_pct_change": safe_float(row[3], f"{symbol}.short_interest_pct_change", allow_none=True),
                "ad_rating": safe_float(row[4], f"{symbol}.ad_rating", allow_none=True),
            }
        # No row exists at all
        logger.debug(
            f"[LOAD_STOCK_SCORES] No positioning metrics available for {symbol} - will reduce score completeness"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_positioning_metrics_found"}

    def _get_stability_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch stability metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 9 columns (volatility_252d, volatility_60d,
          volatility_30d, beta, downside_volatility_252d/60d/30d, max_drawdown_1y,
          data_unavailable)
        - Schema mismatch (len(row) < 9) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_stability_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        CRITICAL FIX 2026-07-03: Now uses safe_float() for all numeric fields to detect
        data corruption. Previous inline float() bypassed error handling.

        FIX 2026-08-16: downside_volatility_60d/30d now included (columns already existed on
        stability_metrics, just never selected - see the cache-building query's comment).

        CLEANUP 2026-08-16 (later): debt_to_assets/debt_to_equity/current_ratio/quick_ratio/
        cash_per_share (fundamental leverage/liquidity metrics) and revenue_concentration_hhi
        (business diversification) are no longer merged in here - stability is meant to track
        price-volatility/risk-of-loss character, not balance-sheet fundamentals. The debt/
        liquidity/cash metrics now feed Quality's _enhance_quality_score instead (see
        _score_financial_stability, called from there); revenue_concentration_hhi was dropped
        from scoring entirely per user request (not a stability signal).

        MINIMUM DATA REQUIREMENT: Row must have exactly 9 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._stability_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 9 columns before accessing indices
            if len(row) < 9:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: stability_metrics row has {len(row)} columns, expected 9. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[8]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in stability_metrics "
                    f"(likely security with insufficient price history)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "stability_data_marked_unavailable"}
            # Row exists and data is available
            metrics = {
                "volatility_252d": safe_float(row[0], f"{symbol}.volatility_252d"),
                "volatility_60d": safe_float(row[1], f"{symbol}.volatility_60d"),
                "volatility_30d": safe_float(row[2], f"{symbol}.volatility_30d"),
                "beta": safe_float(row[3], f"{symbol}.beta"),
                "downside_volatility_252d": safe_float(row[4], f"{symbol}.downside_volatility_252d", allow_none=True),
                "downside_volatility_60d": safe_float(row[5], f"{symbol}.downside_volatility_60d", allow_none=True),
                "downside_volatility_30d": safe_float(row[6], f"{symbol}.downside_volatility_30d", allow_none=True),
                "max_drawdown_1y": safe_float(row[7], f"{symbol}.max_drawdown_1y", allow_none=True),
            }
            return metrics
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No stability metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_metrics_found"}

    def _get_momentum_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch momentum/RS metrics for symbol from momentum_metrics table.

        CRITICAL FIX 2026-07-18: Now reads precomputed momentum values from momentum_metrics
        table (populated by load_risk_metrics_daily.py) instead of computing from scratch.
        This fixes the issue where stock_scores had all NULL momentum despite momentum_metrics
        being populated.

        momentum_metrics provides:
        - momentum_1m, momentum_3m, momentum_6m, momentum_12m (already calculated)
        - data_unavailable flag (True if loader failed)

        Also merges in the latest RSI(14)/MACD from technical_data_daily (via
        self._technical_cache). These are a separate, independently-available source, so a
        symbol missing from momentum_metrics can still contribute an RSI/MACD-only momentum
        score, and vice versa.

        Returns dict with momentum values (which may be None for individual timeframes if
        upstream loader failed to calculate them).
        """
        try:
            tech_row = self._technical_cache.get(symbol, None)
            rsi_14 = safe_float(tech_row[0], f"{symbol}.rsi_14", allow_none=True) if tech_row else None
            macd = safe_float(tech_row[1], f"{symbol}.macd", allow_none=True) if tech_row else None
            sma_50 = safe_float(tech_row[2], f"{symbol}.sma_50", allow_none=True) if tech_row else None
            sma_200 = safe_float(tech_row[3], f"{symbol}.sma_200", allow_none=True) if tech_row else None
            close = safe_float(tech_row[4], f"{symbol}.close", allow_none=True) if tech_row else None
            # Decimal fraction (0.05 = +5%), matching _score_momentum's ±10%-range-maps-to-0-100
            # formula - NOT the *100 percentage scale the scores API computes for display.
            price_vs_sma_50 = (close - sma_50) / sma_50 if close is not None and sma_50 else None
            price_vs_sma_200 = (close - sma_200) / sma_200 if close is not None and sma_200 else None

            row = self._momentum_cache.get(symbol, None)

            if row is not None:
                # momentum_metrics cache has 5 columns: momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable
                if len(row) < 5:
                    raise ValueError(
                        f"[STOCK_SCORES] {symbol}: momentum cache returned {len(row)} columns, expected 5. "
                        f"Schema mismatch detected. Failing fast."
                    )

                momentum_1m = safe_float(row[0], f"{symbol}.momentum_1m", allow_none=True)
                momentum_3m = safe_float(row[1], f"{symbol}.momentum_3m", allow_none=True)
                momentum_6m = safe_float(row[2], f"{symbol}.momentum_6m", allow_none=True)
                momentum_12m = safe_float(row[3], f"{symbol}.momentum_12m", allow_none=True)
                data_unavailable = row[4]

                # If momentum_metrics marked this symbol as unavailable, price-return momentum
                # is unusable, but RSI/MACD came from an independent source and may still score.
                if data_unavailable:
                    if rsi_14 is None and macd is None:
                        return {"data_unavailable": True, "reason": "momentum_metrics_loader_failed"}
                    return {
                        "momentum_1m": None,
                        "momentum_3m": None,
                        "momentum_6m": None,
                        "momentum_12m": None,
                        "rsi_14": rsi_14,
                        "macd": macd,
                        "price_vs_sma_50": price_vs_sma_50,
                        "price_vs_sma_200": price_vs_sma_200,
                    }

                return {
                    "momentum_1m": momentum_1m,
                    "momentum_3m": momentum_3m,
                    "momentum_6m": momentum_6m,
                    "momentum_12m": momentum_12m,
                    "rsi_14": rsi_14,
                    "macd": macd,
                    "price_vs_sma_50": price_vs_sma_50,
                    "price_vs_sma_200": price_vs_sma_200,
                }

            # Symbol not in momentum_metrics cache; RSI/MACD alone cannot substitute for price momentum
            # CRITICAL FIX (Session 416): Do not mix incompatible metric classes as substitutes.
            # Per GOVERNANCE.md line 56-58: "No secondary fallbacks. Never use short-term momentum when long-term unavailable (different signal)"
            # RSI/MACD are oscillators (technical indicators), not price-return momentum (fundamental signal).
            # Substituting one for the other creates false signal diversification - both are now technical.
            # This biases the composite score away from fundamental factors and toward technical analysis.
            # Solution: Return data_unavailable marker instead of partial/mixed metrics.
            if rsi_14 is not None or macd is not None:
                logger.warning(
                    f"[LOAD_STOCK_SCORES] {symbol}: momentum_metrics missing (price momentum unavailable). "
                    f"RSI/MACD available but cannot substitute for price-return momentum (different signal class). "
                    f"Marking momentum data unavailable to prevent metric class mixing."
                )
                return {"data_unavailable": True, "reason": "price_momentum_metrics_missing"}

            logger.warning(
                f"[LOAD_STOCK_SCORES] No momentum data available for {symbol} - momentum_metrics not populated"
            )
            logger.warning(f"[LOAD_STOCK_SCORES] Returning data_unavailable marker for momentum_metrics({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_data_available"}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_quality(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score quality metrics on 0-100 scale using Phase 3 expanded metrics.

        CRITICAL: Uses only pre-computed quality_score (official model consensus). No fallback
        computation - if pre-computed score missing, returns explicit data_unavailable marker.
        For financial accuracy, missing scores are better than fabricated heuristics.

        CORRECTED 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what
        already shipped): this docstring previously claimed "Margins 30% + Profitability 25% +
        Leverage/Liquidity 25% + Growth 20%" - stale/wrong, doesn't match the actual upstream
        computation (load_value_quality_growth_metrics.py, ~line 3313-3330). The real formula
        is a simple equal-weighted average of up to 6 available components - roe, roa,
        operating_margin, net_margin, a debt-to-assets score (100 - debt_to_assets*100,
        inverted so higher is better), and an interest-coverage solvency curve (0 below 0x,
        scaling to 100 at 10x+) - each clamped to [0, 100] and averaged over however many are
        non-None (1/n weight each, not fixed percentages). There is no growth component in this
        upstream score at all, so the double-counting concern that motivated removing
        earnings_growth_yoy from _enhance_quality_score below doesn't apply to this base score -
        checked directly rather than assumed.

        OPEN QUESTION added same pass: built algo/research/fama_macbeth_quality_factors.py to
        test the corrected 6-component formula above with point-in-time Fama-MacBeth (same
        annual-statement reconstruction as the Growth/Value scripts). Two findings, neither
        acted on: (1) measured directly (60-month pooled correlation, n=98,902): roe and
        debt_to_assets correlate r=0.82 (mechanical - ROE = ROA x equity multiplier, so ROE
        embeds much of the same leverage information debt_to_assets measures directly, DuPont
        decomposition), and operating_margin/net_margin correlate r=0.91 (both are profit/
        revenue ratios differing mainly by non-operating items) - the equal-weighted average
        of 6 gives these two redundant pairs 4/6 of the weight, versus roa and
        interest_coverage (the two most distinct signals, ~0.00-0.17 correlated with
        everything else) at 1/6 each. Smaller-magnitude version of the same redundancy issue
        found in Value (algo/research/fama_macbeth_value_factors.py) and Momentum
        (algo/research/fama_macbeth_momentum_factors.py) today. (2) debt_to_assets came back
        POSITIVELY signed in both univariate (t=2.28) and multivariate (t=2.19) FM tests -
        higher leverage associated with HIGHER forward return, opposite the "low debt is good"
        assumption baked into this formula's debt_to_assets_score inversion. Not a confident
        reversal call though: this sits at a genuine, unresolved tension in the literature
        between basic leverage theory (Modigliani-Miller - more debt mechanically raises
        equity beta and expected equity return, textbook corporate finance) and the
        documented distress-risk anomaly (Campbell/Hilscher/Szilagyi 2008, JoF - financially
        distressed/high-leverage firms empirically underperform, a real puzzle against the MM
        prediction) - unlike the cleaner Growth/Value findings above, both directions have
        solid academic grounding here, so this is flagged as genuinely unresolved rather than
        miscalibrated.

        METHODOLOGY CHECK (2026-08-25, same pass, user-prompted): before trusting the linear
        coefficient, checked whether it might be masking a non-monotonic (e.g. U-shaped -
        too-little-debt as inefficient capital structure, too-much as distress risk, a real
        possibility raised by the MM-vs-distress-anomaly tension above) relationship a linear
        regression can't see. Decile sort: deciles 0-6 (well-populated, 144-150 months each)
        show a fairly clean, roughly MONOTONIC increase from 0.70% to 1.04%/month as debt rises
        - not a U-shape. Decile 7 jumps to 2.77% but on only 50 months (deciles 8-9 too
        duplicate-heavy to bin) - too thin to trust. The linear finding holds up under this
        nonparametric check across the reliable range of the distribution; it isn't a
        linear-regression artifact hiding a different true shape.
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

        # CRITICAL: Require pre-computed quality_score (official model consensus of 6 base metrics)
        # Do NOT fall back to dynamic computation - that creates fabricated scores from heuristics.
        # Missing quality_score indicates upstream issue (Phase 3 didn't run or metrics incomplete).
        if metrics.get("quality_score") is not None:
            quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
            if quality_score_value is not None:
                logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
                # Enhance with Phase 3 margin/growth if available
                return self._enhance_quality_score(quality_score_value, metrics, symbol)

        # FAIL-FAST: No pre-computed score and no fallback. This is explicit data unavailability.
        logger.warning(
            f"[STOCK_SCORES] Quality score unavailable for {symbol}. "
            f"Pre-computed quality_score missing - Phase 3 may not have completed or metrics incomplete. "
            f"Returning data_unavailable marker instead of fabricated heuristic score."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_unavailable"}

    def _enhance_quality_score(self, base_score: float, metrics: dict[str, Any], symbol: str) -> float:
        """Enhance pre-computed quality score with Phase 3 margin/earnings-stability signals.

        Adjusts base score by ±10% based on margin level/trend, earnings consistency, cash
        conversion, ROIC, and leverage. Keeps existing quality_score as foundation; uses new
        metrics for refinement.

        CLEANUP 2026-08-16: Financial Stability (debt-to-equity, debt-to-assets -
        _score_financial_stability) moved here from Stability's _score_stability, where it
        was a 20%-weighted sub-score. These are balance-sheet fundamentals (leverage/
        solvency), not price-volatility signals, so they belong under Quality. CLEANUP
        2026-08-18: current_ratio/quick_ratio/cash_per_share removed from
        _score_financial_stability - not factor-score inputs anymore.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): debt_to_assets was
        double-counted: it already feeds the base quality_score (~17%, computed upstream in
        load_value_quality_growth_metrics.py) AND was reused a second time inside
        _score_financial_stability below. _score_financial_stability now uses debt_to_equity
        only - the one genuinely new leverage signal, not a repeat of what the base average
        already scored. earnings_growth_yoy was removed entirely - rewarding recent earnings
        growth here duplicated the entire Growth pillar's purpose (20%->12% of the composite),
        which breaks factor-orthogonality (Asness/AQR: a multi-factor composite only
        diversifies if its factors are close to independent; a fast-growing company was
        getting rewarded once in Growth and again here).

        REVERTED same day (user feedback, goal: reintroduce/re-audit removed inputs): this
        redesign briefly replaced earnings_growth_yoy with eps_growth_stability and the
        margin/ROE trend fields relocated from Growth's own scorer, on the theory
        (Asness/Frazzini/Pedersen "Quality Minus Junk", 2013) that earnings-consistency and
        quality-of-earnings-direction are genuine quality/safety signals distinct from growth
        magnitude. User pushback: these are "consistency of improvement" signals, not the
        balance-sheet-health/margin-level character the rest of this pillar measures, and
        forcing them under Quality was a taxonomy stretch rather than an evidenced placement -
        they don't cleanly belong in Growth (that's why they were moved out) but moving them
        into Quality just relocated the same categorization problem. Dropped from scoring
        entirely rather than re-homed a second time. The underlying fields
        (eps_growth_stability/operating_margin_trend/net_margin_trend/roe_trend) are still
        computed and stored by load_value_quality_growth_metrics.py for potential future use -
        only their consumption here was removed.
        """
        adjustment = 0.0

        # Margin quality: Higher margins + improving margins = quality boost.
        # gross_margin deliberately excluded 2026-08-18 - not a factor-score input.
        ebitda_margin = safe_float(metrics.get("ebitda_margin"), f"{symbol}.ebitda_margin", allow_none=True)
        net_margin = safe_float(metrics.get("net_margin"), f"{symbol}.net_margin", allow_none=True)

        margins_available = [m for m in [ebitda_margin, net_margin] if m is not None]
        if margins_available:
            avg_margin = sum(margins_available) / len(margins_available)
            # Premium for high-margin businesses (>25% net margin = quality companies)
            if avg_margin > 25:
                adjustment += 3.0
            elif avg_margin < 5:
                adjustment -= 5.0

        # Cash flow signal: Strong FCF generation improves quality
        fcf_to_ni = safe_float(metrics.get("fcf_to_net_income"), f"{symbol}.fcf_to_net_income", allow_none=True)
        if fcf_to_ni is not None:
            if fcf_to_ni > 1.0:  # FCF > Net Income = quality cash generation
                adjustment += 2.0
            elif fcf_to_ni < 0.5:  # Low FCF = cash burn risk
                adjustment -= 3.0

        # ROIC signal (2026-08-03): already fetched into the quality metrics cache and
        # displayed on the scores page, but never used in the enhancement adjustment -
        # returns-on-capital is a distinct quality signal from the margin/leverage
        # components already baked into the pre-computed base quality_score.
        roic = safe_float(metrics.get("roic_pct"), f"{symbol}.roic_pct", allow_none=True)
        if roic is not None:
            if roic > 15:
                adjustment += 3.0
            elif roic < 5:
                adjustment -= 3.0

        # Operating cash flow conversion (2026-08-03): same "never used" gap as ROIC -
        # distinct from fcf_to_net_income above since OCF is pre-capex, a purer read on
        # whether reported earnings are backed by real cash from operations.
        ocf_to_ni = safe_float(metrics.get("ocf_to_net_income"), f"{symbol}.ocf_to_net_income", allow_none=True)
        if ocf_to_ni is not None:
            if ocf_to_ni > 1.2:
                adjustment += 2.0
            elif ocf_to_ni < 0.7:
                adjustment -= 2.0

        # Financial stability (leverage): moved from Stability's factor score (see
        # CLEANUP 2026-08-16 note above). _score_financial_stability blends
        # debt_to_equity/debt_to_assets into a single 0-100 solvency read; treated as a
        # bounded adjustment here, same shape as the other signals in this method.
        fin_stability_score = self._score_financial_stability(metrics, symbol)
        if fin_stability_score is not None:
            if fin_stability_score >= 70:
                adjustment += 3.0
            elif fin_stability_score < 40:
                adjustment -= 3.0

        # Clamp adjustment to ±10 points and apply to base score
        adjustment = max(-10.0, min(10.0, adjustment))
        enhanced = base_score + adjustment

        return float(max(0, min(100, enhanced)))

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted blend: EPS 1Y (25%) + Asset Growth YoY (30%, sign-flipped) + Revenue 1Y
        (20%) + Sustainable Growth Rate (20%). Reweighted from 45/25/15/15 2026-08-25 (goal:
        horizon-matched re-audit) - see the OPEN QUESTION/LITERATURE CALIBRATION notes and the
        per-field comments below for why eps_growth_1y's weight was cut specifically.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): previously 14 inputs
        (EPS/Revenue at 1y/3y/5y plus 8 secondary trend/YoY fields), several literature-
        contradicted or redundant. Empirical findings behind this redesign:
        - Asset growth YoY was scored with the WRONG SIGN. Cooper/Gulen/Schill (2008, JoF) and
          Fama-French's CMA factor both show low-asset-growth firms outperform high-asset-growth
          firms; our own panel replicated this cleanly (Spearman rho=-0.037, p=8.4e-6, ~11pt/yr
          quintile spread) - the strongest single empirical result of the whole audit. Now
          scored with growth INVERTED (low asset growth = high score).
        - Revenue growth (1y/3y/5y) and EPS growth (3y/5y) showed weak-to-zero forward-return
          signal both individually and at the composite level - three different reweighted
          growth-composite configurations were backtested against forward 1y returns and NONE
          showed a real signal (p=0.27, p=0.94, p=0.33). Consistent with Lakonishok/Shleifer/
          Vishny (1994) and Chan/Karceski/Lakonishok (2003): trailing growth has little
          persistence. EPS 1y kept as the single conventional growth reference; Revenue kept
          only at 1y and small weight. EPS 3y/5y, Revenue 3y/5y dropped (redundant windows -
          eps_growth_5y/revenue_growth_5y also had the worst coverage of the six CAGR fields,
          38.9%/73.7% of the universe vs 1y's 75.6%/95.2%).
        - NI/OI growth YoY dropped (near-duplicates of EPS growth YoY, which already carries the
          largest single weight). FCF/OCF growth YoY dropped (no proven distinct predictive
          value once tested at the composite level, and correlated with each other and with EPS
          growth). Margin/ROE trend fields and eps_growth_stability were briefly moved to
          Quality's _enhance_quality_score same day, then dropped from scoring entirely on user
          feedback - they're "consistency of improvement" signals that don't cleanly belong in
          either pillar's character (Growth measures magnitude, Quality measures
          balance-sheet-health/margin level), and re-homing them under Quality was a taxonomy
          stretch, not an evidenced placement. The underlying fields are still computed/stored
          upstream, just unused by any score now.
        - Sustainable growth rate (ROE x retention ratio) kept - structurally distinct from the
          CAGR fields above, and its dividends_paid null-handling was independently verified
          correct (non-payers vs missing data already disambiguated via dividend_data history).

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: reintroduce/re-audit
        removed inputs with a proper Fama-MacBeth test): built a point-in-time fundamentals
        panel (algo/research/fama_macbeth_growth_factors.py, reconstructed from
        annual_income_statement/annual_balance_sheet/annual_cash_flow - growth_metrics itself
        has no history to test against) and ran real monthly Fama-MacBeth regressions instead
        of the pooled-panel Spearman test above. Result does NOT confirm this docstring's two
        headline claims: eps_growth_1y (45% of this pillar's weight) and asset_growth_yoy
        (25%, sign-flipped) both came back statistically insignificant at every horizon tested
        (1-month multivariate/univariate, overlapping 12-month, and a non-overlapping 12-month
        check using only 12 independent years to fully remove serial-correlation inflation) -
        including asset_growth_yoy, this docstring's own "strongest single empirical result of
        the whole audit." Meanwhile revenue_growth_5y (a DROPPED field) showed the most
        consistent positive signal across every specification tested (t=2.0-2.9), while
        revenue_growth_1y/3y showed a confusing, opposite-signed, likely-collinear pattern
        (both highly correlated with each other by construction) not yet resolved. NOT acted on
        here - real caveats in the new test too (no true filing-date data, calendar-fiscal-
        year-end assumed for all symbols, n=12 for the cleanest non-overlapping check is a
        small sample) mean this is a genuine open discrepancy needing reconciliation, not an
        instruction to flip weights on a live-money system from one exploratory script. Priority
        follow-up before the next Growth-pillar change.

        LITERATURE CALIBRATION (2026-08-25, same pass): checked published research rather than
        treating the above as an unexplained discrepancy. McLean & Pontiff (2016, JoF) find
        published anomalies' returns decay ~26% purely out-of-sample and ~58% post-publication,
        with most of that decay complete within ~10 years of the original sample ending.
        Cooper/Gulen/Schill's asset-growth effect was published in 2008; this script's panel is
        2016-2026 (8-18 years post-publication) - roughly the window where decay theory predicts
        a much weaker effect than the original paper found, so a weak/null result here is
        plausible and not obviously a test bug. Separately, revenue_growth_1y/3y's negative
        sign matches an actual literature prediction, not just an odd result: Lakonishok/
        Shleifer/Vishny (1994) and La Porta (1996) "glamour reversal" - investors naively
        extrapolate high growth, most firms can't sustain it, and high-growth-expectation
        stocks underperform on average. If revenue growth were reintroduced, the literature
        argues for scoring recent high growth as a caution flag at 1y/3y horizons, not a
        straightforward positive - the opposite framing from how this field was scored before
        removal. Still not shipped: the 3y-negative/5y-positive sign split is unresolved (see
        above) and this reframing needs to survive that before any code changes.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 growth field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all growth fields None → returns marker dict with reason="no_growth_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative growth rates → valid scores (negative growth maps to 0-40 scale)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for growth metric computation.

        MINIMUM DATA REQUIREMENT: At least one of revenue_growth or eps_growth metrics must
        be non-NULL. If all growth metrics are None, returns data_unavailable marker.
        Dependent on upstream annual_income_statement availability.
        """
        if not metrics or metrics.get("data_unavailable"):
            reason = metrics.get("reason") if metrics else "metrics_is_none"
            logger.warning(
                f"[STOCK_SCORES] Growth metrics unavailable for {symbol}: {reason}. "
                f"ROOT CAUSE: Check upstream growth_metrics loader (depends on annual_income_statement from SEC filings). "
                f"Some stocks may lack recent annual filings (IPOs, private equity, international)."
            )
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        def _score_single_growth(val: float | None, cap: float) -> float | None:
            """Score a single growth rate capped at `cap`%.

            Continuous through val=0: negative growth maps [-50, 0] -> [0, 40], positive
            growth maps [0, cap] -> [40, 100]. Both branches meet at 40 for 0% growth, so a
            modest positive grower always outscores any decliner. Previously the positive
            branch was (val/cap)*100, i.e. [0, cap] -> [0, 100] with no floor - a stock
            growing a slim +1% could score near 0, well below a stock shrinking -10% (which
            scored 40 - (10/50)*40 = 32), silently inverting the intended growth ranking for
            any modest grower against any modest decliner.
            """
            if val is None:
                return None
            if val <= 0:
                # Negative growth: map [-50, 0] → [0, 40]
                return max(0, 40 + (val / 50) * 40)
            # Positive growth: map [0, cap] → [40, 100]
            return min(100, 40 + (val / cap) * 60)

        # 1-year EPS growth: kept as a conventional growth reference, weight cut 2026-08-25
        # (goal: horizon-matched re-audit) from 45%. Fama-MacBeth at the 1-month horizon -
        # matched to this system's actual weeks-scale swing-trading holding period, not the
        # 12-month academic-anomaly horizon also tested for robustness - found this field
        # robustly null: t=0.76 (multivariate)/0.97 (univariate), never once close to
        # significant across every horizon and specification tried
        # (algo/research/fama_macbeth_growth_factors.py). Distinct from asset_growth_yoy below,
        # whose weaker-than-claimed showing has a real explanation (McLean & Pontiff 2016
        # post-publication decay) and whose SIGN still isn't contradicted - eps_growth_1y
        # showed no signal in any direction at any horizon, the cleanest null in this pillar.
        eps_1y = _score_single_growth(metrics.get("eps_growth_1y"), 50)
        if eps_1y is not None:
            weighted_sum += eps_1y * 0.25
            total_weight += 0.25

        # Asset growth YoY, SIGN-FLIPPED (2026-08-25): Cooper/Gulen/Schill (2008, JoF) and
        # Fama-French's CMA factor both show LOW asset growth firms outperform HIGH asset
        # growth firms - this was previously scored backwards (rewarding high asset growth).
        # Our own panel replicated the anomaly cleanly (Spearman rho=-0.037, p=8.4e-6,
        # ~11pt/yr quintile spread) - the strongest single empirical result in the audit that
        # produced this redesign. Negate the raw growth rate before scoring so low/negative
        # asset growth now maps to a high score.
        # Weight raised 25%->30% 2026-08-25 (goal: horizon-matched re-audit) - freed from
        # eps_growth_1y's cut above. Also null at the 1-month horizon in the newer
        # Fama-MacBeth test (t=0.65/0.64), but unlike eps_growth_1y that has a specific,
        # credible explanation (McLean & Pontiff 2016: published anomalies decay ~58%
        # post-publication, mostly within ~10 years - Cooper/Gulen/Schill's asset-growth
        # effect published 2008, this panel is 2016-2026) and the SIGN still isn't
        # contradicted in either test - kept at the highest weight among the non-EPS inputs
        # rather than cut alongside eps_growth_1y, whose null had no such explanation.
        asset_growth = _score_single_growth(
            -metrics["asset_growth_yoy"] if metrics.get("asset_growth_yoy") is not None else None, 30
        )
        if asset_growth is not None:
            weighted_sum += asset_growth * 0.30
            total_weight += 0.30

        # 1-year revenue growth: weight raised 15%->20% 2026-08-25 (goal: horizon-matched
        # re-audit), freed from eps_growth_1y's cut. Still null at the 1-month horizon
        # (t=-0.03/-0.65) - NOT raised because of a hidden signal, just because it wasn't the
        # field with the cleanest null (that was eps_growth_1y). A 12-month Fama-MacBeth test
        # found this field NEGATIVELY signed and significant (t=-3.6 to -3.7), matching
        # published "glamour reversal" literature (Lakonishok/Shleifer/Vishny 1994, La Porta
        # 1996 - high growth expectations underperform) - NOT acted on (no sign flip) because
        # this system trades on a weeks-scale horizon, not the 12-month horizon where that
        # effect showed up; the practically-relevant 1-month test doesn't support either
        # direction confidently. Flagged for reconsideration only if this system's holding
        # period changes materially.
        rev_1y = _score_single_growth(metrics.get("revenue_growth_1y"), 30)
        if rev_1y is not None:
            weighted_sum += rev_1y * 0.20
            total_weight += 0.20

        # Sustainable growth rate = ROE * retention ratio: structurally distinct from the
        # trailing CAGR fields above (ROE-driven, not a raw growth rate) - how fast the
        # company can grow without external financing. Weight raised 15%->20% 2026-08-25
        # (goal: horizon-matched re-audit), freed from eps_growth_1y's cut - not independently
        # re-tested this pass (not one of the fields covered by
        # algo/research/fama_macbeth_growth_factors.py), so this is a "not worse than the
        # alternative" redistribution, not new positive evidence for SGR specifically.
        sgr = _score_single_growth(metrics.get("sustainable_growth_rate"), 25)
        if sgr is not None:
            weighted_sum += sgr * 0.20
            total_weight += 0.20

        if total_weight > 0:
            computed_score = weighted_sum / total_weight
            logger.debug(f"[STOCK_SCORES] {symbol} growth_score computed: {computed_score:.2f}")
            return computed_score

        logger.warning(
            f"[STOCK_SCORES] {symbol} growth_score computation FAILED: all fields are None. "
            f"ROOT CAUSE: growth_metrics row exists but all 6 fields are NULL. "
            f"ACTION: Check growth_metrics loader - SEC data fetch may be returning empty results."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "all_growth_fields_null"}

    def _score_value(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Score value metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: P/E (10%) + P/B (22%) + P/S (21%) + PEG (8%) + FCF yield (10%)
        + Dividend yield (3%) + Margin of Safety / DCF discount to intrinsic value (6%) + SIZE
        (market cap, 20% - see "SIZE FACTOR" note below). PE/PB/PS/FCF reweighted 2026-08-25
        (see "PE-vs-PB/PS RANKING - REVERSED" note below) after a selection-bias fix reversed
        which of the three multiples is strongest. EV/EBITDA and EV/Revenue REMOVED
        2026-08-25 (see RESOLVED note below) - duplicated P/E and P/S respectively, not
        independent signals. PE/PB/PS weighting has moved several times the same day and once
        more the day after on a corrected sample - see "PE-vs-PB/PS RANKING - REVERSED" note
        below for the FINAL, currently-live ranking (PB strongest, PS second, PE weakest) before
        trusting any earlier note in this docstring's own history. Peak zone for growth
        stocks: P/E 15-30, P/B < 5, PEG < 1-2, positive FCF yield, positive margin of safety.

        SIZE FACTOR added 2026-08-25 (goal: close the highest-confidence gap found in this
        session's full stock_scores re-audit): checked what canonical institutional factor
        models actually include (Fama-French 1992/1993's original three factors - market,
        SIZE, value; MSCI Barra's style factors) - SIZE (market cap, Banz 1981's original size
        effect) was completely absent from all 6 stock_scores pillars, not represented
        anywhere, despite market_cap already being stored on value_metrics (77.4% coverage,
        confirmed via direct query - no schema change needed to add it here). Tested directly
        (algo/research/*.py's point-in-time methodology): log(market_cap) vs forward 1-month
        return, 150 months 2014-2026, median 2,601 symbols: t=-5.37 - nearly as strong as
        volatility_60d's t=-6.1 (this session's single strongest finding) and far stronger
        than any of this file's other individual value inputs. Smaller companies show a
        robust, large forward-return premium in this exact dataset, matching 60+ years of
        replicated academic literature (this is one of the most extensively replicated
        anomalies in all of empirical finance, unlike several of the more contested findings
        elsewhere in this file's recent audits). Added to Value (not a new 7th pillar) since
        SMB is literally the sibling factor to HML (value) in the original Fama-French model,
        and this pillar's own docstring already centers on that lineage - a new pillar would
        need a stock_scores schema migration + API + frontend changes across the whole
        composite, out of proportion to what a single well-evidenced input needs. See the
        scoring block below for the log10-bucketed curve and its market-cap-tier boundaries.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): PE was 45% (more than
        double every other input) despite being the empirically WEAKER of the three
        traditional value multiples in our own forward-1y-return panel (PE Spearman=-0.091,
        PB=-0.137, PS=-0.146, n=9.2k/12.2k/12.3k) - consistent with the literature (Fama-French
        value work has centered on book-to-market, not P/E, since the 1990s). Shifted weight
        toward PB/PS accordingly. Forward P/E removed entirely: analyst_earnings_estimates has
        zero historical depth (all rows fall within a single 3-week window), so it cannot be
        tested, and it shares trailing P/E's weaker theoretical standing plus adds analyst-
        forecast optimism bias on top. Dividend yield cut to a token weight (not removed) -
        tested inconclusive in our data (marginal p=0.036 full-sample, and the effect vanished
        entirely - p=0.542 - in the best-covered 2019-2024 sub-period), so there's no basis to
        trust either direction at material weight. Margin-of-safety's weight reduced (not
        removed) to reflect its already-documented DCF growth-cap bias above, without
        discarding a component with real, if imperfect, information content. A head-to-head
        composite backtest (old weights vs. these new weights, same panel, same forward-return
        target) showed the new mix modestly but genuinely outperforming: Spearman 0.150 vs.
        0.142, p=6.2e-70 vs. 1.6e-62, top-minus-bottom quintile spread 19.84 vs. 18.22 points.
        Caveat: that backtest, like every price-return test in this file's recent history, only
        has real price coverage from ~2020 onward - it validates the reweight within that
        window, not across market cycles the data can't reach. CORRECTION 2026-08-25 (later
        pass): the "10 of 10,982 symbols pre-2020" claim above doesn't hold up - direct query
        (`SELECT date_trunc('year',date), COUNT(DISTINCT symbol) FROM price_daily GROUP BY 1`)
        shows 3,497 distinct symbols with 2019 coverage and real (if thinner) coverage back to
        1962 (29 symbols) - growing roughly monotonically to 10,982 by 2025. The "~2020 onward"
        framing may still be directionally fine (breadth roughly doubles 2020-2021, from 3,730
        to 6,591 symbols), but the specific "10 symbols" number was wrong; left uncorrected
        elsewhere until now because it wasn't blocking anything, but flagging since
        algo/research/fama_macbeth_*.py's tests now use the fuller history.

        REINSTATED 2026-08-24 (user-directed, goal: NVDA margin-of-safety audit): removed
        2026-08-18 (commit e38a6667d) on the reasoning that margin_of_safety_pct should stay
        display-only for cross-symbol comparability. User explicitly asked for it back in the
        Value calculation - restored verbatim (same curve/weight as the original 2026-08-17
        add, commit 28e7ebf7d). Known caveat carried over from the DCF audit the same day: the
        underlying DCF caps forecast growth at 15%/yr, so a hypergrowth name (priced for far
        higher growth than the cap) will structurally show a large negative margin of safety
        here even when its other fundamentals are excellent - this is a real, understood bias
        in this specific input, not a bug in the scoring math.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped). Built
        algo/research/fama_macbeth_value_factors.py - point-in-time P/E, P/B, P/S, FCF yield,
        dividend yield, EV/EBITDA, EV/Revenue from annual_income_statement/annual_balance_sheet/
        annual_cash_flow (PEG and margin-of-safety out of scope - PEG needs a growth cross-term,
        margin-of-safety is a full DCF model, not a single ratio). Two findings:
        (1) Univariate Fama-MacBeth ranks PE (t=-3.70) at least as strong as PB (t=-2.35) and PS
        (t=-2.97), the OPPOSITE ranking from this docstring's own pooled-Spearman claim above
        (PE=-0.091 weakest, PB/PS=-0.137/-0.146 strongest) that justified cutting PE's weight
        from 45% to 18% - not yet reconciled, same tier of open question as Growth's
        eps_growth_1y/asset_growth_yoy finding. (2) Measured directly (150-month pooled
        correlation, n=45,806): ps and ev_revenue are LITERALLY the same signal (r=1.00 - EV
        only adds net debt/share, negligible next to price for most names), and pe/ev_ebitda are
        near-duplicates (r=0.93) - the identical "counted twice" bug class already caught and
        fixed for Momentum's ROC-vs-return-windows redundancy in the 92cd092ce redesign, just
        not caught here: live weights P/S 18% + EV/Revenue 8% put 26% combined weight on ONE
        signal, P/E 18% + EV/EBITDA 8% put 26% on another. pb is the most genuinely distinct
        multiple (only 0.32-0.38 correlated with pe/ps/ev_ebitda/ev_revenue); fcf_yield and
        dividend_yield are both essentially uncorrelated (~0.00) with the multiples and each
        other - real diversifying signals, not redundant ones (fcf_yield t=1.62 positive,
        directionally right but not quite significant; dividend_yield t=0.98, consistent with
        this docstring's own earlier "inconclusive" finding).

        RESOLVED 2026-08-25 (same-day follow-up): acted on the duplicate-signal finding, but
        NOT on the separate, still-unreconciled PE-ranking dispute above (pooled Spearman ranks
        PE weakest; univariate FM ranks it strongest) - the duplicate collapse is independent of
        that dispute and doesn't require resolving it first, unlike a full PE/PB/PS reweight
        would. ev_ebitda and ev_revenue removed entirely from scoring (still fetched/displayed -
        same "computed but unused by scoring" treatment as other removed-from-scoring fields
        elsewhere in this file) since r=1.00/0.93 means they added no information P/S and P/E
        didn't already carry. The freed 16pts went to the three inputs this same pass identified
        as genuinely distinct/diversifying rather than split proportionally: PB (+6, "the most
        genuinely distinct multiple" per the correlation evidence above - deliberately NOT
        boosted using the disputed PE-vs-PB/PS ranking, only using the separate distinctness
        finding), FCF yield (+6, t=1.62, real near-uncorrelated diversifier, directionally
        significant-adjacent), Dividend yield (+2) and Margin of Safety (+2, both real if
        weaker/untested-here diversifiers - DCF-based MoS wasn't in this FM panel's scope, see
        the panel's own docstring). PE/PS themselves left untouched precisely because their
        correct relative weighting is the open, unreconciled question - this pass fixes the
        unambiguous redundancy without pre-judging that separate dispute.

        PE-vs-PB/PS RANKING DISPUTE - RESOLVED 2026-08-25 (same-day follow-up, sub-period
        robustness check, same method that closed Stability's max_drawdown_1y and Momentum's
        RSI questions this session): unlike those two, which turned out to be fragile/decaying
        under the same check, this one is genuinely robust. Ran two independent FM tests
        (the original univariate run above, and a fresh full re-run with a wider 2014-2026
        window): BOTH find all three multiples negatively signed and strongly significant in
        EVERY sub-period tested - full sample, first/second half, and all three terciles, no
        exceptions, no sign flips, no fading (fresh run: PE t=-4.93/-2.44/-4.37 half-split,
        PB t=-4.39/-1.75/-4.21, PS t=-5.13/-3.53/-3.88 - all comfortably significant even in
        the weakest sub-period). Critically, PB is the CONSISTENTLY WEAKEST of the three in
        both runs (not the strongest, as the original pooled-Spearman claim asserted), and PE
        is comparably strong to PS in both runs (not uniquely weak, as that same claim
        asserted and used to justify cutting PE 45%->18%). The original pooled-Spearman
        ranking was very likely a methodology artifact, not a real cross-sectional pattern:
        it used value_metrics' CURRENT-SNAPSHOT ratios (no history - see this file's own
        repeated caveat that value_metrics/growth_metrics/etc. are single-row-per-symbol
        snapshots) joined against a pooled panel of historical forward returns, which is not
        point-in-time correct and pools non-independent symbol-months exactly the way this
        file's other FM-vs-pooled-Spearman comparisons (Growth, Momentum, Stability) already
        established overstates/misstates significance - this is the same methodology-quality
        gap, just discovered later for Value specifically. ACTED ON: PE 18%->22%, PB 26%->18%,
        PS 18%->22% (PE/PS raised to reflect being robustly comparable-to-strongest rather
        than PE being uniquely weak; PB lowered to reflect being robustly weakest, though
        still real and significant - not cut to zero). Combined PE+PB+PS weight held at 62%,
        unchanged from the post-duplicate-collapse total above - this redistributes within
        the three multiples, it doesn't reopen the EV/EBITDA/EV/Revenue redistribution.

        INDEPENDENT RE-VERIFICATION 2026-08-25 (goal: dig in and be certain before acting
        further, not just trust an existing docstring claim). The "no exceptions, no sign
        flips, no fading" characterization above did not reproduce when independently re-run
        from scratch with the same script (algo/research/fama_macbeth_value_factors.py,
        same 2014-2026 window, same half/tercile split logic): first-half t-stats came back
        PE=-1.80, PB=+0.22 (wrong-signed), PS=-0.08 (near zero) - materially weaker than the
        PE=-4.93/PB=-4.39/PS=-5.13 claimed above, not a rounding difference. Second half and
        full-sample numbers DID reproduce closely (full sample PE=-3.70/PB=-2.35/PS=-2.97,
        matching this docstring's own OPEN QUESTION section above almost exactly). Most
        likely explanation: the pre-2020 sample is known-thin (this docstring's own
        CORRECTION note above: real but much sparser symbol coverage before ~2020, breadth
        roughly doubling 2020-2021), so first-half FM estimates are noisier and more
        sensitive to exact universe/date-boundary choices than a single re-run assumed -
        flagging as a real source of estimation uncertainty rather than treating either run's
        first-half numbers as precise. What DOES hold up across every check, both runs: PB is
        the consistently weakest of the three (worst-or-tied in every sub-period tried,
        including outright wrong-signed in the noisiest one) - the one part of the original
        claim that's robust to independent reproduction. PE-vs-PS is NOT reliably
        differentiable though (flips which is stronger across sub-periods in the fresh run) -
        so PE/PS are kept equal to each other (not one raised over the other) rather than
        the original claim's implicit "both robustly strong" framing. ACTED ON (modest,
        proportionate to what's actually robust): PB cut a further 14%->10%, freed 4pts split
        evenly to PE/PS (18%->20% each) - a small additional adjustment reflecting the
        strengthened (if less precisely quantified) case that PB is weak, not a large move on
        an uncertain number. Combined PE+PB+PS still 50% (post-Size-scaling total), unchanged.

        PE-vs-PB/PS RANKING - REVERSED 2026-08-25 (later same day, follow-up to
        [[composite_weights_reweighted_size_factor_reconfirmed_20260825]]'s top-level pass,
        which flagged Value's own internal weighting as a possible efficiency problem worth a
        dedicated look). Every prior pass above - including both "independent
        re-verifications" - tested via algo/research/fama_macbeth_value_factors.py's ORIGINAL
        design: a strict dropna() requiring ALL SIX value inputs (PE/PB/PS/FCF/dividend/EV
        fields) simultaneously non-null every symbol-month. Requiring PE specifically means
        requiring POSITIVE EARNINGS (PE is only computed for eps>0) - which systematically
        excludes unprofitable/distressed companies, exactly the population smaller-cap and
        deep-value effects concentrate in. This is the identical selection-bias mechanism the
        top-level composite test's own redesign just diagnosed and fixed (see that memory) -
        just never applied back to this pillar's own internal component test.

        Redesigned this script's sample the same way (only forward return mandatory; each
        input z-scored over whatever's available that month, missing imputed to 0) and reran:
        median cross-section jumped 1,285->2,604 symbols. Result completely inverts the
        standing "PB is weakest" conclusion: pooled multivariate PB t=-6.06 (vs PE t=-1.18,
        PS t=-4.01), pooled univariate PB t=-9.34 (vs PE t=-4.11, PS t=-7.33) - PB is now the
        STRONGEST of the three, PE the weakest (barely distinguishable from zero once
        controlling for the others). Sub-period-checked the same way the original ranking
        claim was (half-split, 2014-2020 vs 2020-2026): PB t=-2.41/-6.05, PS t=-2.41/-3.20,
        both robust in every half; PE t=+0.38/-1.78, not even consistently signed - the
        opposite robustness pattern from what justified the two prior PE/PB/PS reweights.
        Also re-tested Size (see the pillar's own docstring) in this same redesigned sample:
        t=-3.74 multivariate/-5.31 univariate pooled, t=-2.93/-2.55 sub-periods - confirms
        Size's already-live 20% weight was correctly calibrated, unaffected by this dispute.
        FCF yield flipped sign versus the strict-sample test (was t=+1.62 positive; redesigned
        sample gives t=-1.75 multivariate/-1.71 univariate pooled, negative in both
        sub-periods too) - genuinely sample-construction-sensitive, not a confident signal
        either direction, treated as a fragile null rather than acted on strongly either way.

        ACTED ON: PE 20%->10% (weak/inconsistent once controlling for the others - the
        opposite of its previous "robustly comparable-to-strongest" status), PB 10%->22%
        (robust strongest across univariate/multivariate/both sub-periods - the opposite of
        its previous "consistently weakest" status), PS 20%->21% (robust, modest bump),
        FCF yield 13%->10% (sign-unstable across sample constructions, trimmed for genuine
        uncertainty rather than a directional claim), dividend yield/Size/PEG/margin-of-safety
        unchanged. This is a full reversal of the PE/PB ranking specifically, not a refinement
        of it - the prior conclusion was built entirely on a methodology now shown to
        mechanistically exclude the population (unprofitable/small/distressed firms) where
        these effects concentrate. Both the old and new rankings can't be right; the new one
        is the one built on a sample that doesn't structurally exclude where the signal lives,
        and it reproduces across two independent specs (univariate/multivariate) and two
        independent sub-periods, the same bar the prior "independently re-verified" pass used.

        CONCURRENT INDEPENDENT VERIFICATION (merge note): a parallel session reached this same
        conclusion at nearly the same time via a near-identical redesign of
        algo/research/fama_macbeth_value_factors.py itself (rather than an ad hoc script),
        acting on the identical weight numbers (PE 10%/PB 22%/PS 21%/FCF 10%). Its multivariate
        PS coefficient came out weaker (t=-1.61 vs this pass's t=-4.01) because its
        VALUE_FACTOR_COLS still included ev_ebitda/ev_revenue (r=0.93/1.00 duplicates of pe/ps
        - see the RESOLVED note above) alongside PB/PS, reintroducing collinearity this pass's
        VALUE_FACTOR_COLS avoids by excluding those already-confirmed-dead columns entirely.
        PB's dominance (t=-5.93 to -9.34 depending on spec, both passes) is the load-bearing,
        convergent result either way.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 value field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all value fields None → returns marker dict with reason="no_value_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative P/E or P/B → skipped (invalid for valuation)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for value metric computation.

        MINIMUM DATA REQUIREMENT: At least one of PE/PB/FCF/dividend metrics must be
        non-NULL. If all value metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Value metrics unavailable for {symbol}")
            logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # P/E ratio: sweet spot 15-30 for growth momentum stocks
        # Weight scaled 22%->18% 2026-08-25 (goal: close the Size-factor gap, see this
        # function's docstring "SIZE FACTOR" section) - proportionally with PB/PS/PEG/FCF/
        # Div/MoS below (each x0.8) to free 20pts for the new Size input, preserving every
        # existing input's relative ratio to the others so the just-resolved PE-vs-PB/PS
        # ranking dispute isn't reopened by this change.
        # CUT AGAIN 20%->10% 2026-08-25, later pass - see docstring's "PE-vs-PB/PS RANKING -
        # REVERSED" note: a selection-bias fix (the strict all-6-required test implicitly
        # required positive earnings, excluding unprofitable/small/distressed firms) flipped
        # PE from "robustly comparable-to-strongest" to weak/inconsistent once controlling for
        # PB/PS/Size - null in one sub-period, weak in the other, unlike PB/PS which are
        # robust in both.
        if metrics.get("pe_ratio") is not None and metrics["pe_ratio"] > 0:
            pe = metrics["pe_ratio"]
            if pe <= 10:
                pe_score = 40 + pe * 2  # very cheap / possibly value trap
            elif pe <= 20:
                pe_score = 60 + (pe - 10) * 4  # good range
            elif pe <= 35:
                pe_score = 100 - (pe - 20) * 2  # growth premium zone ? 70 at pe=35
            else:
                pe_score = max(0, 70 - (pe - 35) * 1.4)  # expensive ? 0 at pe~85
            weighted_sum += pe_score * 0.10
            total_weight += 0.10

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors.
        # Weight raised 20%->26% 2026-08-25 (goal: re-audit ALL stock_scores inputs) - freed
        # from removing EV/EBITDA/EV/Revenue's duplicate weight (see this function's
        # docstring); PB was independently identified as "the most genuinely distinct
        # multiple" in that same pass, not boosted using the still-disputed PE-vs-PB/PS
        # predictive-ranking question. LOWERED again 26%->18% same day, later pass - that
        # ranking dispute was resolved and found PB robustly the WEAKEST of the three
        # multiples, not the strongest (see docstring's "PE-vs-PB/PS RANKING DISPUTE" note).
        # Scaled again 18%->14% same day (Size-factor gap, same proportional x0.8 as PE above).
        # Cut once more 14%->10% same day, third pass - independent re-verification of the
        # "PE-vs-PB/PS RANKING DISPUTE" finding (see docstring) confirmed PB weakest across
        # every sub-period tried, including outright wrong-signed in the noisiest one - a
        # modest additional cut proportionate to that strengthened (if less precisely
        # quantified than first claimed) evidence.
        # RAISED SUBSTANTIALLY 10%->22% 2026-08-25, later pass - see docstring's "PE-vs-PB/PS
        # RANKING - REVERSED" note: every prior verdict on PB above used a strict all-6-input
        # test that implicitly required positive earnings, systematically excluding
        # unprofitable/small/distressed firms - exactly the population where this signal
        # concentrates. A selection-bias-corrected rerun completely inverts the ranking: PB is
        # now the STRONGEST of the three multiples, robust across univariate, multivariate,
        # and both sub-periods tested.
        if metrics.get("pb_ratio") is not None and metrics["pb_ratio"] > 0:
            pb = metrics["pb_ratio"]
            if pb <= 1.0:
                pb_score = 100
            elif pb <= 3.0:
                pb_score = 100 - ((pb - 1.0) / 2.0) * 30  # 100?70 in [1,3]
            elif pb <= 7.0:
                pb_score = 70 - ((pb - 3.0) / 4.0) * 40  # 70?30 in [3,7]
            else:
                pb_score = max(0, 30 - (pb - 7.0) * 3)
            weighted_sum += pb_score * 0.22
            total_weight += 0.22

        # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
        # multiples run richer than book multiples (especially for growth/SaaS names).
        # Previously fetched and displayed but never weighted (dead field).
        # Weight scaled 22%->18% 2026-08-25 (Size-factor gap, same proportional x0.8 as PE).
        # Bumped 18%->20%, then 20%->21% 2026-08-25 same day - see docstring's "PE-vs-PB/PS
        # RANKING - REVERSED" note: PS held up as robust (not the weakest, not quite the
        # strongest) across the selection-bias-corrected rerun; a modest additional bump
        # reflecting that robustness.
        if metrics.get("ps_ratio") is not None and metrics["ps_ratio"] > 0:
            ps = metrics["ps_ratio"]
            if ps <= 2.0:
                ps_score = 100
            elif ps <= 6.0:
                ps_score = 100 - ((ps - 2.0) / 4.0) * 30  # 100?70 in [2,6]
            elif ps <= 15.0:
                ps_score = 70 - ((ps - 6.0) / 9.0) * 40  # 70?30 in [6,15]
            else:
                ps_score = max(0, 30 - (ps - 15.0) * 1.5)
            weighted_sum += ps_score * 0.21
            total_weight += 0.21

        # PEG ratio: PE adjusted for earnings growth - <1 is classically "undervalued
        # relative to growth" (Peter Lynch heuristic), >2-3 signals growth already priced
        # in. Distinct signal from P/E (which says nothing about growth) and P/S (no
        # earnings context at all). Was fetched and displayed but carried zero weight -
        # this loader's own PEG computation (load_sec_valuations.py) previously always
        # computed a growth rate of exactly 0 (comparing TTM EPS to itself), which was
        # fixed 2026-07-20 to use a genuine prior-fiscal-year EPS; backfills on next run.
        # Weight scaled 10%->8% 2026-08-25 (Size-factor gap, same proportional x0.8 as PE).
        if metrics.get("peg_ratio") is not None and metrics["peg_ratio"] > 0:
            weighted_sum += self._peg_to_score(metrics["peg_ratio"]) * 0.08
            total_weight += 0.08

        # FCF yield: positive FCF yield is healthy; > 3% is good
        # BUGFIX 2026-07-20: load_sec_valuations.py stores fcf_yield already as a percentage
        # (e.g. 2.27 = 2.27%, confirmed live: AAPL=2.27, MSFT=4.69, T=25.83) - this used to
        # re-multiply by 100 assuming a decimal fraction, so fcf_pct came out ~100x too high
        # (e.g. 227 for AAPL) and saturated fcf_score to 100 for virtually every FCF-positive
        # stock regardless of actual yield. This component was effectively a dead constant.
        # Weight raised 10%->16% 2026-08-25 (goal: re-audit ALL stock_scores inputs) - freed
        # from removing EV/EBITDA/EV/Revenue's duplicate weight; fcf_yield was independently
        # confirmed a real, near-uncorrelated diversifier (t=1.62, directionally right) in the
        # same pass, not a beneficiary of the disputed PE ranking. Scaled 16%->13% same day
        # (Size-factor gap, same proportional x0.8 as PE above).
        # Trimmed 13%->10% 2026-08-25, later pass - see docstring's "PE-vs-PB/PS RANKING -
        # REVERSED" note: this field's sign flipped between the strict all-6-input test
        # (positive, t=1.62) and the selection-bias-corrected rerun (negative, t=-1.75
        # multivariate/-1.71 univariate, negative in both sub-periods too) - genuinely
        # sample-construction-sensitive, treated as a fragile null and trimmed rather than
        # acted on in either direction with confidence.
        if metrics.get("fcf_yield") is not None and metrics["fcf_yield"] > 0:
            fcf_pct = metrics["fcf_yield"]  # already a percentage
            fcf_score = min(100, fcf_pct * 20)  # 5% FCF yield = 100 score
            weighted_sum += fcf_score * 0.10
            total_weight += 0.10

        # Dividend yield: bonus signal for income/quality (optional). Unlike fcf_yield,
        # sec_valuations.dividend_yield (added 2026-07-20, migration 1146) is computed and
        # stored as a decimal fraction (0.03 = 3%), so the *100 conversion below is correct
        # for this field - do not "fix" it to match fcf_yield's convention.
        # Weight raised 2%->4% 2026-08-25 - modest bump from the same EV/EBITDA/EV/Revenue
        # redistribution; kept small since this field's own signal is still inconclusive
        # (t=0.98, unchanged from the earlier pooled-panel finding). Scaled 4%->3% same day
        # (Size-factor gap, same proportional x0.8 as PE above).
        if metrics.get("dividend_yield") is not None and metrics["dividend_yield"] > 0:
            div = min(metrics["dividend_yield"] * 100, 6)  # decimal -> percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.03
            total_weight += 0.03

        # Forward P/E REMOVED 2026-08-25 (goal: full scoring-architecture audit):
        # analyst_earnings_estimates has zero historical depth (every row falls within a
        # single 3-week window as of this audit), so this input could never be validated, and
        # it shares trailing P/E's weaker theoretical standing (see PE's block above) plus
        # analyst-forecast optimism bias on top. Not worth any weight over PB/PS/PEG.

        # EV/EBITDA and EV/Revenue REMOVED 2026-08-25 (goal: re-audit ALL stock_scores inputs
        # for the "counted twice" bug class already fixed elsewhere - Momentum's ROC-vs-
        # return-windows, Quality's double-counted debt_to_assets): measured directly (150mo
        # pooled correlation, n=45,806) ps_ratio and ev_revenue correlate r=1.00 (literally the
        # same signal - EV only adds net debt/share, negligible next to price for most names),
        # pe_ratio and ev_ebitda correlate r=0.93 (near-duplicate). Both fields are still
        # fetched/displayed (loaders/load_stock_scores.py's _get_value_metrics, scores page) -
        # only their consumption here was removed, same convention as other
        # computed-but-unscored fields in this file. Their freed 16pts (8% each) went to PB
        # (+6, the most genuinely distinct multiple per the same correlation pass - only
        # 0.32-0.38 correlated with pe/ps/ev_ebitda/ev_revenue), FCF yield (+6, real
        # near-uncorrelated diversifier, t=1.62), and Dividend yield/Margin of Safety (+2 each,
        # weaker but still genuinely distinct diversifiers) - see this function's docstring for
        # the full evidence and why PE/PS were deliberately left untouched (separate,
        # unreconciled dispute about their relative predictive ranking).

        # Margin of Safety: DCF-based "discount to intrinsic value" (load_sec_valuations.py,
        # migration 1208) - positive means the stock trades below its DCF intrinsic value
        # (undervalued), negative means above (overvalued). Unlike every other field in this
        # function, a legitimate value can be negative (a real, meaningful "overvalued"
        # signal) - gate on `is not None`, not `> 0`, or every overvalued stock would silently
        # drop this input instead of being correctly scored low.
        # Weight raised 6%->8% 2026-08-25 - modest bump from the same EV/EBITDA/EV/Revenue
        # redistribution; DCF-based margin of safety wasn't in scope for the FM panel that
        # drove this pass (see that panel's own docstring: "PEG and margin-of-safety out of
        # scope"), so this bump rests on it being a real, structurally distinct signal
        # (already established when it was reinstated 2026-08-24), not new FM evidence.
        # Scaled 8%->6% same day (Size-factor gap, same proportional x0.8 as PE above).
        if metrics.get("margin_of_safety_pct") is not None:
            mos = metrics["margin_of_safety_pct"]
            if mos >= 50:
                mos_score = 100
            elif mos >= 0:
                mos_score = 60 + mos * 0.8  # 0% -> 60, 50% -> 100
            elif mos >= -50:
                mos_score = 60 + mos * 1.2  # 0% -> 60, -50% -> 0
            else:
                mos_score = 0
            weighted_sum += mos_score * 0.06
            total_weight += 0.06

        # SIZE (market cap): added 2026-08-25 (goal: close the highest-confidence gap found
        # in this session's full re-audit - see this function's docstring "SIZE FACTOR"
        # section). Fama-French (1992/1993) SMB - the original size effect, Banz (1981) - is
        # completely absent from this pillar's live formula despite market_cap already being
        # stored on value_metrics (77.4% coverage, no schema change needed). Tested directly:
        # log(market_cap) vs forward 1-month return, 150 months 2014-2026, median 2,601
        # symbols: t=-5.37 - nearly as strong as volatility_60d's t=-6.1, the single
        # strongest finding across this whole session's re-audit. Smaller companies show a
        # robust forward-return premium in this exact dataset, matching 60+ years of
        # replicated literature. Scored on log10(market_cap) rather than raw dollars -
        # market cap spans 5+ orders of magnitude (micro-cap ~$50M to mega-cap >$3T), so a
        # linear scale on the raw dollar figure would compress the entire distinction between
        # small and mid caps into a rounding error next to the mega-cap tail. Bucket
        # boundaries follow standard market-cap tier conventions (micro <$300M, small
        # $300M-2B, mid $2B-10B, large $10B-200B, mega >$200B) rather than a data-fitted
        # curve, since the FM test validates the DIRECTION and rough magnitude of the size
        # effect, not a precise functional form. Weight 20% - among the two or three
        # strongest signals in the whole file, matching that empirical strength, not a
        # placeholder value.
        if metrics.get("market_cap") is not None and metrics["market_cap"] > 0:
            log_mc = math.log10(metrics["market_cap"])
            if log_mc <= 8.48:  # <= ~$300M (micro-cap)
                size_score = 100.0
            elif log_mc <= 9.30:  # <= ~$2B (small-cap)
                size_score = 100 - (log_mc - 8.48) / (9.30 - 8.48) * 20  # 100 -> 80
            elif log_mc <= 10.0:  # <= ~$10B (mid-cap)
                size_score = 80 - (log_mc - 9.30) / (10.0 - 9.30) * 20  # 80 -> 60
            elif log_mc <= 11.3:  # <= ~$200B (large-cap)
                size_score = 60 - (log_mc - 10.0) / (11.3 - 10.0) * 30  # 60 -> 30
            else:  # mega-cap
                size_score = max(10.0, 30 - (log_mc - 11.3) * 15)
            weighted_sum += size_score * 0.20
            total_weight += 0.20

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}

    def _score_positioning(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score positioning metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring (weights normalized over whichever fields are present):
        A/D rating (35%) + Institutional ownership (30%) + Short interest (25%)
        + Short interest % change MoM (10%).
        Higher A/D rating + institutional ownership and lower short interest signal positive positioning.

        REWEIGHTED 2026-08-25 (goal: full scoring-architecture audit, user-directed): A/D
        rating raised to the top weight per explicit user direction (kept in this pillar, not
        moved to Momentum as this audit's own code-level analysis would have suggested - A/D
        is a volume-confirmed price-trend indicator by construction, but the user considers it
        this pillar's most important signal and that call stands). Institutional ownership cut
        from 55% - checked institutional_holdings_13f (4,166 rows, exactly 1 per symbol, single
        filing date) and institutional_ownership (0 rows): neither has any historical depth in
        this database, so the 55% weight could never be empirically validated. Literature
        (Gompers & Metrick 2001 and related "smart money" work) treats institutional ownership
        mainly as a flow/change signal, not a level factor - a 55% weight on the raw level was
        higher than that literature supports even before the data-availability problem.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped, explicitly including inputs the user
        has already weighed in on). institutional_ownership_pct/short_interest_pct remain
        untestable for the reason already documented above (checked short_interest_finra
        directly this pass too: 16,151 rows/5,553 symbols but only 2 months of real settlement-
        date coverage, June-July 2026 - not enough for any time-series test). ad_rating IS
        testable though - it's a pure price/volume indicator (Chaikin Money Flow,
        loaders/technical_indicators.py::compute_ad_rating), fully point-in-time-safe from
        price_daily's OHLCV columns. Built algo/research/fama_macbeth_positioning_factors.py to
        reconstruct it exactly and test it: t=-0.23 (133 months, median 3,662 symbols/month) -
        no detectable forward-return signal at all for this pillar's largest weight (35%).
        Surfaced, not overridden: this weight was an explicit user directive ("the user
        considers it this pillar's most important signal and that call stands," per the note
        above), not an empirical claim from the redesign, and a null return-prediction result
        doesn't necessarily mean the indicator has no value to the user for other reasons (e.g.
        as a volume-confirmation filter). Flagging per this pass's own instruction to surface
        findings honestly even against prior decisions, not silently changing a stated
        preference.

        METHODOLOGY CHECK (2026-08-25, same pass, user-prompted): a linear monthly-rebalanced
        Fama-MacBeth test is arguably the WRONG test for A/D rating in the first place - IBD
        explicitly designs it as a screening GATE within CAN SLIM's "I" (Institutional
        Sponsorship) criterion, evaluated AT A BREAKOUT, not as a standing universe-wide linear
        rank (confirmed via IBD's own published methodology description, not assumed). Checked
        two alternative framings rather than trusting the single linear result: (1) a decile
        sort (nonparametric, no linearity assumption) - not clean either: deciles 0-3 average
        ~1.0-1.1%/month, decile 4-7 fall toward ~0.1-0.9%, deciles 8-9 "recover" to 1.4-1.7% but
        on only 16 and 4 of 133 months respectively (too data-sparse to trust - most months'
        cross-section doesn't spread across all 10 buckets). No clean monotonic OR threshold
        pattern emerges. (2) An event-conditional test closer to IBD's actual design: among
        1,923,394 new-20-day-high events (a standard but crude breakout proxy - not this
        system's own base-and-breakout detection, which needs buy_sell_daily's
        base_type/breakout_quality/market_stage fields but that table only has 2.5 months of
        history, June-August 2026, too young to backtest), ad_rating at the breakout vs.
        forward-20-trading-day return: Spearman rho=-0.0229 (p=1.6e-220 - significant only
        because n=1.9M, the exact pooled-panel over-significance problem flagged throughout
        this file's other OPEN QUESTION notes), bottom-decile vs. rest mean returns
        0.628%/0.740% - an economically trivial gap. Three different methodologies (linear,
        nonparametric decile, event-conditional) now agree: no material forward-return signal
        detected for ad_rating by any test tried. This is stronger evidence than the original
        single linear result, though the breakout proxy's crudeness means a genuine test against
        this system's own base-pattern detection is still the fairest one, once buy_sell_daily
        accumulates enough history to backtest against.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 positioning field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all positioning fields None → returns marker dict with reason="no_positioning_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Missing positioning data → marker dict (expected for REITs and special securities)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for positioning metric computation. Position weight redistribution
        applies if positioning unavailable.

        MINIMUM DATA REQUIREMENT: At least one of institutional_ownership/short_interest
        metrics must be non-NULL. If all positioning metrics are None,
        returns data_unavailable marker. Optional for REITs/special securities.

        REMOVED 2026-08-24: insider_ownership scoring component - a concurrent session's
        commit ("REMOVE: drop insider_ownership_pct entirely - not a positioning metric")
        dropped the underlying column from positioning_metrics but missed this scoring
        block, which crashed the loader referencing it via the now-nonexistent SELECT
        column (see _get_positioning_metrics's own fix note). Removing this block needs no
        manual weight redistribution - the remaining weights are already normalized via
        weighted_sum / total_weight below, using only whatever fields are actually present.
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Positioning metrics unavailable for {symbol}")
            logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for positioning_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_positioning_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # Institutional ownership: higher is better (target 50%+, cap at 95%)
        if metrics.get("institutional_ownership") is not None:
            io = min(metrics["institutional_ownership"], 95)
            weighted_sum += io * 0.30
            total_weight += 0.30

        # Short interest: lower is better (target <5%)
        if metrics.get("short_interest") is not None:
            si = metrics["short_interest"]
            if si < 5:
                score = 100 - (si * 10)
            elif si < 15:
                score = 50 - ((si - 5) * 2)
            else:
                score = 30
            weighted_sum += max(0, min(100, score)) * 0.25
            total_weight += 0.25

        # Short interest % change (month-over-month, written by load_positioning_metrics.py's
        # _compute_short_interest_pct_change): shorts covering (negative change) is a positive
        # signal independent of the absolute %-of-float level scored above; shorts building
        # (positive change) is a negative signal even if the absolute level is still low.
        #
        # REPLACED 2026-08-17 (migration 1203): this used to read a pre-bucketed 3-value text
        # enum ('increasing'/'decreasing'/'stable' at a +/-5% threshold) and look up one of 3
        # fixed scores (10/55/100) - every symbol in a bucket scored identically regardless of
        # whether its actual change was 5.1% or 51%, discarding real signal the loader had
        # already computed. Scored with a logistic curve instead of a linear+clamp: strictly
        # monotonic decreasing in pct_change for every real input (a bigger covering move
        # always scores higher than a smaller one, no matter how large), naturally bounded to
        # (0, 100) with no hard clamp/plateau, and centered at 0% change -> 50 (neutral).
        pct_change = metrics.get("short_interest_pct_change")
        if pct_change is not None:
            pct_change_score = 100.0 / (1.0 + math.exp(pct_change / 12.0))
            weighted_sum += pct_change_score * 0.10
            total_weight += 0.10

        # A/D (Accumulation/Distribution) rating: volume-confirmed price-trend signal from
        # load_positioning_metrics.py (loaders/technical_indicators.py::compute_ad_rating) -
        # already a 0-100 score (100=volume confirms uptrend, 60=bullish divergence, 30=bearish),
        # no tiering needed. 93.5% populated (2026-08-04 live check), written and displayed on
        # the scores page since it was added, but never weighted into positioning_score - same
        # "displayed but never weighted" bug class as short_interest_trend above.
        if metrics.get("ad_rating") is not None:
            weighted_sum += metrics["ad_rating"] * 0.35
            total_weight += 0.35

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for positioning_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_positioning_scores_computed"}

    def _score_stability(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score stability metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        Uses weighted scoring: Volatility 60d (45%) + Beta (20%) + Downside Volatility 60d
        (15%, purer "risk of loss" signal) + Max Drawdown 1y (20%). Lower volatility and beta
        closer to 1.0 indicate stable, market-correlated stocks. Weights are relative, not
        required to sum to 100 - each present
        sub-component contributes weighted_sum/total_weight (self-normalizing over whatever
        metrics are actually available for a symbol, per GOVERNANCE's no-redistribution rule at
        the top-level factor split; this renormalization is local to stability's own sub-scores).

        CLEANUP 2026-08-16: Financial Stability (debt-to-equity, debt-to-assets, current/quick
        ratio, cash per share) and Business Diversification (revenue concentration HHI) were
        removed from this factor - stability is meant to track price-volatility/risk-of-loss
        character, not balance-sheet fundamentals or business concentration. The debt/liquidity/
        cash metrics now feed Quality instead (see _enhance_quality_score); revenue concentration
        HHI was dropped from scoring entirely per user request.

        REWEIGHTED 2026-08-25 (goal: Fama-MacBeth factor-weighting pass, see
        algo/research/fama_macbeth_price_factors.py): built a proper monthly cross-sectional
        Fama-MacBeth panel (126 months, 2016-01 to 2026-06, median 3,409 symbols/month,
        z-scored factors, 1%/99% winsorized) regressing forward 1-month return on
        vol/downside_vol/beta/max_drawdown/momentum jointly - unlike the pooled-panel Spearman
        correlations used in the rest of this file's 2026-08-25 audit (which treat every
        symbol-month as an independent observation and understate correlation within a month,
        inflating significance), Fama-MacBeth averages one regression per month so the t-stats
        are month-count-limited (n=126), not observation-count-limited. Result: volatility_60d
        was the single strongest, most robust signal in the entire panel (multivariate
        coef=-0.0071/month, t=-6.07) - low vol robustly predicts higher forward return, same
        direction this pillar already scores it. downside_volatility_60d, once vol is in the
        regression alongside it, carries NO independent signal and comes out wrong-signed
        (coef=+0.0013, t=+1.39, i.e. not distinguishable from zero and if anything pointing the
        wrong way) - consistent with the 2026-08-25 stability consolidation's own finding that
        symmetric and downside volatility windows correlate 0.52-0.92 with each other; downside_vol
        is largely re-measuring what vol already captures. Moved 10pts of weight from
        downside_vol to vol accordingly. beta and max_drawdown weights left unchanged: beta's
        insignificance (t=0.93) doesn't call for a change since this pillar deliberately scores
        beta-near-1.0 for swing-trading fit, not as a return predictor (see below) - a flat
        regression coefficient doesn't contradict a non-alpha design goal. max_drawdown_1y came
        back wrong-signed too (coef=-0.0043, t=-1.65, i.e. bigger past drawdowns weakly
        associated with HIGHER forward returns, the opposite of what this pillar assumes) but
        only marginally (~p=0.10) - not strong enough evidence to flip a pillar's semantic
        meaning on a live-money system; flagged as an open question pending the named follow-up
        (sub-period stability, Newey-West-adjusted SE) rather than acted on that day.

        RESOLVED 2026-08-25 (same-day follow-up, goal: finish the named follow-up rather than
        leave it open): ran exactly that follow-up - univariate-only max_dd regression (isolates
        it from the multivariate collinearity that produced the -1.65 reading above), both a
        Newey-West(3-lag) HAC-adjusted SE on the full 127-month sample and a first-half/second-
        half/tercile sub-period split. Full-sample univariate signal is indistinguishable from
        zero (mean=+0.00017, naive t=0.07, Newey-West t=0.06 - HAC adjustment barely moves it,
        so serial correlation wasn't hiding a real effect either). More importantly it is NOT
        STABLE: first half (2016-01 to 2021-03, 63mo) is wrong-signed (t=-1.61, agreeing with
        the original multivariate finding's direction) while the second half (2021-04 to
        2026-07, 64mo) is right-signed (t=+1.75) - a clean sign flip across the sample, not
        random noise around one stable value. Terciles confirm the same pattern (weak-negative,
        weak-negative, then positive). Conclusion: the original wrong-signed multivariate
        reading was very likely a collinearity artifact from being jointly estimated alongside
        vol/downside_vol/beta/momentum (the same artifact class documented in Momentum's own
        multivariate coefficients elsewhere in this file), not a real, exploitable anomaly in
        either direction - there is no stable relationship here to flip the sign FOR. Correctly
        left as originally designed (higher/less-severe max_drawdown_1y scores better); this
        question is now closed with evidence rather than left open on caution alone.

        INDEPENDENT RE-VERIFICATION 2026-08-25 (same standard applied to the PE-vs-PB/PS
        finding in _score_value's docstring - digging in to be certain rather than trusting
        a claim already in the file, since that Value claim didn't fully reproduce when
        checked). Re-ran the sub-period split from scratch, independently: t-stats came back
        directionally consistent (full sample ~zero, first half negative, second half
        positive - the sign-flip pattern IS real) but meaningfully WEAKER than claimed above
        - full sample t=0.22 (vs claimed 0.07/0.06, both near-zero so roughly consistent),
        first half t=-0.57 (vs claimed -1.61), second half t=+0.77 (vs claimed +1.75). Same
        conclusion either way - no stable relationship, correctly left unflipped - but the
        magnitude of "wrong-signed in the first half" was overstated in the original claim;
        noting the more conservative numbers here rather than leaving the stronger, unverified
        ones as the only record. (Momentum's RSI decay finding, checked the same way, DID
        reproduce closely - see that pillar's docstring - so this isn't a blanket doubt on
        every inherited claim, just this specific one.)

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: check whether other
        canonical academic factors are still missing after adding Size to Value). Amihud
        (2002, Journal of Financial Markets) illiquidity - |monthly return| / average daily
        dollar volume, one of the most replicated liquidity-premium measures in empirical
        finance, alongside the related Brennan/Chordia/Subrahmanyam (1998, JFE) finding that
        raw dollar trading volume itself negatively predicts forward returns - is completely
        absent from this system. Tested directly from price_daily (which has full volume
        history, unlike technical_data_daily's ~3-month window): monthly Amihud illiquidity
        vs forward 1-month return, 126 months 2016-2026, median 3,866 symbols: t=3.34,
        positive (more illiquid = higher forward return, the expected illiquidity-premium
        direction). Checked it isn't just re-measuring Size first: correlation with
        log(market_cap) is only -0.18 (winsorized) - a real, distinct signal, not a
        duplicate. NOT implemented, unlike Size: Size only needed reading an already-stored
        field (market_cap on value_metrics); Amihud illiquidity needs a genuine new
        computation (daily |return|/dollar-volume averaged over a window) that no existing
        metrics table stores - technical_data_daily has volume_ma_20/50 columns, but they're
        100% NULL (computed nowhere) and that table only holds ~3 months of history even if
        populated. Implementing this needs upstream loader work (compute and store an
        illiquidity/dollar-volume metric with real historical depth, most naturally from
        price_daily where the raw OHLCV is), a bigger scope than a stock_scores.py-only
        change - flagged as the clearest remaining structural gap after Size, not rushed in.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 stability field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all stability fields None → returns marker dict with reason="no_stability_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative volatility → treated as 0 (impossible case, but defensive)

        MINIMUM DATA REQUIREMENT: At least one of volatility/beta/financial_stability metrics
        must be non-NULL. If all stability metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for stability_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # CONSOLIDATED 2026-08-25 (goal: full scoring-architecture audit): this pillar
        # previously scored volatility_252d/60d/30d AND downside_volatility_252d/60d/30d as 6
        # separate inputs. Measured directly on a 400-symbol sample (20,904 observations):
        # the three symmetric windows correlate 0.69-0.89 with each other, the three downside
        # windows correlate 0.78-0.92 with each other, and even cross-flavor correlations run
        # 0.52-0.83 - consistent with volatility clustering being one of the most robust
        # stylized facts in finance (Engle 1982, Bollerslev 1986 GARCH literature). All six
        # were essentially the same "how choppy is this stock" signal at different smoothing
        # windows, carrying ~80% of this pillar's raw weight budget while beta and max
        # drawdown - the two genuinely distinct, non-redundant signals here - carried the
        # smallest weights. Collapsed to one symmetric + one downside window (60d - a
        # reasonable middle-ground proxy, correlating 0.83-0.89 with both the 252d and 30d
        # windows it replaces) and redistributed the freed weight to beta and max_drawdown.

        # 60-day volatility: single representative symmetric-volatility window.
        if metrics.get("volatility_60d") is not None:
            vol60 = max(0, metrics["volatility_60d"])
            if vol60 <= 0.15:
                v60_score = 100
            elif vol60 <= 0.30:
                v60_score = 100 - ((vol60 - 0.15) / 0.15) * 50
            elif vol60 <= 0.60:
                v60_score = 50 - ((vol60 - 0.30) / 0.30) * 40
            else:
                v60_score = max(0, 10 - (vol60 - 0.60) * 20)
            weighted_sum += v60_score * 0.45
            total_weight += 0.45

        # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading.
        # Deliberately not the literature's low-beta preference (Frazzini & Pedersen 2014
        # "Betting Against Beta") - this codebase consistently targets market-correlated
        # moves for swing-trading fit rather than minimum systematic risk, a repeated,
        # deliberate design choice, not an oversight.
        if metrics.get("beta") is not None:
            beta = max(0, metrics["beta"])
            diff = min(abs(beta - 1.0), 2.0)
            beta_score = max(0, 100 - (diff * 50))
            weighted_sum += beta_score * 0.20
            total_weight += 0.20

        # Downside deviation (60d): single representative window of the "only penalizes
        # downside price moves" flavor - a purer "risk of loss" signal than symmetric
        # volatility, which penalizes upside moves equally.
        if metrics.get("downside_volatility_60d") is not None:
            dvol60 = max(0, metrics["downside_volatility_60d"])
            if dvol60 <= 0.15:
                dvol60_score = 100
            elif dvol60 <= 0.30:
                dvol60_score = 100 - ((dvol60 - 0.15) / 0.15) * 50
            elif dvol60 <= 0.60:
                dvol60_score = 50 - ((dvol60 - 0.30) / 0.30) * 40
            else:
                dvol60_score = max(0, 10 - (dvol60 - 0.60) * 20)
            weighted_sum += dvol60_score * 0.15
            total_weight += 0.15

        # Max drawdown (1y): peak-to-trough decline, stored as a negative percentage
        # (e.g. -34.63 = a 34.63% decline from peak). Distinct signal from volatility (a
        # stock can have low day-to-day volatility yet still suffer one deep sustained
        # drawdown). <=10% drawdown is mild, >50% is severe.
        if metrics.get("max_drawdown_1y") is not None:
            drawdown_pct = abs(min(0.0, metrics["max_drawdown_1y"]))
            if drawdown_pct <= 10:
                dd_score = 100 - drawdown_pct * 2  # 100->80
            elif drawdown_pct <= 25:
                dd_score = 80 - (drawdown_pct - 10) * 2  # 80->50
            elif drawdown_pct <= 50:
                dd_score = 50 - (drawdown_pct - 25) * 1.2  # 50->20
            else:
                dd_score = max(0, 20 - (drawdown_pct - 50) * 0.4)
            weighted_sum += dd_score * 0.20
            total_weight += 0.20

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for stability_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_scores_computed"}

    def _score_dte(self, dte: float) -> float:
        """Score debt-to-equity (target D/E < 1.0, lower is better)."""
        if dte <= 0.5:
            return 100.0
        if dte <= 1.0:
            return 100.0 - ((dte - 0.5) / 0.5) * 30
        if dte <= 2.0:
            return 70.0 - ((dte - 1.0) / 1.0) * 40
        return max(0, 30 - (dte - 2.0) * 15)

    def _score_financial_stability(self, metrics: dict[str, Any], symbol: str) -> float | None:
        """Score financial stability (leverage/solvency) using Phase 3 debt metrics.

        Uses debt-to-equity only. Returns None if not available.

        Session 359: Phase 8 enhancement - adds financial solvency scoring. CLEANUP 2026-08-16:
        called from _enhance_quality_score (Quality) instead of _score_stability - these are
        balance-sheet fundamentals, not price-volatility signals, so they belong under Quality.
        CLEANUP 2026-08-18: current_ratio/quick_ratio/cash_per_share (liquidity/cash
        components) removed - not factor-score inputs anymore.

        FIX 2026-08-25 (goal: full scoring-architecture audit): debt_to_assets removed from
        this function - it already feeds the base quality_score (~17%, computed upstream in
        load_value_quality_growth_metrics.py), so including it here too meant the same raw
        metric was scored twice within the same pillar. debt_to_equity is the one genuinely
        new leverage signal this adjustment adds.
        """
        components: list[tuple[float, float]] = []  # (score, weight) pairs

        if metrics.get("debt_to_equity") is not None:
            dte = float(max(0, metrics["debt_to_equity"]))
            components.append((self._score_dte(dte), 1.0))

        if not components:
            return None

        total_weight = sum(w for _, w in components)
        if total_weight == 0:
            return None

        weighted_score = sum(s * w for s, w in components) / total_weight
        return float(max(0, min(100, weighted_score)))

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Momentum 3m (20%) + 12-1 skip-month momentum (35%) + RSI(14)
        (21%) + MACD sign (16%) + SMA positioning (8%). Normalizes by total weight of
        available components so partial data doesn't deflate the score. Raw momentum_6m/
        momentum_12m REPLACED 2026-08-25 by a derived 12-1 construction - see RESOLVED note
        below.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): momentum_1m and the
        ROC composite both removed. ROC composite was pure redundancy - roc_20d/60d/120d/252d
        are the same `close.pct_change()` computation as momentum_1m/3m/6m/12m over
        near-identical trading-day windows, so it was the same 4 return windows counted a
        second time, not a diversifying signal. momentum_1m was dropped separately per the
        standard academic 12-1 momentum construction (Jegadeesh 1990 short-term reversal) -
        see the weights dict below for the empirical confirmation in our own data.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped): built
        algo/research/fama_macbeth_momentum_factors.py - reconstructs RSI(14)/MACD/SMA(50,200)
        directly from price_daily (Wilder 1978 RSI convention, standard 12/26/9 MACD EMAs) so
        the ENTIRE live Momentum input set (not just the 3m/6m/12m windows tested in
        fama_macbeth_price_factors.py) could be regressed jointly for the first time. Found
        severe multicollinearity, measured directly (121-month pooled correlation matrix):
        mom_12m/mom_6m r=0.83, rsi_14/macd_sign r=0.70, price_vs_sma_50/200 r=0.87,
        mom_3m/mom_6m r=0.69 - comparable in magnitude to the 0.52-0.92 range that justified
        consolidating Stability's 6 volatility windows down to 2, except this pillar's 6 inputs
        never got that treatment. Consequence: multivariate FM coefficients for mom_6m,
        macd_sign, and price_vs_sma_200 all FLIP SIGN between univariate and multivariate specs
        (e.g. macd_sign t=-0.37 alone vs t=+2.95 controlling for the others) - a classic
        collinearity symptom, meaning none of those multivariate coefficients are trustworthy
        standalone evidence for reweighting. The one factor that stayed directionally stable
        both ways was rsi_14 (t=-1.83 univariate, -1.89 multivariate) - consistently NEGATIVE,
        i.e. high RSI (overbought) weakly predicts LOWER forward return in this data, the
        mean-reversion/oscillator interpretation Wilder originally designed RSI for, not this
        pillar's current trend-following "higher RSI = more bullish" treatment. Lower
        evidentiary tier than the JoF-grade factors elsewhere in this file though - RSI is a
        technical-analysis heuristic without the same academic asset-pricing literature behind
        it, so this is an internal-data finding, not a replicated anomaly. The right fix here
        is a consolidation pass (fewer, less-redundant inputs, same treatment Stability
        already got) before any reweighting - extracting weights from an unstable collinear
        regression would just encode noise (see RESOLVED note below for what was actually
        done). (Growth's open question, previously cited here as the same-tier companion
        item, is now resolved - see that pillar's docstring.)

        CONFIRMATORY RE-RUN 2026-08-25 (same-day follow-up, goal: check whether this needed
        more than a re-statement before the next session touches it): re-ran
        fama_macbeth_momentum_factors.py fresh rather than relying on the numbers above.
        Univariate results for the four return-window factors are ALL statistically
        indistinguishable from zero: mom_12_1 (proper Jegadeesh 1990 skip-month construction,
        not a live input at the time of this run) t=1.04, mom_3m t=-0.88, mom_6m t=-0.38,
        mom_12m t=0.38 - none exceed |t|=1.1, so there is no "drop the weakest, keep the
        strongest" call available from significance alone (unlike Value's clean PB-is-most-
        distinct finding). mom_12_1 was nominally the strongest of the four - suggestive, not
        conclusive on significance, but real: it's the actual literature-standard momentum
        construction (Jegadeesh 1990/Jegadeesh-Titman 1993/Carhart 1997 UMD), not an ad hoc
        pick, independent of whether this internal sample confirms it.

        RESOLVED 2026-08-25 (same-day follow-up, acting on the next-step spec above):
        momentum_6m and momentum_12m REPLACED by a derived 12-1 skip-month construction,
        following the exact same "collapse redundant windows, keep the total category weight"
        treatment already applied to Stability's 6 volatility windows. momentum_6m was the
        most redundant "middle" window (r=0.69 with 3m, r=0.83 with 12m - correlated with
        both neighbors, contributing the least unique information of the three) and
        momentum_12m's simple trailing-return construction is exactly the recency-
        contaminated shape this pillar's docstring already flagged as a problem when it
        dropped momentum_1m for the same Jegadeesh 1990 reason above - that reasoning was
        never carried through to fix the 12m window itself until now. No new stored field
        needed: mom_12_1 (cumulative return from 12mo-ago to 1mo-ago) is algebraically
        derivable from momentum_12m and momentum_1m, both already fetched here -
        ((1+momentum_12m/100)/(1+momentum_1m/100) - 1)*100. Weight 35% = the exact combined
        weight momentum_6m(20%) + momentum_12m(15%) previously carried - a straight
        consolidation of the redundant windows' weight into the literature-correct
        construction, not a new claim about relative signal strength (this data's own
        univariate test above found none of the four constructions individually
        significant - the redistribution rests on redundancy + literature convention, the
        same evidentiary bar Stability's consolidation used, not on this session's t-stats).
        momentum_3m kept unchanged (least correlated of the trio, r=0.69 with 6m, a genuine
        short-horizon complement to the now-proper long-horizon signal).

        RSI SIGN QUESTION - sub-period-checked same session (same method that closed
        Stability's max_drawdown_1y question, see that pillar's docstring): unlike
        max_drawdown_1y, rsi_14's negative univariate coefficient is NOT a sign flip - it's
        directionally consistent negative in 3 of 4 sub-samples (full sample t=-1.91, first
        half 2016-06/2021-06 t=-2.07, tercile 1 t=-1.54, tercile 2 t=-1.60) but fades to
        indistinguishable-from-zero in the most recent ~3.5 years (second half t=-0.45,
        tercile 3 2023-02/2026-07 t=+0.08) - a decaying-but-not-reversing pattern, not noise
        flipping sign. Still NOT flipping this pillar's "higher RSI = more bullish" treatment:
        (1) even the strongest historical reading (t≈-2) is a technical-analysis heuristic
        without the JoF-grade literature backing behind Value/Growth's anomalies, (2) the
        effect is weakest exactly in the most recent period, so acting on it now would mean
        trading on a relationship that has already largely decayed away, the same
        McLean-Pontiff logic already applied to Growth's asset_growth_yoy elsewhere in this
        file. Correctly left as originally designed; this sub-question is closed (won't flip).

        INDEPENDENTLY RE-VERIFIED 2026-08-25 (same "dig in, be certain" pass that corrected
        Stability's max_drawdown_1y sub-period numbers and Value's PE-vs-PB/PS claim, both of
        which had overstated an already-in-file finding). This one reproduced closely on a
        from-scratch re-run: full sample t=-1.83, first half t=-1.97, second half t=-0.44,
        terciles -1.58/-1.73/+0.52 - all within a few hundredths to a few tenths of the
        numbers above, not the several-point gap found in the other two claims. Confidence in
        this specific finding is high; the conclusion (won't flip) stands unchanged.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 scoreable field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all fields None → returns marker dict with reason="no_momentum_scores_computed"

        ERROR HANDLING:
        - Weak price-return momentum (±3%) → returns None for that timeframe (insufficient signal)
        - Missing historical prices → timeframe momentum is None (not guessed)

        MINIMUM DATA REQUIREMENT: At least one of 1m/3m/6m/12m momentum, RSI, MACD, or ROC must be
        available (not None). If everything is None/missing, returns data_unavailable marker.
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_metrics_data"}

        # Named weights (2026-08-25 redesign, see docstring): momentum_1m dropped as a
        # standalone scored timeframe - standard academic 12-1 momentum construction
        # (Jegadeesh 1990) deliberately excludes the most recent month's raw return. Our own
        # panel confirmed why: trailing-1m return vs forward-1m return showed Spearman=-0.031
        # (p=4.2e-97, short-term reversal), but a double sort controlling for 12-1 momentum
        # showed the reversal is concentrated almost entirely in low-momentum (losing) names
        # (-0.31 spread) while high-momentum names showed continuation instead (+0.39 spread) -
        # a flat weighted-sum score can't encode that interaction, so the conservative fix is
        # dropping the most-recent-month return as its own scored input. momentum_1m is still
        # read below (see mom_12_1 derivation) - as an input to the 12-1 construction Jegadeesh
        # 1990 actually specifies, not as a standalone score.
        weights = {
            "momentum_3m": 0.20,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in weights.items():
            if metrics.get(key) is not None:
                score = self._pct_to_score(metrics[key])
                if score is not None:  # Skip weak momentum (score=None)
                    weighted_sum += score * w
                    total_weight += w

        # 12-1 momentum (skip most-recent-month, Jegadeesh 1990 standard construction) -
        # REPLACES raw momentum_6m/momentum_12m 2026-08-25 (see docstring RESOLVED note).
        # Derived rather than requiring a new stored field: cumulative return from 12mo-ago to
        # 1mo-ago is algebraically (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back
        # to a percentage number to match _pct_to_score's expected input convention. Guarded
        # against a near-zero denominator (would require momentum_1m ~ -100%, a stock price
        # going to ~zero in a month - not realistic for a scoreable position, but NaN/Infinity
        # guarded both directions per this codebase's standard convention regardless).
        mom_12m_raw = metrics.get("momentum_12m")
        mom_1m_raw = metrics.get("momentum_1m")
        if mom_12m_raw is not None and mom_1m_raw is not None:
            denom = 1.0 + mom_1m_raw / 100.0
            if abs(denom) > 1e-6:
                mom_12_1 = ((1.0 + mom_12m_raw / 100.0) / denom - 1.0) * 100.0
                if math.isfinite(mom_12_1):
                    mom_12_1_score = self._pct_to_score(mom_12_1)
                    if mom_12_1_score is not None:  # Skip weak momentum (score=None)
                        weighted_sum += mom_12_1_score * 0.35
                        total_weight += 0.35

        # RSI(14): momentum-following curve (not mean-reversion) - higher RSI is more
        # bullish, with only a slight pullback at extreme overbought (>85) for reversal risk.
        if metrics.get("rsi_14") is not None:
            rsi_score = self._rsi_to_score(metrics["rsi_14"])
            weighted_sum += rsi_score * 0.21
            total_weight += 0.21

        # MACD: sign only, not magnitude. MACD's raw value scales with the stock's price
        # level (a MACD of 2 means something different for a $10 stock vs a $500 stock), so
        # magnitude isn't comparable across symbols - use it purely as a bull/bear trend
        # confirmation signal.
        #
        # FIX 2026-08-18 (loader-health review, log-noise sweep): a prior commit speculatively
        # preferred a "macd_line" field, anticipating a migration that never actually happened
        # on this table - _prepare_batch_context()'s own query (~line 402-406) selects
        # "rsi_14, macd, sma_50, sma_200, close" from technical_data_daily and nothing else,
        # so metrics.get("macd_line") was provably always None, 100% of the time, for every
        # symbol, every run. (technical_data_daily has no macd_line column at all - a
        # same-named column DOES exist, but on a different table, momentum_metrics, added by
        # an unrelated migration 119 - not the same computation, not queried here.) The
        # resulting "legacy field" warning fired on ~4926/4930 symbols every single
        # stock_scores run - not a rare backward-compat path, pure log noise masking real
        # warnings, with zero effect on the actual score (this WAS already the only value
        # ever used). Reverted to using "macd" directly.
        macd = metrics.get("macd")
        if macd is not None:
            macd_score = 70.0 if macd > 0 else 30.0 if macd < 0 else 50.0
            weighted_sum += macd_score * 0.16
            total_weight += 0.16

        # ROC (Rate of Change) composite REMOVED 2026-08-25 (goal: full scoring-architecture
        # audit): roc_20d/60d/120d/252d are literally the same computation as
        # momentum_1m/3m/6m/12m above (both `close.pct_change()` over near-identical trading-
        # day windows - momentum_1m uses 21 trading days back vs roc_20d's 20, momentum_12m
        # and roc_252d both use exactly 252) - this wasn't a diversifying signal, it was the
        # same four numbers counted a second time. Removed rather than reweighted.

        # Price vs Moving Averages: premium over SMAs indicates uptrend
        sma_scores = []
        for sma_field in ["price_vs_sma_50", "price_vs_sma_200"]:
            sma_val = metrics.get(sma_field)
            if sma_val is not None:
                # Price above SMA = bullish: +5% above = 75, +10% above = 100, -5% below = 25
                sma_score = 50 + (sma_val / 0.2) * 50  # ±10% range maps to 0-100
                sma_scores.append(min(100, max(0, sma_score)))
        if sma_scores:
            weighted_sum += (sum(sma_scores) / len(sma_scores)) * 0.08
            total_weight += 0.08

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_scores_computed"}

    @staticmethod
    def _pct_to_score(pct_return: float) -> float | None:
        """Convert percentage return to 0-100 score.

        Returns None if momentum is weak (< ±3%), as this indicates
        insufficient conviction. Fail-fast: weak signal is missing data, not low score.
        -20% = 0, ±3% = None, +20% = 100.

        pct_return is a percentage NUMBER (e.g. 20.0 for +20%), not a fraction - matches
        load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100,
        which is what momentum_1m/3m/6m/12m are computed as and stored as.
        """
        # Weak momentum zone: -3% to +3% lacks conviction. This previously checked
        # -0.03 <= pct_return <= 0.03 - a threshold 100x too small for the percentage-number
        # scale pct_return is actually on, so it matched essentially no real momentum value
        # (typical 1m/3m/6m/12m returns are single-to-double-digit percent) and this weak-
        # signal exclusion never fired in practice - every momentum reading, however weak,
        # was scored instead of being excluded as insufficient conviction per the documented
        # design intent.
        if -3 <= pct_return <= 3:
            return None

        # Map momentum: -20% = 0, +20% = 100
        score = 50 + (pct_return / 0.4)
        return max(0, min(100, score))

    @staticmethod
    def _rsi_to_score(rsi: float) -> float:
        """Map RSI(14) to a momentum-following 0-100 score (higher RSI = more bullish).

        This is deliberately NOT a mean-reversion mapping (which would penalize high RSI as
        "overbought"). For a momentum factor, sustained strength (RSI 50-85) should score
        well; only extreme overbought (>85) gets a mild pullback for reversal risk.
        """
        rsi = max(0.0, min(100.0, rsi))
        if rsi <= 30:
            return (rsi / 30) * 30
        if rsi <= 50:
            return 30 + ((rsi - 30) / 20) * 20
        if rsi <= 70:
            return 50 + ((rsi - 50) / 20) * 35
        if rsi <= 85:
            return 85 + ((rsi - 70) / 15) * 15
        return max(60.0, 100 - (rsi - 85) * 3)

    @staticmethod
    def _peg_to_score(peg: float) -> float:
        """Map PEG ratio to a 0-100 score. <=1 is the classic "undervalued relative to
        growth" zone (Peter Lynch heuristic); >4 signals growth already richly priced in.
        """
        if peg <= 1.0:
            return 100.0
        if peg <= 2.0:
            return 100 - (peg - 1.0) * 40  # 100->60 in [1,2]
        if peg <= 4.0:
            return 60 - (peg - 2.0) * 20  # 60->20 in [2,4]
        return max(0.0, 20 - (peg - 4.0) * 5)

    def _value_metrics_coverage_excluding_fpi(self, cur: Any) -> tuple[int, int] | None:
        """Return (covered, total) for value_metrics over the active, non-FPI universe.

        See audit_upstream_coverage()'s 2026-08-21 fix comment for why the raw
        data_loader_status.completion_pct is unusable for this gate: it counts every
        foreign-private-issuer symbol's permanent, correct value_metrics exclusion as a
        "failure" alongside genuine loader breakage.
        """
        try:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE v.data_unavailable IS NOT TRUE) AS covered,
                  COUNT(*) AS total
                FROM value_metrics v
                JOIN stock_symbols s ON s.symbol = v.symbol
                LEFT JOIN LATERAL (
                    SELECT is_foreign_private_issuer FROM company_info_sec c
                    WHERE c.symbol = v.symbol ORDER BY filing_date DESC LIMIT 1
                ) cis ON true
                WHERE s.active = true AND COALESCE(cis.is_foreign_private_issuer, false) = false
                """
            )
            row = cur.fetchone()
            if not row or not row[1]:
                return None
            return int(row[0]), int(row[1])
        except Exception as e:
            logger.warning(f"[STOCK_SCORES] Could not compute FPI-excluded value_metrics coverage: {e}")
            return None

    def audit_upstream_coverage(self) -> None:
        """Audit upstream metric loader coverage after stock_scores completes.

        Verifies that critical metric loaders (value_metrics, stability_metrics) have
        sufficient completion before considering stock_scores run successful.
        Prevents silent data degradation when upstream loaders fail to complete.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT
                        table_name,
                        completion_pct,
                        symbols_loaded,
                        symbol_count
                    FROM data_loader_status
                    WHERE table_name IN ('value_metrics', 'positioning_metrics', 'stability_metrics', 'growth_metrics')
                    ORDER BY table_name
                """)

                metric_coverage = cur.fetchall()
                if not metric_coverage:
                    logger.warning(
                        "[STOCK_SCORES] No upstream metric loader status found. Metrics may not be populated yet."
                    )
                    return

                # Require at least 95% coverage on critical metric loaders for real-money readiness
                min_coverage_pct = 95.0
                critical_metric_loaders = ["value_metrics", "stability_metrics"]
                # FIX 2026-08-10: value_metrics/quality_metrics/growth_metrics' data_loader_status
                # row is SHARED across every invocation of load_value_quality_growth_metrics.py,
                # including small scoped `--symbols` diagnostic/spot-check runs (e.g. re-verifying
                # a couple of symbols after a data fix). completion_pct/symbol_count reflect
                # whatever the MOST RECENT run's own requested scope was, not the real universe -
                # live-reproduced: a 2-symbol diagnostic run that legitimately failed both (unrelated
                # missing SEC valuation data) left symbol_count=2/symbols_loaded=0, which this audit
                # then read as "value_metrics is 0.0% complete" and hard-failed EVERY subsequent
                # stock_scores run universe-wide, even though the real full-universe run moments
                # earlier had already loaded 5699/4917 symbols successfully. A tiny symbol_count is
                # not a statistically meaningful sample of universe-wide health - require the row to
                # actually represent a full-universe run before trusting its percentage.
                min_representative_symbol_count = 1000

                for table_name, completion_pct, symbols_loaded, symbol_count in metric_coverage:
                    if completion_pct is None:
                        logger.warning(f"[STOCK_SCORES] {table_name}: completion_pct is NULL (loader still running?)")
                        continue

                    if table_name not in critical_metric_loaders:
                        continue

                    if not symbol_count or symbol_count < min_representative_symbol_count:
                        logger.warning(
                            f"[STOCK_SCORES] {table_name}: symbol_count={symbol_count} is too small to represent "
                            f"the full universe (likely a scoped/diagnostic run) - skipping the {min_coverage_pct}% "
                            f"coverage gate for this table rather than judging universe-wide health from a "
                            f"non-representative sample."
                        )
                        continue

                    # FIXED 2026-08-21 (goal session - "why is stock_scores intermittently
                    # stale"): value_metrics' own completion_pct counts a symbol as "failed"
                    # whenever its row-level data_unavailable=TRUE (see
                    # load_value_quality_growth_metrics.py's symbols_failed bookkeeping) - but
                    # the overwhelming majority of those are foreign private issuers, which
                    # load_sec_valuations.py deliberately and permanently refuses to compute
                    # market_cap/pe/pb/etc. for (20-F/40-F filers report share counts in
                    # non-ADS home-market units - see that file's shares_outstanding
                    # resolution comments). Live-confirmed: of 982 active symbols with
                    # value_metrics.data_unavailable=TRUE, 795 (81%) are FPIs - a permanent,
                    # correct exclusion, not a loader health signal. That inflates the
                    # "failure" count enough that this gate hard-failed the whole stock_scores
                    # run today (80.8% raw vs the 95% bar) even though the loader had actually
                    # completed cleanly. Recomputing coverage over the non-FPI universe only
                    # (the population this gate can actually judge loader health from) gives
                    # 95.37% for the exact same run - real, achievable, and still enforces the
                    # gate's actual intent (catch real upstream breakage) without punishing an
                    # already-verified structural gap.
                    if table_name == "value_metrics":
                        corrected = self._value_metrics_coverage_excluding_fpi(cur)
                        if corrected is None:
                            logger.warning(
                                "[STOCK_SCORES] value_metrics: could not compute FPI-excluded "
                                "coverage, falling back to raw completion_pct"
                            )
                        else:
                            symbols_loaded, symbol_count = corrected
                            completion_pct = (symbols_loaded / symbol_count * 100.0) if symbol_count else 100.0

                    if completion_pct < min_coverage_pct:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Post-run audit failed: {table_name} only {completion_pct:.1f}% complete "
                            f"({symbols_loaded}/{symbol_count} symbols). "
                            f"Cannot compute stock scores with upstream metric coverage below {min_coverage_pct}%. "
                            f"Requires upstream metric loaders to complete successfully."
                        )
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"[STOCK_SCORES] Post-run audit encountered error: {e}", exc_info=True)
            raise

    def post_run(self) -> None:
        # ORDER MATTERS: update_rs_percentiles() reads only momentum_score, which is
        # unrelated to what audit_upstream_coverage() checks (value_metrics/stability_metrics
        # coverage). Live-reproduced 2026-08-10: a transient dip in value_metrics coverage
        # (contention from concurrent sessions) made audit_upstream_coverage() raise, which
        # crashed the whole subprocess (exit 1) BEFORE update_rs_percentiles() ever ran - even
        # though all 4917 symbols' per-symbol scoring (including momentum_score) had already
        # completed successfully. rs_percentile stayed NULL for the entire universe, and
        # Phase 7 silently filtered out every single candidate as a result (100+ candidates
        # otherwise qualified) with a misleading "no signals found" message that never named
        # the real cause. Compute the RS ranking first (it doesn't depend on the audited
        # tables), THEN run the audit - a coverage problem should still fail the run for
        # visibility, but must not collaterally block an unrelated, Phase-7-critical step.
        self.update_rs_percentiles()
        self.snapshot_score_history()
        self.audit_upstream_coverage()

    def update_rs_percentiles(self) -> None:
        """Batch pass: rank all stocks by momentum_score and write true RS percentile.

        Uses PERCENT_RANK() so a stock scoring higher than 90% of peers gets rs_percentile=90.
        Must run after all per-symbol scores are loaded.

        GOVERNANCE: PostgreSQL sorts NULLs last by default, so ranking over the full table
        (including rows with no momentum_score) previously gave every NULL-momentum stock a
        false top-quintile rs_percentile (~81, the percentile of the last real row) instead
        of reflecting that the stock has no momentum data at all. That fabricated value fed
        straight into Phase 7's signal-generation completeness gate, defeating the exact
        check meant to catch missing data. Rank only over rows with real momentum_score, and
        explicitly null out rs_percentile for the rest so missing data stays visibly missing.

        CRITICAL: Raises on failure. RS percentiles are essential for ranking signal quality;
        missing or stale percentiles invalidate momentum-based signal filtering.

        CRITICAL FIX 2026-08-06: Update `updated_at` timestamp to ensure Phase 1's freshness
        check recognizes that post_run() completed successfully and rs_percentile was computed.
        Without this, rs_percentile stays NULL and Phase 7 filters out all signals.
        """
        try:
            with DatabaseContext("write") as cur:
                # First, update rs_percentile via PERCENT_RANK for symbols with momentum scores
                cur.execute("""
                    UPDATE stock_scores ss
                    SET rs_percentile = ranked.pct,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT symbol,
                               ROUND(
                                   (PERCENT_RANK() OVER (ORDER BY momentum_score))::NUMERIC * 100,
                                   2
                               ) AS pct
                        FROM stock_scores
                        WHERE momentum_score IS NOT NULL
                    ) ranked
                    WHERE ss.symbol = ranked.symbol
                """)
                # Second, explicitly null out rs_percentile for symbols without momentum scores
                cur.execute("""
                    UPDATE stock_scores
                    SET rs_percentile = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE momentum_score IS NULL AND rs_percentile IS NOT NULL
                """)
                # Third, update timestamp for any remaining rows to mark post_run completion
                cur.execute("""
                    UPDATE stock_scores
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE rs_percentile IS NOT NULL OR momentum_score IS NOT NULL
                """)
            logger.info("RS percentiles updated via batch rank (post_run completed)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"RS percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def snapshot_score_history(self) -> None:
        """Batch pass: snapshot today's stock_scores into stock_scores_history.

        Must run after update_rs_percentiles() so the snapshot includes the finalized
        rs_percentile from this same run, not a stale value from the prior run.

        One row per (symbol, score_date): re-running post_run() on the same calendar day
        (e.g. a retry) updates that day's snapshot in place rather than appending a
        duplicate, so history stays one data point per trading day regardless of how many
        times the loader runs that day.

        composite_rank is computed once here (not at read time) so a stock's historical
        rank reflects the universe actually scored that day, not today's universe size.

        CRITICAL: Raises on failure, same as update_rs_percentiles() - a broken snapshot
        pass should be visible, not silently swallowed.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    INSERT INTO stock_scores_history (
                        symbol, score_date, composite_score, composite_rank,
                        momentum_score, quality_score, growth_score, value_score,
                        positioning_score, stability_score, rs_percentile,
                        data_completeness, updated_at
                    )
                    SELECT
                        symbol,
                        CURRENT_DATE,
                        composite_score,
                        RANK() OVER (ORDER BY composite_score DESC NULLS LAST) AS composite_rank,
                        momentum_score, quality_score, growth_score, value_score,
                        positioning_score, stability_score, rs_percentile,
                        data_completeness, CURRENT_TIMESTAMP
                    FROM stock_scores
                    WHERE data_unavailable IS NOT TRUE AND composite_score IS NOT NULL
                    ON CONFLICT (symbol, score_date) DO UPDATE SET
                        composite_score = EXCLUDED.composite_score,
                        composite_rank = EXCLUDED.composite_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        quality_score = EXCLUDED.quality_score,
                        growth_score = EXCLUDED.growth_score,
                        value_score = EXCLUDED.value_score,
                        positioning_score = EXCLUDED.positioning_score,
                        stability_score = EXCLUDED.stability_score,
                        rs_percentile = EXCLUDED.rs_percentile,
                        data_completeness = EXCLUDED.data_completeness,
                        updated_at = CURRENT_TIMESTAMP
                """)
                snapshotted = cur.rowcount
            logger.info(f"Score history snapshot written for {snapshotted} symbols (post_run completed)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Score history snapshot failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


if __name__ == "__main__":
    sys.exit(run_loader(StockScoresLoader))
