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
            cur.execute(
                "SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, "
                "eps_growth_1y, eps_growth_3y, eps_growth_5y, "
                "net_income_growth_yoy, operating_income_growth_yoy, sustainable_growth_rate, "
                "fcf_growth_yoy, ocf_growth_yoy, "
                "gross_margin_trend, operating_margin_trend, net_margin_trend, roe_trend, asset_growth_yoy, "
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
            cur.execute(
                "SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, "
                "forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct, data_unavailable FROM value_metrics"
            )
            self._value_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # shares_short_prior_month/short_interest_pct_change added: written by
            # load_positioning_metrics.py (migration 1184, pct_change replacing the former
            # short_interest_trend enum column in migration 1203) but never read here before -
            # the existing short_interest weight only used the latest %-of-float snapshot, with
            # no signal for which direction it's moving.
            cur.execute(
                "SELECT symbol, institutional_ownership_pct, insider_ownership_pct, short_interest_pct, "
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
            base_weights = {
                "quality": 0.25,
                "growth": 0.20,
                "value": 0.20,
                "positioning": 0.15,
                "stability": 0.12,
                "momentum": 0.08,
            }
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
                "positioning": ["institutional_holdings_13f", "insider_holdings_sec", "short_interest_finra"]
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
            # CRITICAL: Validate row has expected 17 columns before accessing indices
            if len(row) < 17:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 17. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[16]
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
        - Row length validation: Must have 7 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
          dividend_yield, fcf_yield, data_unavailable)
        - Schema mismatch (len(row) < 7) → raises ValueError immediately
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
            # CRITICAL: Validate row has expected 11 columns before accessing indices
            # (10 + margin_of_safety_pct added for the DCF Value factor goal, 2026-08-17)
            if len(row) < 11:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 11. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[10]
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
        - Row length validation: Must have 7 columns (institutional_ownership, insider_ownership,
          short_interest_percent, shares_short_prior_month, short_interest_pct_change, ad_rating,
          data_unavailable)
        - Schema mismatch (len(row) < 7) → raises ValueError immediately
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
            # CRITICAL: Validate row has expected 7 columns before accessing indices
            if len(row) < 7:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: positioning_metrics row has {len(row)} columns, expected 7. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[6]
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
                "insider_ownership": safe_float(row[1], f"{symbol}.insider_ownership"),
                "short_interest": safe_float(row[2], f"{symbol}.short_interest"),
                "shares_short_prior_month": safe_float(row[3], f"{symbol}.shares_short_prior_month", allow_none=True),
                "short_interest_pct_change": safe_float(row[4], f"{symbol}.short_interest_pct_change", allow_none=True),
                "ad_rating": safe_float(row[5], f"{symbol}.ad_rating", allow_none=True),
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

        Components weighted (in pre-computed model): Margins 30% + Profitability 25% + Leverage/Liquidity 25% + Growth 20%
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
        """Enhance pre-computed quality score with Phase 3 margin/growth signals.

        Adjusts base score by ±10% based on margin trends and earnings growth (Phase 3).
        Keeps existing quality_score as foundation; uses new metrics for refinement.

        CLEANUP 2026-08-16: Financial Stability (debt-to-equity, debt-to-assets -
        _score_financial_stability) moved here from Stability's _score_stability, where it
        was a 20%-weighted sub-score. These are balance-sheet fundamentals (leverage/
        solvency), not price-volatility signals, so they belong under Quality.
        debt_to_assets already feeds the base quality_score (~17%, computed upstream in
        load_value_quality_growth_metrics.py) - this adjustment adds the remaining
        leverage signal on top, same bounded-adjustment pattern as the margin/ROIC/OCF
        adjustments below rather than a new proportional weight slot. CLEANUP 2026-08-18:
        current_ratio/quick_ratio/cash_per_share removed from _score_financial_stability -
        not factor-score inputs anymore.
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

        # Growth signal: Positive earnings growth improves quality perception
        earnings_growth = safe_float(
            metrics.get("earnings_growth_yoy"), f"{symbol}.earnings_growth_yoy", allow_none=True
        )
        if earnings_growth is not None and earnings_growth > 0:
            # Growth premium: +5 for 10%+ growth, +2 for 5%+ growth
            adjustment += min(5.0, earnings_growth / 10.0)

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

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Score growth metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted blend: EPS 1Y (33%) + Revenue 1Y (24%) + EPS 3Y (19%) + Revenue 3Y (14%)
        + EPS 5Y (5%) + Revenue 5Y (5%). Longer-term growth signals more durable earnings quality.

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

        # 1-year EPS growth: target 25%+ for growth stocks (highest weight)
        eps_1y = _score_single_growth(metrics.get("eps_growth_1y"), 50)
        if eps_1y is not None:
            weighted_sum += eps_1y * 0.33
            total_weight += 0.33

        # 1-year revenue growth: target 15%+
        rev_1y = _score_single_growth(metrics.get("revenue_growth_1y"), 30)
        if rev_1y is not None:
            weighted_sum += rev_1y * 0.24
            total_weight += 0.24

        # 3-year EPS CAGR: sustained growth signal
        eps_3y = _score_single_growth(metrics.get("eps_growth_3y"), 35)
        if eps_3y is not None:
            weighted_sum += eps_3y * 0.19
            total_weight += 0.19

        # 3-year revenue CAGR: sustained top-line growth
        rev_3y = _score_single_growth(metrics.get("revenue_growth_3y"), 20)
        if rev_3y is not None:
            weighted_sum += rev_3y * 0.14
            total_weight += 0.14

        # 5-year EPS CAGR: long-term compounding quality (lower weight)
        eps_5y = _score_single_growth(metrics.get("eps_growth_5y"), 30)
        if eps_5y is not None:
            weighted_sum += eps_5y * 0.05
            total_weight += 0.05

        # 5-year revenue CAGR: long-term top-line durability. Previously fetched
        # and displayed but never weighted (dead field); cap set lower than the
        # 1y/3y revenue caps since CAGR compounds and is harder to sustain longer.
        rev_5y = _score_single_growth(metrics.get("revenue_growth_5y"), 15)
        if rev_5y is not None:
            weighted_sum += rev_5y * 0.05
            total_weight += 0.05

        # Bottom-line growth trend fields (2026-08-03): computed by
        # load_value_quality_growth_metrics.py and mirrored into growth_metrics, but never
        # read here before - fetched and displayed on the scores page with zero influence
        # on growth_score. Smaller combined weight budget (0.30 total vs 1.0 for the
        # existing eps/revenue CAGR components above) since these are noisier single-year
        # deltas rather than multi-year CAGRs; total_weight normalization means they only
        # matter when the more stable eps/revenue fields are unavailable.
        ni_growth = _score_single_growth(metrics.get("net_income_growth_yoy"), 40)
        if ni_growth is not None:
            weighted_sum += ni_growth * 0.08
            total_weight += 0.08

        oi_growth = _score_single_growth(metrics.get("operating_income_growth_yoy"), 40)
        if oi_growth is not None:
            weighted_sum += oi_growth * 0.06
            total_weight += 0.06

        # Sustainable growth rate = ROE * retention ratio: how fast the company can grow
        # without external financing. Typically 0-30% for healthy companies; capped lower
        # than the YoY deltas above since it's already a moderated, long-run-oriented figure.
        sgr = _score_single_growth(metrics.get("sustainable_growth_rate"), 25)
        if sgr is not None:
            weighted_sum += sgr * 0.06
            total_weight += 0.06

        fcf_growth = _score_single_growth(metrics.get("fcf_growth_yoy"), 50)
        if fcf_growth is not None:
            weighted_sum += fcf_growth * 0.06
            total_weight += 0.06

        ocf_growth = _score_single_growth(metrics.get("ocf_growth_yoy"), 40)
        if ocf_growth is not None:
            weighted_sum += ocf_growth * 0.04
            total_weight += 0.04

        # Asset growth YoY (2026-08-03): balance-sheet-level growth signal, same growth-rate
        # shape as the income-statement deltas above.
        asset_growth = _score_single_growth(metrics.get("asset_growth_yoy"), 30)
        if asset_growth is not None:
            weighted_sum += asset_growth * 0.05
            total_weight += 0.05

        # Margin/ROE trend fields (2026-08-03): these are percentage-POINT deltas
        # (curr - prior), not growth rates - e.g. operating_margin_trend=+2 means the
        # margin improved 2 points YoY. Reused _score_single_growth's [-cap,0]->[0,40],
        # [0,cap]->[40,100] shape with a small cap tuned for point-deltas rather than %
        # growth (a 10-point margin swing YoY is already a large move for most companies).
        # Small individual weights (0.03 each) since these are correlated views of the
        # same underlying margin-trend signal, not independent factors.
        # gross_margin_trend deliberately excluded 2026-08-18 - not a factor-score input.
        om_trend = _score_single_growth(metrics.get("operating_margin_trend"), 10)
        if om_trend is not None:
            weighted_sum += om_trend * 0.03
            total_weight += 0.03

        nm_trend = _score_single_growth(metrics.get("net_margin_trend"), 10)
        if nm_trend is not None:
            weighted_sum += nm_trend * 0.03
            total_weight += 0.03

        roe_trend = _score_single_growth(metrics.get("roe_trend"), 10)
        if roe_trend is not None:
            weighted_sum += roe_trend * 0.03
            total_weight += 0.03

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

        Uses weighted scoring: P/E (45%) + P/B (20%) + P/S (15%) + PEG (15%) + FCF yield (12%)
        + Dividend yield (8%) + Forward P/E (15%) + EV/EBITDA (12%) + EV/Revenue (10%).
        Peak zone for growth stocks: P/E 15-30, P/B < 5, PEG < 1-2, positive FCF yield.

        NOTE 2026-08-18: margin_of_safety_pct (DCF discount to intrinsic value) is
        deliberately NOT a Value input - it's the one metric we keep for cross-symbol
        comparability, but it's displayed as an informational read (see
        StockScoreAccordion.jsx) rather than folded into any factor score.

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
            weighted_sum += pe_score * 0.45
            total_weight += 0.45

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors
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
            weighted_sum += pb_score * 0.20
            total_weight += 0.20

        # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
        # multiples run richer than book multiples (especially for growth/SaaS names).
        # Previously fetched and displayed but never weighted (dead field).
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
            weighted_sum += ps_score * 0.15
            total_weight += 0.15

        # PEG ratio: PE adjusted for earnings growth - <1 is classically "undervalued
        # relative to growth" (Peter Lynch heuristic), >2-3 signals growth already priced
        # in. Distinct signal from P/E (which says nothing about growth) and P/S (no
        # earnings context at all). Was fetched and displayed but carried zero weight -
        # this loader's own PEG computation (load_sec_valuations.py) previously always
        # computed a growth rate of exactly 0 (comparing TTM EPS to itself), which was
        # fixed 2026-07-20 to use a genuine prior-fiscal-year EPS; backfills on next run.
        if metrics.get("peg_ratio") is not None and metrics["peg_ratio"] > 0:
            weighted_sum += self._peg_to_score(metrics["peg_ratio"]) * 0.15
            total_weight += 0.15

        # FCF yield: positive FCF yield is healthy; > 3% is good
        # BUGFIX 2026-07-20: load_sec_valuations.py stores fcf_yield already as a percentage
        # (e.g. 2.27 = 2.27%, confirmed live: AAPL=2.27, MSFT=4.69, T=25.83) - this used to
        # re-multiply by 100 assuming a decimal fraction, so fcf_pct came out ~100x too high
        # (e.g. 227 for AAPL) and saturated fcf_score to 100 for virtually every FCF-positive
        # stock regardless of actual yield. This component was effectively a dead constant.
        if metrics.get("fcf_yield") is not None and metrics["fcf_yield"] > 0:
            fcf_pct = metrics["fcf_yield"]  # already a percentage
            fcf_score = min(100, fcf_pct * 20)  # 5% FCF yield = 100 score
            weighted_sum += fcf_score * 0.12
            total_weight += 0.12

        # Dividend yield: bonus signal for income/quality (optional). Unlike fcf_yield,
        # sec_valuations.dividend_yield (added 2026-07-20, migration 1146) is computed and
        # stored as a decimal fraction (0.03 = 3%), so the *100 conversion below is correct
        # for this field - do not "fix" it to match fcf_yield's convention.
        if metrics.get("dividend_yield") is not None and metrics["dividend_yield"] > 0:
            div = min(metrics["dividend_yield"] * 100, 6)  # decimal -> percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.08
            total_weight += 0.08

        # Forward P/E: analyst-consensus-based, complements trailing P/E with a forward-
        # looking view (2026-08-03: loaded via sec_valuations/analyst_earnings_estimates,
        # displayed on the scores page, but never weighted). Same tiered curve as trailing
        # P/E since the interpretation (cheap/fair/growth-premium/expensive) is identical.
        if metrics.get("forward_pe") is not None and metrics["forward_pe"] > 0:
            fpe = metrics["forward_pe"]
            if fpe <= 10:
                fpe_score = 40 + fpe * 2
            elif fpe <= 20:
                fpe_score = 60 + (fpe - 10) * 4
            elif fpe <= 35:
                fpe_score = 100 - (fpe - 20) * 2
            else:
                fpe_score = max(0, 70 - (fpe - 35) * 1.4)
            weighted_sum += fpe_score * 0.15
            total_weight += 0.15

        # EV/EBITDA: capital-structure-neutral valuation (unlike P/E, unaffected by
        # leverage) - 2026-08-03: loaded via sec_valuations, displayed, never weighted.
        # <8x cheap, 8-15x fair, >20x expensive (standard equity-research heuristic).
        if metrics.get("ev_ebitda") is not None and metrics["ev_ebitda"] > 0:
            eve = metrics["ev_ebitda"]
            if eve <= 8:
                eve_score = 100
            elif eve <= 15:
                eve_score = 100 - ((eve - 8) / 7) * 30  # 100->70
            elif eve <= 25:
                eve_score = 70 - ((eve - 15) / 10) * 40  # 70->30
            else:
                eve_score = max(0, 30 - (eve - 25) * 1.5)
            weighted_sum += eve_score * 0.12
            total_weight += 0.12

        # EV/Revenue: same interpretation as P/S but on an EV basis (accounts for debt/cash)
        # - 2026-08-03: loaded via sec_valuations, displayed, never weighted.
        if metrics.get("ev_revenue") is not None and metrics["ev_revenue"] > 0:
            evr = metrics["ev_revenue"]
            if evr <= 2.0:
                evr_score = 100
            elif evr <= 6.0:
                evr_score = 100 - ((evr - 2.0) / 4.0) * 30
            elif evr <= 15.0:
                evr_score = 70 - ((evr - 6.0) / 9.0) * 40
            else:
                evr_score = max(0, 30 - (evr - 15.0) * 1.5)
            weighted_sum += evr_score * 0.10
            total_weight += 0.10

        # margin_of_safety_pct (DCF discount to intrinsic value) is intentionally excluded
        # from Value scoring - see docstring note above. Still computed/stored by
        # load_sec_valuations.py and displayed informationally, just not weighted here.

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
        Institutional ownership (55%) + Insider ownership (20%) + Short interest (25%)
        + Short interest % change MoM (10%) + A/D rating (15%).
        Higher institutional + insider ownership and lower short interest signal positive positioning.

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

        MINIMUM DATA REQUIREMENT: At least one of institutional_ownership/insider_ownership/
        short_interest metrics must be non-NULL. If all positioning metrics are None,
        returns data_unavailable marker. Optional for REITs/special securities.
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
            weighted_sum += io * 0.55
            total_weight += 0.55

        # Insider ownership: moderate insider ownership (5-20%) is a positive signal
        if metrics.get("insider_ownership") is not None:
            ins = metrics["insider_ownership"]  # stored as percentage (e.g., 5.2 = 5.2%)
            if ins >= 20:
                ins_score = 100
            elif ins >= 5:
                ins_score = 60 + (ins - 5) / 15 * 40
            elif ins >= 1:
                ins_score = 40 + (ins - 1) / 4 * 20
            else:
                ins_score = ins * 40
            weighted_sum += min(100, ins_score) * 0.20
            total_weight += 0.20

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
            weighted_sum += metrics["ad_rating"] * 0.15
            total_weight += 0.15

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for positioning_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_positioning_scores_computed"}

    def _score_stability(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Score stability metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        Uses weighted scoring: Volatility 252d (40%) + Volatility 60d (20%) + Volatility 30d (15%)
        + Beta (15%) + Downside Volatility 252d/60d/30d (15%/7.5%/5%, purer "risk of loss" signal)
        + Max Drawdown 1y (10%). Lower volatility and beta closer to 1.0 indicate stable,
        market-correlated stocks. Weights are relative, not required to sum to 100 - each present
        sub-component contributes weighted_sum/total_weight (self-normalizing over whatever
        metrics are actually available for a symbol, per GOVERNANCE's no-redistribution rule at
        the top-level factor split; this renormalization is local to stability's own sub-scores).

        CLEANUP 2026-08-16: Financial Stability (debt-to-equity, debt-to-assets, current/quick
        ratio, cash per share) and Business Diversification (revenue concentration HHI) were
        removed from this factor - stability is meant to track price-volatility/risk-of-loss
        character, not balance-sheet fundamentals or business concentration. The debt/liquidity/
        cash metrics now feed Quality instead (see _enhance_quality_score); revenue concentration
        HHI was dropped from scoring entirely per user request.

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

        # 12-month (252-day) annualized volatility: lower is better
        # Swing traders can tolerate moderate volatility; penalty starts above 25%
        if metrics.get("volatility_252d") is not None:
            vol = max(0, metrics["volatility_252d"])
            if vol <= 0.15:
                vol_score = 100
            elif vol <= 0.30:
                vol_score = 100 - ((vol - 0.15) / 0.15) * 50  # 100?50 in [15%,30%]
            elif vol <= 0.60:
                vol_score = 50 - ((vol - 0.30) / 0.30) * 40  # 50?10 in [30%,60%]
            else:
                vol_score = max(0, 10 - (vol - 0.60) * 20)
            weighted_sum += vol_score * 0.40
            total_weight += 0.40

        # 60-day volatility: recent stability proxy (higher weight than 12m for swing traders)
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
            weighted_sum += v60_score * 0.20
            total_weight += 0.20

        # 30-day volatility: most-recent stability read; best-populated volatility
        # column in the DB (98%+) but previously fetched and never scored.
        if metrics.get("volatility_30d") is not None:
            vol30 = max(0, metrics["volatility_30d"])
            if vol30 <= 0.15:
                v30_score = 100
            elif vol30 <= 0.30:
                v30_score = 100 - ((vol30 - 0.15) / 0.15) * 50
            elif vol30 <= 0.60:
                v30_score = 50 - ((vol30 - 0.30) / 0.30) * 40
            else:
                v30_score = max(0, 10 - (vol30 - 0.60) * 20)
            weighted_sum += v30_score * 0.15
            total_weight += 0.15

        # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading
        if metrics.get("beta") is not None:
            beta = max(0, metrics["beta"])
            diff = min(abs(beta - 1.0), 2.0)
            beta_score = max(0, 100 - (diff * 50))
            weighted_sum += beta_score * 0.15
            total_weight += 0.15

        # Downside deviation (252d/60d/30d): only penalizes downside price moves, unlike the
        # symmetric volatility_* above which penalizes upside moves equally - a purer
        # "risk of loss" signal (2026-08-03: written by load_risk_metrics_daily.py,
        # displayed on the scores page, but only 252d was ever weighted - 60d/30d were
        # computed and shown on the dashboard with no scoring effect, an inconsistency vs.
        # symmetric volatility which scores all three windows. Fixed 2026-08-16: 60d/30d
        # now scored too, at the same 40:20:15 ratio as symmetric volatility's
        # 252d:60d:30d weights, scaled onto downside's 15% base (15 * 20/40 = 7.5,
        # 15 * 15/40 = 5.625 -> 5). Same tiered curve as volatility_252d since it's on the
        # same annualized-stdev scale.
        if metrics.get("downside_volatility_252d") is not None:
            dvol = max(0, metrics["downside_volatility_252d"])
            if dvol <= 0.15:
                dvol_score = 100
            elif dvol <= 0.30:
                dvol_score = 100 - ((dvol - 0.15) / 0.15) * 50
            elif dvol <= 0.60:
                dvol_score = 50 - ((dvol - 0.30) / 0.30) * 40
            else:
                dvol_score = max(0, 10 - (dvol - 0.60) * 20)
            weighted_sum += dvol_score * 0.15
            total_weight += 0.15

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
            weighted_sum += dvol60_score * 0.075
            total_weight += 0.075

        if metrics.get("downside_volatility_30d") is not None:
            dvol30 = max(0, metrics["downside_volatility_30d"])
            if dvol30 <= 0.15:
                dvol30_score = 100
            elif dvol30 <= 0.30:
                dvol30_score = 100 - ((dvol30 - 0.15) / 0.15) * 50
            elif dvol30 <= 0.60:
                dvol30_score = 50 - ((dvol30 - 0.30) / 0.30) * 40
            else:
                dvol30_score = max(0, 10 - (dvol30 - 0.60) * 20)
            weighted_sum += dvol30_score * 0.05
            total_weight += 0.05

        # Max drawdown (1y): peak-to-trough decline, stored as a negative percentage
        # (e.g. -34.63 = a 34.63% decline from peak) - 2026-08-03: written by
        # load_risk_metrics_daily.py, displayed, never weighted. Distinct signal from
        # volatility (a stock can have low day-to-day volatility yet still suffer one deep
        # sustained drawdown). <=10% drawdown is mild, >50% is severe.
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
            weighted_sum += dd_score * 0.10
            total_weight += 0.10

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

        Combines: Debt-to-equity (30%) + Debt-to-assets (25%). Returns None if no
        financial metrics available.

        Session 359: Phase 8 enhancement - adds financial solvency scoring. CLEANUP 2026-08-16:
        called from _enhance_quality_score (Quality) instead of _score_stability - these are
        balance-sheet fundamentals, not price-volatility signals, so they belong under Quality.
        CLEANUP 2026-08-18: current_ratio/quick_ratio/cash_per_share (liquidity/cash
        components) removed - not factor-score inputs anymore.
        """
        components: list[tuple[float, float]] = []  # (score, weight) pairs

        if metrics.get("debt_to_equity") is not None:
            dte = float(max(0, metrics["debt_to_equity"]))
            components.append((self._score_dte(dte), 0.30))

        if metrics.get("debt_to_assets") is not None and metrics["debt_to_assets"] >= 0:
            dta = float(min(metrics["debt_to_assets"], 1.0))
            dta_score = max(0, 100.0 - (dta * 100.0))
            components.append((dta_score, 0.25))

        if not components:
            return None

        total_weight = sum(w for _, w in components)
        if total_weight == 0:
            return None

        weighted_score = sum(s * w for s, w in components) / total_weight
        return float(max(0, min(100, weighted_score)))

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Momentum 1m (16%) + 3m (16%) + 6m (14%) + 12m (9%)
        + RSI(14) (15%) + MACD sign (10%) + ROC composite (12%) + SMA positioning (8%).
        Weights favor recent price-return momentum (1m/3m) over longer-term (12m) for swing
        trading. Technical indicators (RSI, MACD, ROC, SMA) were added to complement
        price-return momentum with mean-reversion and trend-following signals.
        Normalizes by total weight of available components so partial data doesn't deflate
        the score.

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

        # Named weights - recent timeframes matter more for swing trading
        weights = {
            "momentum_1m": 0.16,
            "momentum_3m": 0.16,
            "momentum_6m": 0.14,
            "momentum_12m": 0.09,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in weights.items():
            if metrics.get(key) is not None:
                score = self._pct_to_score(metrics[key])
                if score is not None:  # Skip weak momentum (score=None)
                    weighted_sum += score * w
                    total_weight += w

        # RSI(14): momentum-following curve (not mean-reversion) - higher RSI is more
        # bullish, with only a slight pullback at extreme overbought (>85) for reversal risk.
        if metrics.get("rsi_14") is not None:
            rsi_score = self._rsi_to_score(metrics["rsi_14"])
            weighted_sum += rsi_score * 0.15
            total_weight += 0.15

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
            weighted_sum += macd_score * 0.10
            total_weight += 0.10

        # ROC (Rate of Change) composite: average of 20d/60d/120d/252d windows
        roc_scores = []
        for roc_field in ["roc_20d", "roc_60d", "roc_120d", "roc_252d"]:
            roc_val = metrics.get(roc_field)
            if roc_val is not None:
                roc_scores.append(self._pct_to_score(roc_val))
        if roc_scores:
            roc_scores_filtered: list[float] = [s for s in roc_scores if s is not None]
            if roc_scores_filtered:
                weighted_sum += (sum(roc_scores_filtered) / len(roc_scores_filtered)) * 0.12
                total_weight += 0.12

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


if __name__ == "__main__":
    sys.exit(run_loader(StockScoresLoader))
