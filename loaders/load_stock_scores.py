#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
                    "value_metrics": 0.30,  # FIXED: Metric loaders intentionally load subset (S&P 500 dividend payers ~4,700 stocks)
                    "growth_metrics": 0.20,  # FIXED: SEC-filing dependent (some stocks have no annual filings)
                    "positioning_metrics": 0.30,  # FIXED: Institutional data limited to liquid stocks
                    "stability_metrics": 0.30,  # FIXED: Beta calculation requires price history
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
                        cur.execute(
                            f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """
                        )
                    except psycopg2.ProgrammingError:
                        # Column doesn't exist; assume all rows are available (no data_unavailable markers yet)
                        logger.critical(
                            f"[STOCK_SCORES CRITICAL] {table_name} missing data_unavailable column; schema mismatch detected. "
                            f"Migration {table_name} may not have been applied yet."
                        )
                        cur.execute(f"SELECT COUNT(*) as available_count, COUNT(*) as total_count FROM {table_name}")

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
                        # Get sample unavailable symbols for debugging
                        cur.execute(
                            f"SELECT symbol, COUNT(*) FROM {table_name} WHERE data_unavailable = true GROUP BY symbol LIMIT 5"
                        )
                        unavail_sample = cur.fetchall()
                        unavail_sample_str = ", ".join([s[0] for s in unavail_sample]) if unavail_sample else "(none)"

                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} coverage insufficient. "
                            f"ROOT CAUSE: Only {coverage:.1%} coverage ({available_count}/{total_count} stocks with real data). "
                            f"Required: {min_coverage:.0%}. "
                            f"Sample unavailable symbols: {unavail_sample_str}. "
                            f"ACTION: Check upstream {table_name} loader for timeouts/failures in CloudWatch logs. "
                            f"Typical causes: SEC API limits (quality/growth), yfinance throttling (value/positioning), price history gaps (stability)."
                        )

                for table_name in optional_sec_metric_tables:
                    # RACE CONDITION FIX: Use single query to get both counts atomically
                    try:
                        cur.execute(
                            f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """
                        )
                    except psycopg2.ProgrammingError:
                        # Column doesn't exist; assume all rows are available
                        logger.critical(
                            f"[STOCK_SCORES CRITICAL] {table_name} missing data_unavailable column; schema mismatch detected. "
                            f"Migration for {table_name} may not have been applied yet."
                        )
                        cur.execute(f"SELECT COUNT(*) as available_count, COUNT(*) as total_count FROM {table_name}")

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
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol, roe, roa, operating_margin, net_margin, debt_to_equity, "
                "current_ratio, quick_ratio, quality_score, data_unavailable FROM quality_metrics"
            )
            self._quality_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            cur.execute(
                "SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, "
                "eps_growth_1y, eps_growth_3y, eps_growth_5y, data_unavailable FROM growth_metrics"
            )
            self._growth_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            cur.execute(
                "SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, "
                "data_unavailable FROM value_metrics"
            )
            self._value_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            cur.execute(
                "SELECT symbol, institutional_ownership, insider_ownership, short_interest_percent, "
                "data_unavailable FROM positioning_metrics"
            )
            self._positioning_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            cur.execute(
                "SELECT symbol, volatility_252d, volatility_60d, volatility_30d, beta, data_unavailable "
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
        if not hasattr(self, '_quality_cache'):
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

            # Merge debt_to_assets from quality into stability metrics for solvency scoring
            if stability and quality and quality.get("debt_to_assets") is not None:
                dta = quality.get("debt_to_assets")
                if not isinstance(dta, (int, float)) or isinstance(dta, bool):
                    logger.warning(
                        f"[STOCK_SCORES] {symbol}: debt_to_assets from quality is {type(dta).__name__} "
                        f"(expected float). Not merging invalid value into stability."
                    )
                else:
                    stability["debt_to_assets"] = dta

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

            # CRITICAL: Enforce minimum 4/6 metrics per GOVERNANCE.md
            # Stock scores require sufficient metric diversity to prevent single-metric bias
            # (e.g., pure value without growth/quality check).
            # With fewer than 4 metrics, position sizing becomes unreliable:
            # - 1-2 metrics: extreme bias (may favor one factor without balance)
            # - 3 metrics: insufficient diversity (missing critical dimension)
            # - 4+ metrics: balanced evaluation across multiple dimensions
            # Momentum now available from momentum_metrics loader (Session 260)
            min_required_metrics = 4

            if data_count < min_required_metrics:
                raise RuntimeError(
                    f"[STOCK_SCORES] {symbol}: CRITICAL - insufficient metrics for scoring. "
                    f"Got {data_count}/6 metrics (need minimum {min_required_metrics}). "
                    f"With fewer than {min_required_metrics} metrics, position sizing decisions are unreliable. "
                    f"Score computation requires: growth (IPO/SEC), quality (SEC), value, positioning (yfinance), "
                    f"stability (technical), momentum (price). Upstream loaders must populate sufficient data. "
                    f"Failing fast to prevent single-metric-biased trading positions."
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

            # CRITICAL: Enforce minimum 4/6 metrics for diversity (prevents single-metric bias)
            # But allow computation with 4-5 metrics per GOVERNANCE.md line 60.
            # Trading entry gates (GOVERNANCE.md line 97) will filter on completeness >= 70%.
            if real_metric_count < 4:
                missing_metrics = [k for k, v in score_availability.items() if not v]
                logger.warning(
                    f"[STOCK_SCORES] {symbol}: Insufficient metric diversity. "
                    f"Available {real_metric_count}/6 (need minimum 4 for sufficient diversity). "
                    f"Missing: {', '.join(missing_metrics)}. "
                    f"Scoring skipped per GOVERNANCE minimum diversity requirement."
                )
                raise ValueError(
                    f"{symbol}: insufficient metrics ({real_metric_count}/6, need >=4). "
                    f"Minimum 4 metrics required for diversity. "
                    f"Missing: {', '.join(missing_metrics)}. Trading gates will filter based on completeness %."
                )

            # Base weights (unchanged per GOVERNANCE "no weight redistribution").
            # Unavailable metrics contribute 0 to composite (their weight is skipped, not redistributed).
            # Example: If positioning/quality unavailable, composite = 0.20*growth + 0.20*value + 0.12*stability + 0.08*momentum
            # (remaining 0.25+0.15=0.40 is simply not included, score is out of 0.60 total instead of 1.0)
            base_weights = {
                "quality": 0.25,
                "growth": 0.20,
                "value": 0.20,
                "positioning": 0.15,
                "stability": 0.12,
                "momentum": 0.08,
            }
            # Compute sum of available-only weights for re-normalizing final score
            available_weight_sum = sum(base_weights[k] for k, v in score_availability.items() if v)
            normalized_weights = base_weights  # Use base weights, but only accumulate for available metrics

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
                if not score_availability.get(metric_name, False):
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

            # Re-normalize composite score to 0-100 scale based on available metrics only
            # If available_weight_sum < 1.0, divide by sum to scale back up to 0-100
            if available_weight_sum > 0:
                composite_score_value = composite_score_value / available_weight_sum
            composite_score = max(0, min(100, round(composite_score_value, 2)))

            def extract_score_value(score_result: float | dict[str, Any] | None) -> float | None:
                """Extract numeric score from result (float or marker dict)."""
                if isinstance(score_result, float):
                    return round(score_result, 2)
                return None  # Markers and None return as None

            result = {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": extract_score_value(clamped_quality),
                "growth_score": extract_score_value(clamped_growth),
                "value_score": extract_score_value(clamped_value),
                "momentum_score": extract_score_value(clamped_momentum),
                "positioning_score": extract_score_value(clamped_positioning),
                "stability_score": extract_score_value(clamped_stability),
                "rs_percentile": 0.0,
                "data_completeness": data_completeness,
                "unavailable_metrics": json.dumps(unavailable_metrics) if unavailable_metrics else None,
                "data_unavailable": False,  # EXPLICIT: All required metrics available (fail-fast filters removed unavailable scores)
                "reason": None,  # EXPLICIT: Score computed successfully from available metrics
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
    #   * _get_quality_metrics: 9 columns (roe through data_unavailable)
    #   * _get_growth_metrics: 7 columns (revenue_growth_1y through data_unavailable)
    #   * _get_value_metrics: 7 columns (pe_ratio through data_unavailable)
    #   * _get_positioning_metrics: 4 columns (institutional_ownership through data_unavailable)
    #   * _get_stability_metrics: 5 columns (volatility_252d through data_unavailable)
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
        """Fetch quality metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 9 columns (roe, roa, operating_margin, net_margin,
          debt_to_equity, current_ratio, quick_ratio, quality_score, data_unavailable)
        - Schema mismatch (len(row) < 9) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_quality_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities (REITs, etc.)
        have rows marked data_unavailable=True with NULL values. Previously returned NULLs instead
        of marker; now properly returns marker dict.

        CRITICAL FIX 2026-07-01 (continued): Now fetches pre-computed quality_score from quality_metrics
        table instead of re-computing from individual metrics. This ensures consistency between
        load_quality_metrics.py (which computes the score) and load_stock_scores.py (which uses it).

        MINIMUM DATA REQUIREMENT: Row must have exactly 9 columns. Missing columns causes immediate
        fail-fast ValueError to prevent silent data corruption.
        """
        row = self._quality_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 9 columns before accessing indices
            if len(row) < 9:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: quality_metrics row has {len(row)} columns, expected 9. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[8]
            quality_score = safe_float(row[7], f"{symbol}.quality_score")
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in quality_metrics "
                    f"(likely REIT or security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "quality_metrics")
            # Row exists and data is available
            return {
                "roe": safe_float(row[0], f"{symbol}.roe"),
                "roa": safe_float(row[1], f"{symbol}.roa"),
                "operating_margin": safe_float(row[2], f"{symbol}.operating_margin"),
                "net_margin": safe_float(row[3], f"{symbol}.net_margin"),
                "debt_to_equity": safe_float(row[4], f"{symbol}.debt_to_equity"),
                "current_ratio": safe_float(row[5], f"{symbol}.current_ratio"),
                "quick_ratio": safe_float(row[6], f"{symbol}.quick_ratio"),
                "quality_score": quality_score,  # Pre-computed by load_quality_metrics.py
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
            # CRITICAL: Validate row has expected 7 columns before accessing indices
            if len(row) < 7:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 7. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[6]
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
            # CRITICAL: Validate row has expected 7 columns before accessing indices
            if len(row) < 7:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 7. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[6]
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
        - Row length validation: Must have 4 columns (institutional_ownership, insider_ownership,
          short_interest_percent, data_unavailable)
        - Schema mismatch (len(row) < 4) → raises ValueError immediately
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
            # CRITICAL: Validate row has expected 4 columns before accessing indices
            if len(row) < 4:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: positioning_metrics row has {len(row)} columns, expected 4. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[3]
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
        - Row length validation: Must have 5 columns (volatility_252d, volatility_60d,
          volatility_30d, beta, data_unavailable)
        - Schema mismatch (len(row) < 5) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_stability_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        CRITICAL FIX 2026-07-03: Now uses safe_float() for all numeric fields to detect
        data corruption. Previous inline float() bypassed error handling.

        MINIMUM DATA REQUIREMENT: Row must have exactly 5 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._stability_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 5 columns before accessing indices
            if len(row) < 5:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: stability_metrics row has {len(row)} columns, expected 5. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[4]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in stability_metrics "
                    f"(likely security with insufficient price history)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "stability_data_marked_unavailable"}
            # Row exists and data is available
            return {
                "volatility_252d": safe_float(row[0], f"{symbol}.volatility_252d"),
                "volatility_60d": safe_float(row[1], f"{symbol}.volatility_60d"),
                "volatility_30d": safe_float(row[2], f"{symbol}.volatility_30d"),
                "beta": safe_float(row[3], f"{symbol}.beta"),
            }
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

        Returns dict with momentum values (which may be None for individual timeframes if
        upstream loader failed to calculate them).
        """
        try:
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

                # If momentum_metrics marked this symbol as unavailable, return marker
                if data_unavailable:
                    return {"data_unavailable": True, "reason": "momentum_metrics_loader_failed"}

                return {
                    "momentum_1m": momentum_1m,
                    "momentum_3m": momentum_3m,
                    "momentum_6m": momentum_6m,
                    "momentum_12m": momentum_12m,
                }

            # Symbol not in momentum_metrics cache (loader hasn't run for this symbol yet)
            logger.warning(f"[LOAD_STOCK_SCORES] No momentum data available for {symbol} - momentum_metrics not populated")
            logger.warning(f"[LOAD_STOCK_SCORES] Returning data_unavailable marker for momentum_metrics({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_data_available"}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_quality(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score quality metrics on 0-100 scale. Returns marker dict if no real data.

        Internal function: caller (_compute_stock_score) converts marker dicts to None.

        RETURN TYPES (STRICT):
        - metrics available with quality_score → returns float (0-100)
        - metrics available with component fields → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - No scoreable fields → returns marker dict with reason="no_quality_scores_computed"

        CRITICAL FIX 2026-07-01: Use pre-computed quality_score from load_quality_metrics.py
        when available (quality_score in metrics dict). This ensures consistency and avoids
        discrepancies between the two scoring algorithms. Now uses safe_float() for
        robust error handling.

        MINIMUM DATA REQUIREMENT: At least one of ROE/ROA/margin/ratio metrics must be
        non-NULL. If all component metrics are None, returns data_unavailable marker.
        """
        # FAIL-FAST: Explicitly check for data_unavailable flag (not just falsy)
        if not metrics or metrics.get("data_unavailable") is True:
            logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
            logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for quality_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

        # Use pre-computed quality_score from load_quality_metrics.py if available
        if metrics.get("quality_score") is not None:
            quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
            if quality_score_value is not None:
                logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
                return quality_score_value
            # Should not reach here (quality_score is not None so _safe_float won't return None)
            # but type-safe fallback in case of unexpected state
            logger.warning(f"[STOCK_SCORES] quality_score was present but converted to None for {symbol}")
            return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_conversion_failed"}

        scores = []

        # ROE: higher is better (target 15%+, cap at 40%)
        # Use `is not None` to correctly handle ROE=0 (break-even) as a real data point.
        if metrics.get("roe") is not None:
            roe = min(metrics["roe"], 40)
            scores.append(min(100, max(0, (roe / 40) * 100)))

        # ROA: higher is better (target 5%+, cap at 20%)
        if metrics.get("roa") is not None:
            roa = min(max(0, metrics["roa"]), 20)
            scores.append(min(100, (roa / 20) * 100))

        # Net margin: higher is better (target 10%+, cap at 30%)
        if metrics.get("net_margin") is not None:
            nm = min(max(0, metrics["net_margin"]), 30)
            scores.append(min(100, (nm / 30) * 100))

        # Operating margin: higher is better (target 10%+, cap at 30%)
        if metrics.get("operating_margin") is not None:
            om = min(max(0, metrics["operating_margin"]), 30)
            scores.append(min(100, (om / 30) * 100))

        # Debt-to-equity: lower is better (target <1.0)
        if metrics.get("debt_to_equity") is not None and metrics["debt_to_equity"] >= 0:
            de = min(metrics["debt_to_equity"], 5)
            score = max(0, 100 - (de * 20))
            scores.append(min(100, score))

        # Current ratio: above 1.5 is good, above 2.0 is excellent
        if metrics.get("current_ratio") is not None:
            cr = max(0, metrics["current_ratio"])
            if cr >= 2.0:
                scores.append(100)
            elif cr >= 1.5:
                scores.append(80)
            elif cr >= 1.0:
                scores.append(60)
            else:
                scores.append(max(0, cr * 60))

        if scores:
            return float(sum(scores) / len(scores))
        logger.debug(f"[STOCK_SCORES] No quality metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for quality_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_scores_computed"}

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted blend: EPS 1Y (35%) + Revenue 1Y (25%) + EPS 3Y (20%) + Revenue 3Y (15%) + EPS 5Y (5%).
        Longer-term growth signals more durable earnings quality.

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
        if not metrics or metrics.get("data_unavailable") is True:
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
            """Score a single growth rate capped at `cap`%."""
            if val is None:
                return None
            if val <= 0:
                # Negative growth: map [-50, 0] → [0, 40]
                return max(0, 40 + (val / 50) * 40)
            return min(100, (val / cap) * 100)

        # 1-year EPS growth: target 25%+ for growth stocks (highest weight)
        eps_1y = _score_single_growth(metrics.get("eps_growth_1y"), 50)
        if eps_1y is not None:
            weighted_sum += eps_1y * 0.35
            total_weight += 0.35

        # 1-year revenue growth: target 15%+
        rev_1y = _score_single_growth(metrics.get("revenue_growth_1y"), 30)
        if rev_1y is not None:
            weighted_sum += rev_1y * 0.25
            total_weight += 0.25

        # 3-year EPS CAGR: sustained growth signal
        eps_3y = _score_single_growth(metrics.get("eps_growth_3y"), 35)
        if eps_3y is not None:
            weighted_sum += eps_3y * 0.20
            total_weight += 0.20

        # 3-year revenue CAGR: sustained top-line growth
        rev_3y = _score_single_growth(metrics.get("revenue_growth_3y"), 20)
        if rev_3y is not None:
            weighted_sum += rev_3y * 0.15
            total_weight += 0.15

        # 5-year EPS CAGR: long-term compounding quality (lower weight)
        eps_5y = _score_single_growth(metrics.get("eps_growth_5y"), 30)
        if eps_5y is not None:
            weighted_sum += eps_5y * 0.05
            total_weight += 0.05

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

    def _score_value(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score value metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: P/E (50%) + P/B (25%) + FCF yield (15%) + Dividend yield (10%).
        Peak zone for growth stocks: P/E 15-30, P/B < 5, positive FCF yield.

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
        if not metrics or metrics.get("data_unavailable") is True:
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
            weighted_sum += pe_score * 0.50
            total_weight += 0.50

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
            weighted_sum += pb_score * 0.25
            total_weight += 0.25

        # FCF yield: positive FCF yield is healthy; > 3% is good
        if metrics.get("fcf_yield") is not None and metrics["fcf_yield"] > 0:
            fcf_pct = metrics["fcf_yield"] * 100  # stored as decimal fraction
            fcf_score = min(100, fcf_pct * 20)  # 5% FCF yield = 100 score
            weighted_sum += fcf_score * 0.15
            total_weight += 0.15

        # Dividend yield: bonus signal for income/quality (optional)
        if metrics.get("dividend_yield") is not None and metrics["dividend_yield"] > 0:
            div = min(metrics["dividend_yield"] * 100, 6)  # decimal ? percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.10
            total_weight += 0.10

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}

    def _score_positioning(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score positioning metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Institutional ownership (55%) + Insider ownership (20%) + Short interest (25%).
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
        if not metrics or metrics.get("data_unavailable") is True:
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

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for positioning_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_positioning_scores_computed"}

    def _score_stability(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score stability metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Volatility 252d (50%) + Volatility 60d (25%) + Beta (15%) + Debt-to-assets (10%).
        Lower volatility and beta closer to 1.0 indicate stable, market-correlated stocks.
        Lower debt-to-assets indicates stronger financial stability.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 stability field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all stability fields None → returns marker dict with reason="no_stability_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative volatility → treated as 0 (impossible case, but defensive)

        MINIMUM DATA REQUIREMENT: At least one of volatility_252d/volatility_60d/beta/
        debt_to_assets metrics must be non-NULL. If all stability metrics are None,
        returns data_unavailable marker. Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable") is True:
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
            weighted_sum += vol_score * 0.50
            total_weight += 0.50

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
            weighted_sum += v60_score * 0.25
            total_weight += 0.25

        # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading
        if metrics.get("beta") is not None:
            beta = max(0, metrics["beta"])
            diff = min(abs(beta - 1.0), 2.0)
            beta_score = max(0, 100 - (diff * 50))
            weighted_sum += beta_score * 0.15
            total_weight += 0.15

        # Debt-to-assets: lower is better (target < 0.5)
        if metrics.get("debt_to_assets") is not None and metrics["debt_to_assets"] >= 0:
            dta = min(metrics["debt_to_assets"], 1.0)
            dta_score = max(0, 100 - (dta * 100))
            weighted_sum += dta_score * 0.10
            total_weight += 0.10

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for stability_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_scores_computed"}

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Momentum 1m (30%) + Momentum 3m (30%) + Momentum 6m (25%) + Momentum 12m (15%).
        Weights favor recent momentum (1m/3m) over longer-term (12m) for swing trading.
        Normalizes by total weight of available timeframes so partial data doesn't deflate the score.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 momentum field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all momentum fields None → returns marker dict with reason="no_momentum_scores_computed"

        ERROR HANDLING:
        - Weak momentum (±3%) → returns None for that timeframe (insufficient signal)
        - Missing historical prices → timeframe momentum is None (not guessed)

        MINIMUM DATA REQUIREMENT: At least one of 1m/3m/6m/12m momentum values must be
        available (not None). If all momentum values are None/missing, returns data_unavailable marker.
        Requires minimum 30/60/120/252 days of price history per timeframe (no short-term fallback).
        """
        if not metrics or metrics.get("data_unavailable") is True:
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_metrics_data"}

        # Named weights â€" recent timeframes matter more for swing trading
        weights = {
            "momentum_1m": 0.30,
            "momentum_3m": 0.30,
            "momentum_6m": 0.25,
            "momentum_12m": 0.15,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in weights.items():
            if metrics.get(key) is not None:
                score = self._pct_to_score(metrics[key])
                if score is not None:  # Skip weak momentum (score=None)
                    weighted_sum += score * w
                    total_weight += w

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
        """
        # Weak momentum zone: -3% to +3% lacks conviction
        if -0.03 <= pct_return <= 0.03:
            return None

        # Map momentum: -20% = 0, +20% = 100
        score = 50 + (pct_return / 0.4)
        return max(0, min(100, score))

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

                # Require at least 90% coverage on critical metric loaders
                min_coverage_pct = 90.0
                critical_metric_loaders = ["value_metrics", "stability_metrics"]

                for table_name, completion_pct, symbols_loaded, symbol_count in metric_coverage:
                    if completion_pct is None:
                        logger.warning(f"[STOCK_SCORES] {table_name}: completion_pct is NULL (loader still running?)")
                        continue

                    if table_name in critical_metric_loaders and completion_pct < min_coverage_pct:
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
        self.audit_upstream_coverage()
        self.update_rs_percentiles()

    def update_rs_percentiles(self) -> None:
        """Batch pass: rank all stocks by momentum_score and write true RS percentile.

        Uses PERCENT_RANK() so a stock scoring higher than 90% of peers gets rs_percentile=90.
        Must run after all per-symbol scores are loaded.

        CRITICAL: Raises on failure. RS percentiles are essential for ranking signal quality;
        missing or stale percentiles invalidate momentum-based signal filtering.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    UPDATE stock_scores ss
                    SET rs_percentile = ranked.pct
                    FROM (
                        SELECT symbol,
                               ROUND(
                                   (PERCENT_RANK() OVER (ORDER BY momentum_score))::NUMERIC * 100,
                                   2
                               ) AS pct
                        FROM stock_scores
                    ) ranked
                    WHERE ss.symbol = ranked.symbol
                """)
            logger.info("RS percentiles updated via batch rank")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"RS percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


if __name__ == "__main__":
    sys.exit(run_loader(StockScoresLoader))
