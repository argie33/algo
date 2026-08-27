#!/usr/bin/env python3
"""Stock Scores Loader - Multi-factor composite stock scoring.

Computes composite stock scores by aggregating:
- Quality metrics (ROE, margins, debt-to-equity ratio)
- Growth metrics (revenue growth, EPS growth)
- Value metrics (P/E, P/B, P/S ratios, dividend yield)
- Momentum/Relative Strength (1m/3m/6m/12m returns)
- Stability metrics (volatility, beta)

Positioning (A/D rating, institutional ownership, short interest) is NOT part of the
composite - retired as a top-level pillar 2026-08-27 (see BASE_PILLAR_WEIGHTS). Its inputs
are still computed/stored by load_positioning_metrics.py and displayed via the scores API's
positioning_inputs field, informationally only.

Each factor is normalized to 0-100 scale and weighted.
Final composite score is weighted average of all factors.

CRITICAL GOVERNANCE RULES:
- Minimum 1/5 metrics required for any stock score - degraded-mode scoring is allowed (SPACs/
  new listings, see Session 530 note on min_required_metrics below); trading gates separately
  filter on data_completeness >= 70% (min_completeness_score), which is the real entry-quality
  bar (no IPO exceptions there either)
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
# SIZE PILLAR REMOVED 2026-08-26 (user directive): market cap is no longer a scored input at
# all - not as a top-level pillar, not folded back into Value either. This reverts the
# 2026-08-26 "promote Size to a 7th pillar" change (commit 869e431c3) entirely; weights below
# are the pre-promotion values. See _score_size's removal note for what was deleted.
#
# POSITIONING RETIRED AS A COMPOSITE PILLAR 2026-08-27 (evidence-driven, see migration
# 1240_retire_positioning_score_from_stock_scores.sql for the full trail). Its only
# consistently-testable input, A/D rating (35% weight, previously kept on an explicit user
# directive despite null return-prediction evidence), was re-tested against the FULL
# available price history (2000-2026, 318 months, median 2,403 symbols - vs. the ~2015-on
# window every prior test defaulted to) specifically to rule out "not enough data" hiding a
# real signal: t=1.05, still not significant. institutional_ownership_pct and
# short_interest_pct/short_interest_pct_change have never had real historical depth in this
# database (institutional_holdings_13f: 1 row/symbol; short_interest_finra: ~2 real months of
# settlement-date coverage) - untestable, not merely untested. The pillar-level composite
# proxy is consistent with this: never significant in the top-level regression
# (algo/research/fama_macbeth_composite_weights.py), and its sign FLIPS between half-splits
# (t=+1.61 first half, t=-1.15 second half) - the signature of noise, not a real factor.
#
# Freed 12% moves to Growth (+6, 0.12->0.18) and Risk (+6, 0.18->0.24) - the two pillars that
# are consistently positive and never sign-flip across every specification of that same
# top-level regression (growth_proxy t=1.39 univariate/1.72 multivariate; risk_proxy
# [formerly stability_proxy] t=2.48 multivariate, the single strongest non-Size coefficient in
# the file, t=2.40/2.86 in both half-splits). Value and Momentum were left unchanged - both
# weak/inconsistent in this same regression, but with no stronger competing evidence to move
# them either direction (Value's own within-pillar FM work is separately robust; Momentum's
# composite-level coefficient is noisy but not worse than its neighbors, and moving it would
# just be encoding this run's specific noise). Quality's negative composite-level coefficient
# was deliberately NOT acted on - flagged in a prior pass as not half-split robust, a known
# collinearity artifact of this specific regression, not a finding about Quality itself (whose
# own within-pillar FM validation is separately strong).
#
# A/D rating, institutional ownership, and short interest are NOT deleted from the system:
# load_positioning_metrics.py keeps computing/storing them unchanged, and the scores API
# still surfaces them via positioning_inputs for display - only the synthesized 0-100
# "positioning_score" composite, which no longer has a coherent empirical basis, is dropped.
BASE_PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.25,
    "growth": 0.18,
    "value": 0.21,
    "risk": 0.24,
    "momentum": 0.12,
}


class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field: str = "updated_at"
    exclude_etfs_from_symbols = True  # Metric loaders (quality, growth, value, risk) exclude ETFs

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
        - required: value/risk - must have real coverage thresholds met
        - optional_sec: quality/growth - depend on SEC annual financials; may be all-unavailable
          if the annual_income_statement upstream is empty. Fail only if table is completely empty
          (loader never ran). All-unavailable is acceptable; per-symbol scoring handles gracefully.

        positioning_metrics REMOVED 2026-08-27: no longer a stock_scores upstream dependency
        now that Positioning is retired as a composite pillar (see BASE_PILLAR_WEIGHTS). The
        table itself is unaffected and still validated by its own loader - this loader just no
        longer reads it.
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
                            f"Typical causes: SEC API limits (quality/growth), yfinance throttling (value), price history gaps (stability). "
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
        """Load all metric tables once instead of per-symbol (N+1 fix).

        Previously each of quality/growth/value/positioning/stability_metrics was queried with
        a separate `WHERE symbol = %s` per symbol (~5 x symbol_count round-trips per run), and
        the momentum query re-evaluated `(SELECT MAX(date) FROM price_daily)` as an inline
        subquery up to 4 times per symbol against an 8.6M+ row table. Now: bulk queries total,
        cached by symbol; momentum is read from momentum_metrics table (precomputed).
        positioning_metrics dropped from this batch-preload 2026-08-27 (Positioning retired as
        a composite pillar - see BASE_PILLAR_WEIGHTS).

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
            # rates) and stored at 67.8% coverage. CORRECTED 2026-08-26 (verified directly in
            # _score_growth's actual weighted_sum below, not assumed from an older memory note):
            # this field is fetched here but NOT currently in _score_growth's weighted formula -
            # a 2026-08-26 Growth re-audit briefly gave it a 25% weight, but a same-day user-
            # directed revert restored the pre-audit 14-input blend (see _score_growth's own
            # "RESTORED 2026-08-26" docstring), which never included eps_growth_stability. It is
            # NOT read for the since-removed `_enhance_quality_score` either - that reference was
            # itself stale. Currently a genuinely dead fetch; flagged, not fixed, since removing
            # a dead SELECT column is out of scope for whatever prompted this comment originally.
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

            # amihud_illiquidity wiring REMOVED 2026-08-26 (user directive, same day it was
            # added - see _score_value's docstring for why: not a bug, a deliberate call that
            # an illiquidity-premium tilt isn't worth carrying in live scoring given this
            # system's own realistic execution-cost concerns for the exact names it would
            # favor). technical_data_daily.amihud_illiquidity itself is left computed/stored
            # (loaders/load_technical_indicators.py, migration 1232) - only its consumption
            # here was removed, same convention as EV/EBITDA/EV/Revenue elsewhere in this file.

            # positioning_metrics preload REMOVED 2026-08-27: Positioning retired as a
            # composite pillar (see BASE_PILLAR_WEIGHTS), so this loader no longer reads
            # positioning_metrics at all - the table itself, and its own loader
            # (load_positioning_metrics.py), are unaffected and keep populating it for the
            # scores API's informational positioning_inputs display.

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
                        "risk_score": None,
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
                    "risk_score": None,
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
        value_score, momentum_score, risk_score, rs_percentile, data_completeness

        Raises:
            RuntimeError: If insufficient metrics available to compute valid score
        """
        try:
            with DatabaseContext("read") as cur:
                quality = self._get_quality_metrics(cur, symbol)
                growth = self._get_growth_metrics(cur, symbol)
                value = self._get_value_metrics(cur, symbol)
                risk_metrics = self._get_stability_metrics(cur, symbol)
                momentum = self._get_momentum_metrics(cur, symbol)

            # Compute individual factor scores from REAL data only (no defaults)
            # Scoring functions return float or dict (marker when data unavailable)
            # Keep marker dicts throughout to track missing data reasons
            quality_score = self._score_quality(quality, symbol)
            growth_score = self._score_growth(growth, symbol)
            value_score = self._score_value(value, symbol)
            risk_score = self._score_risk(risk_metrics, symbol)
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
            # 5 pillars are evaluated: quality, growth, value, risk, momentum (Positioning
            # retired as a composite pillar 2026-08-27 - see BASE_PILLAR_WEIGHTS)
            # Minimum 70% completeness (3.5/5 metrics) required per GOVERNANCE.md
            all_scores = {
                "quality": quality_score,
                "growth": growth_score,
                "value": value_score,
                "risk": risk_score,
                "momentum": momentum_score,
            }
            real_scores = [s for s in all_scores.values() if is_real_score(s)]
            data_count = len(real_scores)
            unavailable_metrics = {
                name: get_marker_reason(score) for name, score in all_scores.items() if not is_real_score(score)
            }

            # CRITICAL FIX 2026-07-19: Log when scores computed with <5 metrics for visibility.
            # Traders need to see completeness % in dashboards to filter based on GOVERNANCE entry gates.
            if data_count < 5 and data_count >= 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.info(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/5 metrics ({100.0 * data_count / 5:.1f}% complete). "
                    f"Missing: {', '.join(missing)}. Trading filter gate: completeness >= 70% per GOVERNANCE."
                )
            elif data_count < 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.warning(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/5 metrics ({100.0 * data_count / 5:.1f}% complete). "
                    f"Minimum 4 metrics ensures diversity against single-metric bias."
                )

            # NUMERIC(4,2) schema constraint: max 99.99 (not 100.0)
            # Calculate completeness on 5 pillars (quality, growth, value, risk, momentum)
            data_completeness = min(99.99, round((data_count / 5.0) * 100, 2))

            # CRITICAL FIX 2026-07-19: Compute score for all symbols with 4+/5 metrics, mark completeness for trading filters.
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
                    f"Got {data_count}/5 metrics. Cannot compute score with no metric data."
                )

            # GOVERNANCE COMPLIANCE: Compute scores with 4+/5 metrics (sufficient diversity).
            # No weight redistribution fallbacks (normalized weights stay fixed).
            # Trading gates will filter based on completeness % >= 70% per GOVERNANCE.md line 62.
            # Reason: Rejecting a few-metric-short score wastes valid signals; incomplete data is honest data marked visible.

            score_availability = {
                "quality": is_real_score(quality_score),
                "growth": is_real_score(growth_score),
                "value": is_real_score(value_score),
                "risk": is_real_score(risk_score),
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
                    f"Available {real_metric_count}/5. "
                    f"Missing: {', '.join(missing_metrics)}. "
                    f"Cannot compute even degraded score without any real data."
                )
                raise ValueError(
                    f"{symbol}: zero metrics ({real_metric_count}/5, impossible to score). "
                    f"Cannot compute score with zero available metrics."
                )

            if real_metric_count < 2:
                # Degraded mode: score with 1 metric only (for SPACs/new listings)
                logger.info(
                    f"[STOCK_SCORES] {symbol}: DEGRADED MODE - {real_metric_count}/5 metrics available. "
                    f"Computing partial score (dashboard will show data_completeness={int(real_metric_count / 5 * 100)}%)"
                )

            # Fixed base weights (no redistribution per GOVERNANCE fail-fast rule)
            # Unavailable metrics contribute 0 to composite (their weight is skipped, lost).
            # This means composite score is 0-100 scale, where:
            # - 100 = all 7 metrics perfect
            # - 50 with all 7 = truly 50/100
            # - 50 with only some pillars available = an incomplete picture (only the available
            #   pillars' weight contributed; missing pillars' weight is simply not counted)
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
            # SIZE FACTOR (market cap) - promoted to a 7th top-level pillar 2026-08-26 (Fama-
            # French SMB/Banz 1981, tested at size_proxy t=7.63 multivariate - the strongest
            # coefficient of any pillar in this file's re-audit), then REMOVED entirely the
            # same day (user directive - market cap should not be a scored input at all,
            # whether as its own pillar or folded back into Value). BASE_PILLAR_WEIGHTS above
            # is back to its pre-Size 6-pillar values. Full evidence trail for why Size was
            # promoted (and the double-counting bug that was caught along the way) is in git
            # history - see commit 869e431c3 - not repeated here since it no longer describes
            # live behavior. _score_size and its DB column/API/frontend wiring were removed;
            # the stock_scores.size_score column itself is left in the schema (unused) rather
            # than migrated away.
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
            clamped_risk = clamp_score(risk_score)
            clamped_momentum = clamp_score(momentum_score)

            # Composite: only use metrics that are actually available
            # Do NOT redistribute weights (GOVERNANCE rule: no weight redistribution)
            # If metric unavailable, its weight is skipped (contributes 0), not given to other metrics
            composite_score_value = 0.0
            for metric_name, clamped_value_score in [
                ("quality", clamped_quality),
                ("growth", clamped_growth),
                ("value", clamped_value),
                ("risk", clamped_risk),
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
                "risk": extract_score_value(clamped_risk),
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
                "risk": ["risk_metrics_daily", "technical_data_daily", "financial_statements"]
                if extract_score_value(clamped_risk)
                else [],
                "momentum": ["technical_data_daily", "market_status_daily", "insider_transaction_velocity"]
                if extract_score_value(clamped_momentum)
                else [],
            }

            # POSITIONING FULLY RETIRED 2026-08-27 (supersedes the 2026-08-26 "minimal unblock"
            # patch that used to live here - see BASE_PILLAR_WEIGHTS for the full evidence
            # trail). positioning_score no longer appears anywhere in this function: not in
            # all_scores/score_availability/the composite loop/components/data_sources, and not
            # in this result dict or snapshot_score_history()'s INSERT below. A/D rating,
            # institutional ownership, and short interest are unaffected upstream -
            # load_positioning_metrics.py keeps computing/storing them for the scores API's
            # informational positioning_inputs display; this loader just no longer reads or
            # scores them.
            result = {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": extract_score_value(clamped_quality),
                "growth_score": extract_score_value(clamped_growth),
                "value_score": extract_score_value(clamped_value),
                "momentum_score": extract_score_value(clamped_momentum),
                "risk_score": extract_score_value(clamped_risk),
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
    #   * _get_stability_metrics: 8 columns (volatility_252d through max_drawdown_1y, data_unavailable last)
    #   * _get_momentum_metrics: 5 columns (current through price_12m_ago)
    # - All _score_* functions return marker dicts if input metrics are missing/incomplete
    # - Momentum metrics: Require proper lookback periods (30d/60d/120d/252d), not degraded estimates
    # - Stock minimum: 1/5 metrics (degraded-mode scoring allowed); trading gates separately
    #   filter on data_completeness >= 70% regardless of stock age (no IPO exceptions there)
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
        earnings_growth_yoy, revenue_growth_yoy, interest_coverage). CORRECTED 2026-08-26:
        `_enhance_quality_score()` this comment referenced no longer exists - it was replaced
        entirely by `_score_quality`'s current weighted composite (see that method's own
        docstring for the current formula). Of this list, payout_ratio and interest_coverage
        are real weighted inputs in that composite today; roic_pct/fcf_to_net_income and the
        rest were tested and excluded (no independent signal) or are fetched for reference/
        display only - not all of them feed quality_score.

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
        price-volatility/risk-of-loss character, not balance-sheet fundamentals. debt_to_assets
        is scored in Quality's base quality_score formula (see _score_quality); debt_to_equity
        was scored via Quality's _score_financial_stability adjustment until the 2026-08-26
        literature audit removed it as a redundant transform of debt_to_assets ("pick D/A or
        D/E, not both") and deleted that now-dead function; revenue_concentration_hhi was
        dropped from scoring entirely per user request (not a stability signal).

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
        """Score quality metrics on 0-100 scale.

        CRITICAL: Uses only pre-computed quality_score (official model consensus). No fallback
        computation - if pre-computed score missing, returns explicit data_unavailable marker.
        For financial accuracy, missing scores are better than fabricated heuristics.

        REBUILT 2026-08-26 (Quality pillar exhaustive-input review, user-directed - supersedes
        this docstring's earlier "9-weighted-component cluster blend" description, which
        described the c568eccfe state, not the current one). The upstream quality_score
        (load_value_quality_growth_metrics.py) is now a 7-weighted-component blend, no
        clusters: ROA 18%, ROCE 18% (replaces ROIC - fixes ROIC's cash-netting coverage gap),
        Debt-to-Equity 18% (replaces Debt-to-Assets - tests stronger, t=3.12 vs 2.18), FCF
        Margin 15% (replaces Accruals Ratio - independent signal, corr=0.13), ROE 11%,
        Interest Coverage 5%, Payout Ratio 5% - renormalized over whichever are available for a
        given symbol, with a 40% minimum-available-weight floor (below that, quality_score is
        None rather than a thin-sample extrapolation - see
        load_value_quality_growth_metrics.py's quality_components comment). Weights are set
        from both full-sample t-stat magnitude AND a half-split time-stability check, not raw
        t-stat alone. Operating/Gross Profitability and Margin Volatility were tested and
        dropped entirely (no replacement candidate cleared the bar); Current Ratio was tested
        and excluded (no cross-sectional signal despite being a standard quality-investing
        checklist item).

        Altman Z''-Score ADDED then REMOVED same day (2026-08-26, user directive) - not on new
        negative evidence, but a methodological objection: the literature frames Z''-Score as a
        discrete distress-triage classifier ("quick check of economic health; if it flags a
        problem, do more detailed analysis"), not a continuously-scaled input meant to be
        averaged into a magnitude-weighted composite - independently reinforcing what the data
        already flagged as this component's weakest point (its t=3.49 came from only 41 months
        and decayed hard within that short window, t=4.40->1.39 half-split). Raw altman_z_score
        still computed/persisted for reference, unscored; where a distress-flag use belongs (if
        anywhere) is deliberately left open for later, not decided today.

        This REPLACES the previous "_enhance_quality_score" ±10-point bump layer entirely -
        every signal that layer used to bump on is now either a real weighted input in the
        base formula above, superseded by a literature-grounded replacement, or dropped as
        redundant. Splitting one quality signal across two differently-weighted functions in
        two different files was real architectural debt (user-flagged 2026-08-26) independent
        of the literature findings - collapsing to one function fixes both at once.
        _score_financial_stability/_score_dte removed as dead code (no other callers).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

        # CRITICAL: Require pre-computed quality_score. Do NOT fall back to dynamic computation -
        # that creates fabricated scores from heuristics. Missing quality_score indicates an
        # upstream issue (Phase 3 didn't run or metrics incomplete).
        if metrics.get("quality_score") is not None:
            quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
            if quality_score_value is not None:
                logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
                return quality_score_value

        # FAIL-FAST: No pre-computed score and no fallback. This is explicit data unavailability.
        logger.warning(
            f"[STOCK_SCORES] Quality score unavailable for {symbol}. "
            f"Pre-computed quality_score missing - Phase 3 may not have completed or metrics incomplete. "
            f"Returning data_unavailable marker instead of fabricated heuristic score."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_unavailable"}

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale. Returns marker dict if no real data.

        RESTORED 2026-08-26 (user directive, goal: undo the 2026-08-25 4-input reduction):
        back to the pre-08-25 14-input blend - EPS 1Y (33%) + Revenue 1Y (24%) + EPS 3Y (19%)
        + Revenue 3Y (14%) + EPS 5Y (5%) + Revenue 5Y (5%) + NI growth YoY (8%) + OI growth
        YoY (6%) + Sustainable Growth Rate (6%) + FCF growth YoY (6%) + OCF growth YoY (4%) +
        Asset Growth YoY (5%, SIGN-FLIPPED - see below) + Operating/Net Margin Trend (3% each)
        + ROE Trend (3%). User's explicit reasoning: the 2026-08-25 redesign's case for
        dropping these 10 fields rested on this system's own exploratory backtests - not
        external validated research (see the full paragraph below for detail).

        MARGIN/ROE TREND FIELDS MOVED TO QUALITY 2026-08-27 (goal: resolve this pillar's own
        placement question, flagged since the 2026-08-27 missing-metrics sweep - see MEMORY.md
        growth_missing_metrics_swept_20260827). Operating Margin Trend, Net Margin Trend, and
        ROE Trend (3% each, 9% combined) are now scored in Quality instead
        (load_value_quality_growth_metrics.py's quality_components), per Piotroski (2000 JAR)
        and Asness/Frazzini/Pedersen's Quality Minus Junk (2019) - both place improvement-in-
        profitability signals in Quality's domain (is the existing business getting more/less
        profitable), not Growth's (is the business getting bigger). This is now an 11-input
        blend; the paragraph below describes the historical 14-input restoration these 3
        fields were originally part of before this relocation.
        dropping these 10 fields rested on this system's own exploratory backtests - three
        composite-level configurations (p=0.27/0.94/0.33) plus later Fama-MacBeth reruns that
        the docstrings themselves flagged with real caveats (no true SEC filing-date data, a
        flat calendar-fiscal-year-end assumption for every symbol, and for the cleanest
        non-overlapping check only 12 independent sample years) - not external validated
        research. Rather than trust that evidentiary basis, all 14 inputs are back as the
        starting point for a fresh, more rigorous research pass (tracked separately from this
        revert).
        - EXCEPTION - asset_growth_yoy's sign fix is KEPT, not reverted: pre-08-25 this field
          was scored with growth counted as good, which is backwards per Cooper/Gulen/Schill
          (2008, JoF) and the Fama-French CMA factor (both externally peer-reviewed, not this
          system's own backtest) - low-asset-growth firms outperform high-asset-growth firms.
          This system's own panel independently replicated the direction (Spearman
          rho=-0.037, p=8.4e-6). Unlike the weight/inclusion decisions above, this specific
          correction isn't resting on the disputed self-referential evidence, so it stays
          fixed while everything else reverts. Weight reverts to its original 5% though - the
          25%/30% weight it briefly carried 2026-08-25 came from the same disputed backtest
          process as the rest of this redesign, not from independent confirmation that 5% was
          too low.
        - The underlying fields were never deleted from upstream storage
          (load_value_quality_growth_metrics.py) even while unused here, so this restores
          consumption only - no backfill needed.

        MOVED then REMOVED, both 2026-08-26 (user directive): earnings_growth_yoy was briefly
        added here as a 15th input after being moved from Quality's _enhance_quality_score,
        but removed the same day - live coverage for this field is too sparse (shows "No
        data" for most symbols in practice), so it wasn't earning its keep as either a
        Growth or Quality input. Not scored anywhere in stock_scores now. The underlying
        field is still computed/stored by load_value_quality_growth_metrics.py for potential
        future use if its coverage improves.

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

        # 1-year EPS growth: highest single weight, restored to its original 33%.
        eps_1y = _score_single_growth(metrics.get("eps_growth_1y"), 50)
        if eps_1y is not None:
            weighted_sum += eps_1y * 0.33
            total_weight += 0.33

        # 1-year revenue growth: restored to its original 24%.
        rev_1y = _score_single_growth(metrics.get("revenue_growth_1y"), 30)
        if rev_1y is not None:
            weighted_sum += rev_1y * 0.24
            total_weight += 0.24

        # 3-year EPS CAGR: sustained growth signal.
        eps_3y = _score_single_growth(metrics.get("eps_growth_3y"), 35)
        if eps_3y is not None:
            weighted_sum += eps_3y * 0.19
            total_weight += 0.19

        # 3-year revenue CAGR: sustained top-line growth.
        rev_3y = _score_single_growth(metrics.get("revenue_growth_3y"), 20)
        if rev_3y is not None:
            weighted_sum += rev_3y * 0.14
            total_weight += 0.14

        # 5-year EPS CAGR: long-term compounding quality (lower weight - worst coverage of
        # the six CAGR fields, ~38.9% of the universe).
        eps_5y = _score_single_growth(metrics.get("eps_growth_5y"), 30)
        if eps_5y is not None:
            weighted_sum += eps_5y * 0.05
            total_weight += 0.05

        # 5-year revenue CAGR: long-term top-line durability. Cap set lower than the 1y/3y
        # revenue caps since CAGR compounds and is harder to sustain longer.
        rev_5y = _score_single_growth(metrics.get("revenue_growth_5y"), 15)
        if rev_5y is not None:
            weighted_sum += rev_5y * 0.05
            total_weight += 0.05

        # Bottom-line growth trend fields: noisier single-year deltas rather than
        # multi-year CAGRs, hence the smaller individual weights.
        ni_growth = _score_single_growth(metrics.get("net_income_growth_yoy"), 40)
        if ni_growth is not None:
            weighted_sum += ni_growth * 0.08
            total_weight += 0.08

        oi_growth = _score_single_growth(metrics.get("operating_income_growth_yoy"), 40)
        if oi_growth is not None:
            weighted_sum += oi_growth * 0.06
            total_weight += 0.06

        # Sustainable growth rate = ROE * retention ratio: how fast the company can grow
        # without external financing - structurally distinct from the trailing CAGR fields
        # above, capped lower since it's already a moderated, long-run-oriented figure.
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

        # Asset growth YoY, SIGN-FLIPPED (kept from the 2026-08-25 redesign - see docstring):
        # Cooper/Gulen/Schill (2008, JoF) and the Fama-French CMA factor both show LOW asset
        # growth firms outperform HIGH asset growth firms; this system's own panel replicated
        # the direction (Spearman rho=-0.037, p=8.4e-6). Negate the raw growth rate before
        # scoring so low/negative asset growth maps to a high score. Weight restored to its
        # original 5% (the 25-30% it briefly carried came from the disputed 08-25 backtest
        # process, not from separate confirmation the field deserved that much weight).
        asset_growth = _score_single_growth(
            -metrics["asset_growth_yoy"] if metrics.get("asset_growth_yoy") is not None else None, 30
        )
        if asset_growth is not None:
            weighted_sum += asset_growth * 0.05
            total_weight += 0.05

        # Margin/ROE trend fields (operating_margin_trend/net_margin_trend/roe_trend) MOVED to
        # Quality 2026-08-27 (goal: resolve this pillar's own long-flagged placement question -
        # see MEMORY.md growth_missing_metrics_swept_20260827 and
        # load_value_quality_growth_metrics.py's quality_components comment for the literature
        # basis: Piotroski 2000 JAR / QMJ 2019 both place improvement-in-profitability signals
        # in Quality, not Growth). Scored there now with the same curve shape, unchanged weight
        # (3% each) - not removed from scoring, relocated.

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

        Uses weighted scoring: P/E (12%) + P/B (28%) + P/S (26%) + PEG (10%) + FCF yield (13%)
        + Dividend yield (4%) + Margin of Safety / DCF discount to intrinsic value (6%).
        Amihud illiquidity briefly added and removed 2026-08-26 same day (see "AMIHUD
        ILLIQUIDITY" note below) - these are back to their pre-Amihud weights, not new values.
        PE/PB/PS/FCF reweighted 2026-08-25 (see "PE-vs-PB/PS RANKING - REVERSED" note below)
        after a selection-bias fix reversed which of the three multiples is strongest.
        EV/EBITDA and EV/Revenue REMOVED 2026-08-25 (see RESOLVED note below) - duplicated
        P/E and P/S respectively, not independent signals. PE/PB/PS weighting has moved
        several times the same day and once more the day after on a corrected sample - see
        "PE-vs-PB/PS RANKING - REVERSED" note below for the ranking (PB strongest, PS second,
        PE weakest) before trusting any earlier note in this docstring's own history. Peak
        zone for growth stocks: P/E 15-30, P/B < 5, PEG < 1-2, positive FCF yield, positive
        margin of safety.

        SIZE FACTOR added 2026-08-25 as a 20%-weighted sub-component (market cap, Fama-French
        SMB / Banz 1981), tested at t=-5.37 standalone. PROMOTED to its own top-level 7th
        pillar 2026-08-26, then REMOVED entirely later the same day, both market cap's pillar
        and its scoring - user directive; see BASE_PILLAR_WEIGHTS' docstring and git history
        (commit 869e431c3) for the full trail, no longer repeated here since neither describes
        live behavior. Size's removal from THIS function specifically (to avoid double-
        counting once it briefly had its own composite slot) is what's still live: the 7
        remaining inputs above were rescaled back to their pre-Size-addition relative
        proportions (each x1.25, restoring the 100% they held before Size's 20% carve-out)
        rather than left permanently discounted for an input that no longer lives here.
        SUPERSEDED the same day by the "AMIHUD ILLIQUIDITY" note below - those same 7
        inputs were rescaled again (x0.92) a few hours later to free 8 points for the new
        Amihud sub-component, so the live weights in the code above no longer match the x1.25
        figures quoted here; this paragraph is kept for history, not current state.

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
        # REVERTED 2026-08-26: back to 12% (was briefly rescaled to 11% for Amihud
        # illiquidity, removed the same day - see "AMIHUD ILLIQUIDITY" removal note below).
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
            weighted_sum += pe_score * 0.12
            total_weight += 0.12

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors.
        # REVERTED 2026-08-26: back to 28% (was briefly rescaled to 26% for Amihud, removed
        # same day). PB is the STRONGEST of the three multiples per the selection-bias-
        # corrected rerun (see "PE-vs-PB/PS RANKING - REVERSED" note below), robust across
        # univariate, multivariate, and both sub-periods tested.
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
            weighted_sum += pb_score * 0.28
            total_weight += 0.28

        # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
        # multiples run richer than book multiples (especially for growth/SaaS names).
        # REVERTED 2026-08-26: back to 26% (was briefly rescaled to 24% for Amihud, removed
        # same day). PS held up as robust (not the weakest, not quite the strongest) across
        # the selection-bias-corrected rerun.
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
            weighted_sum += ps_score * 0.26
            total_weight += 0.26

        # PEG ratio: PE adjusted for earnings growth - <1 is classically "undervalued
        # relative to growth" (Peter Lynch heuristic), >2-3 signals growth already priced
        # in. Distinct signal from P/E (which says nothing about growth) and P/S (no
        # earnings context at all). Was fetched and displayed but carried zero weight -
        # this loader's own PEG computation (load_sec_valuations.py) previously always
        # computed a growth rate of exactly 0 (comparing TTM EPS to itself), which was
        # fixed 2026-07-20 to use a genuine prior-fiscal-year EPS; backfills on next run.
        # REVERTED 2026-08-26: back to 10% (was briefly rescaled to 9% for Amihud, removed
        # same day).
        if metrics.get("peg_ratio") is not None and metrics["peg_ratio"] > 0:
            weighted_sum += self._peg_to_score(metrics["peg_ratio"]) * 0.10
            total_weight += 0.10

        # FCF yield: positive FCF yield is healthy; > 3% is good
        # BUGFIX 2026-07-20: load_sec_valuations.py stores fcf_yield already as a percentage
        # (e.g. 2.27 = 2.27%, confirmed live: AAPL=2.27, MSFT=4.69, T=25.83) - this used to
        # re-multiply by 100 assuming a decimal fraction, so fcf_pct came out ~100x too high
        # (e.g. 227 for AAPL) and saturated fcf_score to 100 for virtually every FCF-positive
        # stock regardless of actual yield. This component was effectively a dead constant.
        # REVERTED 2026-08-26: back to 13% (was briefly rescaled to 12% for Amihud, removed
        # same day). This field's sign flipped between an earlier strict-sample test
        # (positive, t=1.62) and the selection-bias-corrected rerun (negative, t=-1.75
        # multivariate/-1.71 univariate) - genuinely sample-construction-sensitive, treated
        # as a fragile null, kept at a modest weight rather than acted on in either direction.
        if metrics.get("fcf_yield") is not None and metrics["fcf_yield"] > 0:
            fcf_pct = metrics["fcf_yield"]  # already a percentage
            fcf_score = min(100, fcf_pct * 20)  # 5% FCF yield = 100 score
            weighted_sum += fcf_score * 0.13
            total_weight += 0.13

        # Dividend yield: bonus signal for income/quality (optional). Unlike fcf_yield,
        # sec_valuations.dividend_yield (added 2026-07-20, migration 1146) is computed and
        # stored as a decimal fraction (0.03 = 3%), so the *100 conversion below is correct
        # for this field - do not "fix" it to match fcf_yield's convention.
        # Weight unchanged at 4% throughout the Amihud add/removal - kept small since this
        # field's own signal is still inconclusive (t=0.98).
        if metrics.get("dividend_yield") is not None and metrics["dividend_yield"] > 0:
            div = min(metrics["dividend_yield"] * 100, 6)  # decimal -> percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.04
            total_weight += 0.04

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
        # REVERTED 2026-08-26: back to 7% (was briefly rescaled to 6% for Amihud, removed
        # same day).
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
            weighted_sum += mos_score * 0.07
            total_weight += 0.07

        # SIZE (market cap) REMOVED from here 2026-08-26 - briefly promoted to its own
        # top-level pillar the same day, then removed from scoring entirely (user directive).
        # market_cap is not a scored input anywhere in this file now.

        # AMIHUD ILLIQUIDITY added 2026-08-26, REMOVED same day (user directive). It was
        # academically real (FM t=2.41 univariate) but scored the standard direction - MORE
        # illiquid (harder-to-trade micro-caps) = HIGHER score - which is a real, defensible
        # practical objection for a live-executing strategy: the illiquidity premium is
        # smallest-and-hardest-to-trade-name concentrated, and this system's flat 5bps/side
        # backtest slippage assumption almost certainly understates real execution cost for
        # exactly the names this component would have favored, eating into or reversing the
        # modest premium it's trying to capture. Not re-added pending a real, name-specific
        # execution-cost model rather than the current flat assumption. The underlying
        # technical_data_daily.amihud_illiquidity computation (migration 1232) is left in
        # place, unused - see the cache-removal comment near this class's __init__.

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}

    # _score_size (market cap / Fama-French SMB Size pillar) REMOVED 2026-08-26 (user
    # directive) - market cap is no longer a scored input anywhere in this file. Full history
    # (added as a Value sub-component 2026-08-25, promoted to a 7th top-level pillar
    # 2026-08-26, removed entirely the same day) is in git history - see commit 869e431c3 for
    # the promotion this reverts.

    # _score_positioning REMOVED 2026-08-27 (Positioning retired as a composite pillar - see
    # BASE_PILLAR_WEIGHTS for the full evidence trail: A/D rating null across every methodology
    # tried, including a full-history 2000-2026 re-test; institutional_ownership/short_interest
    # untestable for lack of real historical depth; the pillar-level composite proxy itself
    # never significant and sign-flips across half-splits). The method used to live here -
    # weighted A/D rating (35%) + institutional ownership (30%) + short interest (25%) + short
    # interest % change (10%) - see git history (this file, pre-2026-08-27) for the full
    # docstring and implementation if ever revisited. A/D rating/institutional ownership/short
    # interest are still computed by load_positioning_metrics.py and displayed via the scores
    # API's informational positioning_inputs field - only this synthesized composite is gone.

    def _score_risk(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score risk metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        RENAMED 2026-08-26 (user directive): Stability -> Risk. Same computation
        (volatility/beta/downside-vol/max-drawdown), name only - the underlying
        stability_metrics input table and _get_stability_metrics accessor are unchanged.

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
        cash metrics moved to Quality (at the time, via `_enhance_quality_score` - since removed
        2026-08-26; debt-to-equity is now a real 18%-weighted `_score_quality` input directly,
        not an enhancement bump - see that method's own docstring). Revenue concentration HHI
        was dropped from scoring entirely per user request.

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
        - all risk fields None → returns marker dict with reason="no_risk_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative volatility → treated as 0 (impossible case, but defensive)

        MINIMUM DATA REQUIREMENT: At least one of volatility/beta/financial_stability metrics
        must be non-NULL. If all stability metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_metrics_data"}

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
        logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol}) - no scoreable fields")
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_scores_computed"}

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
                    WHERE table_name IN ('value_metrics', 'stability_metrics', 'growth_metrics')
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
                        risk_score, rs_percentile,
                        data_completeness, updated_at
                    )
                    SELECT
                        symbol,
                        CURRENT_DATE,
                        composite_score,
                        RANK() OVER (ORDER BY composite_score DESC NULLS LAST) AS composite_rank,
                        momentum_score, quality_score, growth_score, value_score,
                        risk_score, rs_percentile,
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
                        risk_score = EXCLUDED.risk_score,
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
