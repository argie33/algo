#!/usr/bin/env python3
"""Stock Scores Loader - Multi-factor composite stock scoring.

Computes composite stock scores by aggregating:
- Quality metrics (ROE, margins, debt-to-equity ratio)
- Growth metrics (revenue growth, EPS growth)
- Value metrics (P/E, P/B, P/S ratios, dividend yield)
- Momentum/Relative Strength (1m/3m/6m/12m returns)
- Stability metrics (volatility, beta)

Positioning (A/D rating, institutional ownership, short interest) and Size (market cap) are
NOT part of the composite - both retired as top-level pillars (Positioning 2026-08-27, Size
2026-08-28, see BASE_PILLAR_WEIGHTS). Positioning's inputs are still computed/stored by
load_positioning_metrics.py and displayed via the scores API's positioning_inputs field,
informationally only. Size's input (market_cap) remains stored on value_metrics and surfaced
via the Value pillar's data - no synthesized size_score is computed anymore.

Each factor is normalized to 0-100 scale and weighted.
Final composite score is weighted average of all factors.

CRITICAL GOVERNANCE RULES:
- Minimum 1/6 metrics required for any stock score - degraded-mode scoring is allowed (SPACs/
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

# execute_values: re-exported, not called directly here - value_metrics.py's
# update_value_multiples_percentiles reaches this via `_owner().execute_values` (see that
# helper's docstring) so `patch("loaders.load_stock_scores.execute_values")` in existing tests
# keeps working.
from psycopg2.extras import execute_values  # noqa: E402, F401

from loaders.runner import run_loader  # noqa: E402
from loaders.stock_scores.growth_scoring import (  # noqa: E402
    GROWTH_INPUT_IMPLAUSIBLE_PCT,
    GROWTH_MIN_FIELDS_AVAILABLE,
    GROWTH_SCORE_FIELDS,
    GrowthScoringMixin,
)
from loaders.stock_scores.momentum_scoring import MomentumScoringMixin  # noqa: E402
from loaders.stock_scores.pillar_weights import (  # noqa: E402
    BASE_PILLAR_WEIGHTS,
    VALUE_RISK_INTERACTION_MAX_SHIFT,
    _value_risk_adjusted_weights,
)
from loaders.stock_scores.quality_scoring import QualityScoringMixin  # noqa: E402
from loaders.stock_scores.risk_scoring import (  # noqa: E402
    NEAR_ZERO_LIQUIDITY_THRESHOLD,
    RISK_MIN_WEIGHT_AVAILABLE,
    RiskScoringMixin,
)
from loaders.stock_scores.value_metrics import ValueMetricsMixin  # noqa: E402
from loaders.stock_scores.value_score import ValueScoreMixin  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.type_conversion import safe_float  # noqa: E402

logger = logging.getLogger(__name__)

# BASE_PILLAR_WEIGHTS / VALUE_RISK_INTERACTION_MAX_SHIFT (from pillar_weights.py) and
# GROWTH_SCORE_FIELDS / GROWTH_INPUT_IMPLAUSIBLE_PCT / GROWTH_MIN_FIELDS_AVAILABLE (from
# growth_scoring.py) and RISK_MIN_WEIGHT_AVAILABLE / NEAR_ZERO_LIQUIDITY_THRESHOLD (from
# risk_scoring.py) are re-exported here, not used directly in this file - existing external
# consumers (algo/research/*.py, dashboard/panels/scores.py, several tests) import these names
# directly from loaders.load_stock_scores and must keep working unchanged after the
# 2026-09-05 bloaters-decomposition split moved their real definitions into loaders/stock_scores/.
# __all__ marks them as an intentional re-export - otherwise mypy --strict's implicit-reexport
# check (bundled into `strict = true`) treats a plain pass-through import as private to this
# module and flags every external `from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS`
# (etc.) as accessing an attribute this module doesn't "explicitly export".
__all__ = [
    "BASE_PILLAR_WEIGHTS",
    "GROWTH_INPUT_IMPLAUSIBLE_PCT",
    "GROWTH_MIN_FIELDS_AVAILABLE",
    "GROWTH_SCORE_FIELDS",
    "NEAR_ZERO_LIQUIDITY_THRESHOLD",
    "RISK_MIN_WEIGHT_AVAILABLE",
    "VALUE_RISK_INTERACTION_MAX_SHIFT",
    "StockScoresLoader",
]


class StockScoresLoader(
    OptimalLoader,
    QualityScoringMixin,
    GrowthScoringMixin,
    ValueScoreMixin,
    ValueMetricsMixin,
    RiskScoringMixin,
    MomentumScoringMixin,
):
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
            # always NULL" premise.
            # eps_growth_stability added 2026-08-25: computed by
            # load_value_quality_growth_metrics.py (stddev of trailing 4-quarter EPS growth
            # rates) and stored at 67.8% coverage. Still a genuinely dead fetch - it's a
            # dispersion metric (lower=more consistent), not a growth-rate on the same
            # higher-is-better scale as GROWTH_SCORE_FIELDS, so it isn't a candidate for the
            # 2026-08-28 multi-input restore below; fetched for reference/display only.
            # quarterly_growth_momentum/earnings_growth_4q_avg added 2026-08-28 (goal: restore
            # multi-input Growth blend - see GROWTH_SCORE_FIELDS/_score_growth): both computed
            # by _compute_quarterly_metrics in load_value_quality_growth_metrics.py (the loader
            # that runs in the local dev pipeline) and mirrored into BOTH growth_metrics and
            # quality_metrics by that same loader's _insert_growth_metrics/_insert_quality_metrics
            # (verified directly in that file's INSERT column lists, not assumed from an older
            # docstring here) - previously fetched here (quarterly_growth_momentum only) and
            # left completely unscored on a deliberate-but-since-overridden scope decision.
            # Read off growth_metrics's own copy here rather than merging in quality_metrics's -
            # both hold the same value, and every other GROWTH_SCORE_FIELDS candidate is already
            # a growth_metrics column, so this keeps _score_growth reading one dict, one table.
            #
            # forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy
            # added 2026-08-31 (goal: growth-pillar industry-alignment review - see
            # GROWTH_SCORE_FIELDS below for the full rationale): forward/analyst-consensus EPS
            # growth is the headline Growth descriptor in MSCI/Russell/S&P's own published
            # methodologies and this repo's Growth blend was entirely backward-looking without
            # it. eps_estimate_revision_90d_pct fetched too but stays informational-only (a
            # revision-momentum signal, not a growth-rate level - not a GROWTH_SCORE_FIELDS
            # candidate).
            cur.execute(
                "SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, "
                "eps_growth_1y, eps_growth_3y, eps_growth_5y, book_value_growth, "
                "net_income_growth_yoy, operating_income_growth_yoy, sustainable_growth_rate, "
                "fcf_growth_yoy, ocf_growth_yoy, "
                "gross_margin_trend, operating_margin_trend, net_margin_trend, roe_trend, asset_growth_yoy, "
                "eps_growth_stability, quarterly_growth_momentum, earnings_growth_4q_avg, "
                "forward_eps_growth_current_fy, forward_eps_growth_next_fy, forward_revenue_growth_next_fy, "
                "eps_estimate_revision_90d_pct, "
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
            # pe_ratio_unavailable_reason/forward_pe_unavailable_reason added 2026-08-28
            # (goal: "is this value score right per industry best practice" - the E/P vs P/E
            # gap): live-confirmed 2283/2519 pe_ratio NULLs and 848/1560 forward_pe
            # "no_analyst_estimates" rows are actually unprofitable/negative-forecast-earnings
            # companies (real values, just not ratio-able), not missing data - see
            # _score_value's PE/Forward P/E blocks for how these are now used.
            # pb_ratio_unavailable_reason added 2026-09-05 (real-money-readiness audit): same
            # "unprofitable/undefined-ratio silently skipped instead of scored at the floor"
            # bug class already fixed for pe_ratio/forward_pe above, found unfixed for pb_ratio
            # (negative book value) - see _score_value's P/B block for how this is now used.
            cur.execute(
                "SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, "
                "forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct, market_cap, net_payout_yield, "
                "pe_ratio_unavailable_reason, forward_pe_unavailable_reason, pb_ratio_unavailable_reason, "
                "data_unavailable FROM value_metrics"
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

            # GOVERNANCE 2026-09-01 (goal session - user directive: "figure out what is best"
            # after observing untradeable micro-caps topping Risk's "safest" list; see
            # [[momentum_ads_warrant_leak_fixed_and_pillar_sweep_20260901]]'s liquidity-gap
            # finding). Same 20-trading-day average(volume*close) definition
            # algo/risk/liquidity_checks.py's _check_dollar_volume already uses for the
            # trade-eligibility gate (min_adv_dollars=$500K in algo_config) - deliberately the
            # SAME metric family this codebase already trusts operationally, not a new concept.
            # A 45-calendar-day lookback (vs that check's 25) comfortably covers 20 real trading
            # days including holidays without per-signal-date precision requirements this batch
            # query doesn't need. See _score_risk's docstring for why this is scored as a
            # tradability-RISK penalty, not an academic illiquidity-return-premium reward
            # (opposite signs - this codebase already tested the premium direction in
            # algo/research/fama_macbeth_liquidity_factor.py; using that sign here would reward
            # the exact thin names this input exists to flag).
            cur.execute(
                """
                WITH ranked AS (
                    SELECT symbol, volume, close,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                )
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d
                FROM ranked
                WHERE rn <= 20
                GROUP BY symbol
                """
            )
            self._liquidity_cache: dict[str, float] = {
                row[0]: safe_float(row[1], f"{row[0]}.avg_dollar_volume_20d", allow_none=False)
                for row in cur.fetchall()
            }

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

    def _compute_stock_score(self, symbol: str) -> dict[str, Any]:
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
                # Merged in regardless of stability's own data_unavailable state - _score_risk's
                # early-return guard already handles that case before looking at any individual
                # field, so this is safe either way. See _prepare_batch_context's liquidity-cache
                # query docstring for what this value is and why it's scored as a Risk input.
                risk_metrics["avg_dollar_volume_20d"] = self._liquidity_cache.get(symbol)
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
            # REAL-MONEY-READINESS FIX (2026-09-07): isinstance(nan, float) is True, so a
            # NaN/Inf score used to pass this check as "real data" - a data-quality bug
            # anywhere upstream (e.g. an unguarded 0/0 ratio) would silently count as an
            # available pillar instead of being excluded. math.isfinite() rejects both
            # nan and +/-inf so a non-finite score is treated the same as a marker dict.
            def is_real_score(result: float | dict[str, Any] | None) -> bool:
                return isinstance(result, float) and math.isfinite(result)

            def get_marker_reason(result: float | dict[str, Any] | None) -> str:
                if isinstance(result, dict) and result.get("data_unavailable"):
                    reason = result.get("reason")
                    if isinstance(reason, str):
                        return reason
                if isinstance(result, float) and not math.isfinite(result):
                    return "non_finite_score_nan_or_inf"
                return "unknown_reason"

            # Count data completeness: only float scores count as "real data"
            # Markers (dicts with data_unavailable=True) are excluded from count
            # Session 260: Momentum loader now fixed and included in completeness calculation
            # 5 pillars are evaluated: quality, growth, value, risk, momentum (Positioning
            # retired as a composite pillar 2026-08-27; Size retired as a composite pillar
            # 2026-08-28 - see BASE_PILLAR_WEIGHTS)
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
            # REAL-MONEY-READINESS FIX (2026-09-07 pre-live audit): this used to be a flat
            # pillar COUNT (data_count/5), so a symbol missing "value" (27% of
            # BASE_PILLAR_WEIGHTS, the single largest pillar) reported the exact same 80%
            # completeness as one missing "momentum" (10% of the weight) - both cleared the
            # same >=70% GOVERNANCE trading-eligibility gate (phase7_signal_generation.py's
            # composite_score ranking, phase8_entry_execution.py's concentration-limited
            # entry queue) identically, even though the real impact on composite_score's
            # ceiling differs by ~3x between those two cases. Weight completeness by each
            # available pillar's actual share of BASE_PILLAR_WEIGHTS instead of a flat
            # per-pillar count, so the gate reflects how much of the composite is actually
            # backed by real data, not just how many of 5 slots are filled.
            available_weight = sum(
                BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores.items() if is_real_score(score)
            )
            data_completeness = min(99.99, round(available_weight * 100, 2))

            # CRITICAL FIX 2026-07-19: Compute score for all symbols with 5+/6 metrics, mark completeness for trading filters.
            # Previous: Rejected any score with <70% completeness, removing 1,635 valid candidates from universe.
            # New: Calculate scores for all candidates with sufficient diversity (5+ metrics), let trading logic
            # (entry gates) filter based on completeness %. This gives traders full visibility + control.
            # GOVERNANCE.md says: "Signals < 70% completeness are excluded from scoring" (trading exclusion, not computation exclusion).
            # The minimum 5 metrics check below ensures sufficient diversity to prevent single-metric bias.
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
            # - 100 = all 5 metrics perfect
            # - 50 with all 5 = truly 50/100
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
            # SIZE FACTOR (market cap) - retired entirely 2026-08-28 (user directive: "just
            # get rid of size"). See BASE_PILLAR_WEIGHTS' own comment for the full history and
            # evidence trail - not repeated here. BASE_PILLAR_WEIGHTS above is a 5-pillar dict
            # again (quality/growth/value/risk/momentum).
            # Clamp scores to 0-100, keep markers for missing data
            def clamp_score(score: float | dict[str, Any] | None) -> float | dict[str, Any] | None:
                if isinstance(score, float):
                    # REAL-MONEY-READINESS FIX (2026-09-07): min(100.0, nan) evaluates to
                    # 100.0 in Python (nan comparisons are always False, so the replacement
                    # never happens) - a NaN/Inf score used to silently clamp to a *perfect*
                    # 100.0 instead of being rejected, and that 100.0 would then be stored
                    # directly in the DB column via extract_score_value(). Convert to a
                    # marker dict instead, matching is_real_score's non-finite rejection above.
                    if not math.isfinite(score):
                        return {"data_unavailable": True, "reason": "non_finite_score_nan_or_inf"}
                    return max(0.0, min(100.0, score))
                # Return marker dicts as-is; don't silence them with None
                return score if isinstance(score, dict) else None

            clamped_quality = clamp_score(quality_score)
            clamped_growth = clamp_score(growth_score)
            clamped_value = clamp_score(value_score)
            clamped_risk = clamp_score(risk_score)
            clamped_momentum = clamp_score(momentum_score)

            # VALUE x RISK INTERACTION: see VALUE_RISK_INTERACTION_MAX_SHIFT's module-level
            # docstring for the evidence. Conditions Value's/Risk's own weights on THIS symbol's
            # real risk_score (falls back to unmodified base weights if Risk is unavailable, same
            # as clamped_risk being None below).
            normalized_weights = _value_risk_adjusted_weights(clamped_risk if isinstance(clamped_risk, float) else None)

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

            # POSITIONING FULLY RETIRED 2026-08-27, SIZE FULLY RETIRED 2026-08-28 (see
            # BASE_PILLAR_WEIGHTS for the full evidence trail on both). Neither positioning_score
            # nor size_score appears anywhere in this function anymore: not in
            # all_scores/score_availability/the composite loop/components/data_sources, and not
            # in this result dict or snapshot_score_history()'s INSERT below. Positioning's A/D
            # rating, institutional ownership, and short interest are unaffected upstream -
            # load_positioning_metrics.py keeps computing/storing them for the scores API's
            # informational positioning_inputs display; this loader just no longer reads or
            # scores them. Size's market_cap likewise keeps being computed/stored on
            # value_metrics unaffected - this loader just no longer synthesizes a size_score
            # from it.
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
                # reason_type ADDED 2026-09-01 (/goal session, "make sure results make sense"
                # investigation). This dict is written on every non-exceptional pass through
                # _compute_stock_score, but previously never included "reason_type" at all -
                # only fetch_incremental's two exception-handling branches set it, to
                # "loader_failed". Since BulkInsertManager derives each row's UPSERT column
                # list from that row's own dict keys (see bulk_insert_manager.py), a symbol
                # that failed once (reason_type='loader_failed' persisted) and later recovered
                # never had reason_type in its column list on the recovery write - the stale
                # 'loader_failed' value was silently carried forward FOREVER, untouched by
                # every subsequent successful re-score. Live-confirmed 2026-09-01: symbols
                # (including NVDA, BRK.A, BRK.B, BYND) sat at reason_type='loader_failed'
                # despite full completeness and real scored pillars - a false-failure signal
                # that would mislead exactly this kind of "why is data missing" triage. Always
                # writing "unknown" here (this loader's own reason_text messages are plain
                # completeness-threshold strings, never the "loader_failed:"/"not_applicable:"/
                # "unavailable_temporary:" prefixes utils/loaders/unavailable_markers.py's
                # extract_reason_type() checks for for other loaders' governance markers, so it
                # would resolve to "unknown" here regardless) matches the column's own DEFAULT
                # and every other successful row already in the table - it just also now
                # actively RESETS a stale 'loader_failed' on recovery instead of leaving it out
                # of the write entirely.
                "reason_type": "unknown",
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
    #   * _get_value_metrics: 15 columns (pe_ratio through forward_pe_unavailable_reason, data_unavailable last)
    #   * _get_stability_metrics: 8 columns (volatility_252d through max_drawdown_1y, data_unavailable last)
    #   * _get_momentum_metrics: 5 columns (current through price_12m_ago)
    # - All _score_* functions return marker dicts if input metrics are missing/incomplete
    # - Momentum metrics: Require proper lookback periods (30d/60d/120d/252d), not degraded estimates
    # - Stock minimum: 1/6 metrics (degraded-mode scoring allowed); trading gates separately
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

    # _score_size/_size_curve_score REMOVED 2026-08-28 (Size retired as a composite pillar -
    # see BASE_PILLAR_WEIGHTS for the full evidence trail: size_proxy's strong imputed-regime
    # coefficient reconfirmed as substantially an MNAR data-coverage artifact even after fixing
    # the specific coverage bugs the user required first; direct user directive "just get rid
    # of size"). market_cap itself is NOT deleted - value_metrics.market_cap keeps being
    # computed/stored unchanged by load_value_quality_growth_metrics.py, just no longer scored
    # into its own 0-100 size_score here.

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
        # Must run before snapshot_score_history() so the history snapshot captures the
        # CORRECTED value_score/composite_score, not Pass 1's provisional fixed-curve values -
        # see update_value_multiples_percentiles()'s own docstring for the full evidence trail.
        self.update_value_multiples_percentiles()
        # update_size_percentiles() REMOVED 2026-08-28 (Size retired as a composite pillar -
        # see BASE_PILLAR_WEIGHTS for the full evidence trail).
        self.snapshot_score_history()
        self.audit_upstream_coverage()

    # MIN_SECTOR_SLICE: a sector/GICS group needs at least this many symbols in the current
    # run's universe before its own within-sector percentile is trusted; smaller groups fall
    # back to the plain universe-wide percentile for just their members (fails open, mirrors
    # `_get_symbol_sector`'s own fail-open convention in load_value_quality_growth_metrics.py).
    # Live sector sizes in the scored universe are all far above this (smallest ~117 symbols,
    # see SECTOR-RELATIVE VALUE RANKING docstring note below) - this floor exists for
    # 'Unclassified' (company_profile.sector missing/NULL) and any genuinely thin group, not
    # the normal case.

    # update_size_percentiles() REMOVED 2026-08-28 (Size retired as a composite pillar - see
    # BASE_PILLAR_WEIGHTS for the full evidence trail).

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
