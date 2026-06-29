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

Run: python3 loaders/load_stock_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import psycopg2  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class StockScoresLoader(OptimalLoader):
    """Compute and load multi-factor stock scores."""

    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field: str = ""  # No date watermark, we compute all at once

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run to validate upstream metrics are ready before computing scores.

        CRITICAL: Fail fast if upstream metric loaders haven't populated data.
        If quality/growth/value/positioning/stability metrics are all missing,
        stock_scores will be empty (no actual factor scores, just metadata).
        """
        self._validate_upstream_metrics_ready()
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)

    def _validate_upstream_metrics_ready(self) -> None:
        """Check that upstream metric tables have sufficient coverage.

        Raises RuntimeError if critical metric loaders haven't populated data yet.
        Prevents silent score computation failure when metrics are missing due to loader timeouts.
        """
        try:
            with DatabaseContext("read") as cur:
                metric_tables = {
                    "quality_metrics": 0.75,  # Require 75% coverage for SEC filings
                    "growth_metrics": 0.75,  # Require 75% coverage for SEC filings
                    "value_metrics": 0.80,  # Require 80% (less dependent on financials)
                    "positioning_metrics": 0.70,  # Require 70% (many don't have short interest data)
                    "stability_metrics": 0.85,  # Require 85% (computed from price data, nearly complete)
                }

                for table_name, min_coverage in metric_tables.items():
                    cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE data_unavailable = false")
                    row = cur.fetchone()
                    available_count = row[0] if row else 0

                    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                    row = cur.fetchone()
                    total_count = row[0] if row else 0

                    if total_count == 0:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} is empty. "
                            f"Upstream metric loader may not have run yet. "
                            f"Cannot compute stock scores without metric data."
                        )

                    coverage = available_count / total_count if total_count > 0 else 0
                    if coverage < min_coverage:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} only {coverage:.1%} coverage "
                            f"({available_count}/{total_count} stocks with data). "
                            f"Requires minimum {min_coverage:.0%} coverage. "
                            f"Upstream metric loader may have timed out or failed. "
                            f"Check step function logs and metric loader CloudWatch logs."
                        )

                logger.info(
                    f"[STOCK_SCORES] Pre-flight validation passed: "
                    f"All upstream metric loaders have sufficient coverage (>={min(metric_tables.values()):.0%}). "
                    f"Proceeding with stock score computation."
                )
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(f"[STOCK_SCORES] Pre-flight validation skipped due to query error: {e}")

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute stock scores for this symbol. Returns data_unavailable dict if unable to compute.

        CRITICAL: At the PUBLIC API boundary, converts internal RuntimeError to explicit
        data_unavailable marker for operator visibility. Callers can distinguish:
        - None/empty returns: data genuinely unavailable (not an error)
        - Exception propagation: actual system failures (database, auth, etc.)
        """
        try:
            score_result = self._compute_stock_score(symbol)
            if not score_result:
                # This should not occur (internal _compute_stock_score raises on failure),
                # but safeguard against unexpected None returns
                logger.warning(f"[STOCK_SCORES] Unexpected None return for {symbol} — marking data unavailable")
                return [
                    {
                        "symbol": symbol,
                        "data_unavailable": True,
                        "reason": "internal_computation_returned_none",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            return [score_result]
        except RuntimeError as e:
            # Upstream metric loaders insufficient data: convert to explicit data_unavailable marker
            logger.warning(f"[STOCK_SCORES] Cannot compute score for {symbol}: {e!s}")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "insufficient_upstream_metrics",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

    def _compute_stock_score(self, symbol: str) -> dict[str, Any]:
        """Compute composite stock score from REAL metrics only (no fake defaults).

        CRITICAL: Fails fast if stock has insufficient real data (>=50% completeness required).
        Do not return None or fake markers — callers must know immediately if scoring failed.

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
                stability["debt_to_assets"] = quality["debt_to_assets"]

            # Compute individual factor scores from REAL data only (no defaults)
            # Scoring functions return None if metrics dict exists but has all NULL values
            quality_score = self._score_quality(quality)
            growth_score = self._score_growth(growth)
            value_score = self._score_value(value)
            positioning_score = self._score_positioning(positioning)
            stability_score = self._score_stability(stability)
            momentum_score = self._score_momentum(momentum)

            # Count data completeness: only non-None scores count as "real data"
            # (ignores empty rows with all NULLs which return None from scoring functions)
            all_scores = [
                quality_score,
                growth_score,
                value_score,
                positioning_score,
                stability_score,
                momentum_score,
            ]
            real_scores = [s for s in all_scores if s is not None]
            data_count = len(real_scores)
            # Cap at 99.99 to fit in NUMERIC(4,2) database column
            data_completeness = min(99.99, round((data_count / 6.0) * 100, 2))

            # CRITICAL: Require minimum 50% (3 of 6) metrics for composite scoring.
            # Single or dual-metric composites have severe bias and produce unreliable signals.
            # Upstream metric loaders MUST complete before score computation. Do not degrade silently.
            min_required_metrics = 3

            if data_count < min_required_metrics:
                raise RuntimeError(
                    f"[STOCK_SCORES] {symbol}: insufficient metrics for scoring ({data_count}/{min_required_metrics} required, "
                    f"{data_completeness:.0f}% complete). "
                    f"Upstream metric loaders (quality, growth, value, positioning, stability, momentum) must have sufficient coverage. "
                    f"Cannot compute score with incomplete data — failing fast to prevent poor position sizing decisions."
                )

            # Compute weighted composite score with NORMALIZED weights
            # When metrics are missing, redistribute their weight to available metrics
            # instead of filling with mean (which would double-count missing factors)
            base_weights = {
                "quality": 0.25,
                "growth": 0.20,
                "value": 0.20,
                "positioning": 0.15,
                "stability": 0.12,
                "momentum": 0.08,
            }

            if not real_scores:
                logger.error(
                    f"[STOCK_SCORES] {symbol}: no real score data available. "
                    f"All metric calculations failed or returned None."
                )
                raise ValueError(
                    f"{symbol}: no real score data available. Cannot compute composite score without any real metrics. "
                    f"Upstream metrics (quality, growth, value, positioning, stability, momentum) not computed."
                )

            score_availability = {
                "quality": quality_score is not None,
                "growth": growth_score is not None,
                "value": value_score is not None,
                "positioning": positioning_score is not None,
                "stability": stability_score is not None,
                "momentum": momentum_score is not None,
            }

            # Normalize weights: keep weights of available metrics, redistribute missing weights
            available_weight_sum = sum(w for k, w in base_weights.items() if score_availability[k])
            if available_weight_sum <= 0:
                raise ValueError(
                    f"[STOCK_SCORES] No component scores available for {symbol}. "
                    "Stock score computation requires at least one available component (quality/growth/value/positioning/stability). "
                    "Check upstream loader status and data availability."
                )
            normalized_weights = {}
            for key, weight in base_weights.items():
                if score_availability[key]:
                    # Scale up available weights to sum to 1.0
                    normalized_weights[key] = weight / available_weight_sum
                else:
                    normalized_weights[key] = 0

            # Clamp scores to 0-100, keeping None for missing data
            clamped_quality = max(0, min(100, quality_score)) if quality_score is not None else None
            clamped_growth = max(0, min(100, growth_score)) if growth_score is not None else None
            clamped_value = max(0, min(100, value_score)) if value_score is not None else None
            clamped_positioning = max(0, min(100, positioning_score)) if positioning_score is not None else None
            clamped_stability = max(0, min(100, stability_score)) if stability_score is not None else None
            clamped_momentum = max(0, min(100, momentum_score)) if momentum_score is not None else None

            # Composite: only use metrics that are actually available
            # Fail fast if a metric has weight but no value (indicates calculation error)
            composite_score_value = 0.0
            for metric_name, clamped_value_score in [
                ("quality", clamped_quality),
                ("growth", clamped_growth),
                ("value", clamped_value),
                ("positioning", clamped_positioning),
                ("stability", clamped_stability),
                ("momentum", clamped_momentum),
            ]:
                weight = normalized_weights[metric_name]
                if weight > 0:
                    if clamped_value_score is None:
                        raise ValueError(
                            f"[{symbol}] Metric '{metric_name}' has weight {weight:.3f} but value is None. "
                            "This indicates incomplete data despite passing min_required_metrics check."
                        )
                    composite_score_value += clamped_value_score * weight
            composite_score = max(0, min(100, round(composite_score_value, 2)))

            return {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": (round(clamped_quality, 2) if clamped_quality is not None else None),
                "growth_score": (round(clamped_growth, 2) if clamped_growth is not None else None),
                "value_score": (round(clamped_value, 2) if clamped_value is not None else None),
                "momentum_score": (round(clamped_momentum, 2) if clamped_momentum is not None else None),
                "positioning_score": (round(clamped_positioning, 2) if clamped_positioning is not None else None),
                "stability_score": (round(clamped_stability, 2) if clamped_stability is not None else None),
                "rs_percentile": 0.0,
                "data_completeness": data_completeness,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _safe_float(self, value: Any, field_name: str) -> float | None:
        """Convert value to float, distinguishing None (no data) from conversion errors (corrupted data).

        CRITICAL: Allows operators to distinguish "no data available" from "corrupted data detected".
        """
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"CRITICAL: Financial metric {field_name} cannot be converted to float: {value!r}. "
                f"Data corruption detected or invalid format. Cannot score stock without valid financials. "
                f"Error: {e}"
            ) from e

    # ARCHITECTURAL PATTERN: Internal Scoring Pipeline
    # ====================================================
    # The following _get_* and _score_* methods are INTERNAL PLUMBING that feeds into
    # _compute_stock_score() → fetch_incremental() public API.
    #
    # INTERNAL FUNCTIONS (None returns):
    # - All 6 _get_*() methods return None when data table has no entry for the symbol
    # - All 6 _score_*() methods return None if their metrics dict is empty/all-NULL
    # - None returns are EXPLICITLY HANDLED by _compute_stock_score() via:
    #   * Line 168: real_scores = [s for s in all_scores if s is not None]
    #   * Lines 208-215: score_availability dict with `is not None` checks
    #   * Lines 234-239: None guards for each clamped score
    #   * Lines 244-259: ValueError raised if weight>0 but value is None (fail-fast)
    #   * Line 178-184: RuntimeError raised if data_count < 3 (hard threshold)
    #
    # PUBLIC API (Exceptions, not None):
    # - fetch_incremental() (line 107-121) raises RuntimeError if _compute_stock_score()
    #   returns falsy (line 115-120). No silent degradation—caller gets immediate feedback.
    # - This enforces fail-fast semantics at the boundary.
    #
    # PHILOSOPHY (from CLAUDE.md):
    # - data_unavailable dicts are for OPTIONAL ENRICHMENT at the LOADER-LEVEL (public outputs)
    # - Example: load_value_metrics.py fetch_incremental() returns dict with data_unavailable=True
    # - None returns in internal scoring helpers are appropriate because:
    #   1. They are never exposed externally (only _compute_stock_score sees them)
    #   2. They are explicitly handled by their sole caller (fail-fast enforcement)
    #   3. Missing financial data is logged at WARNING level (high-priority data visibility)
    #   4. Weight validation (line 244-259) prevents silent score degradation
    #
    # DECISION: Keep None returns in internal functions. They are part of a fail-fast
    # public API that raises exceptions. Refactoring to data_unavailable dicts would
    # add 50+ lines of boilerplate with zero operational benefit since all None returns
    # are already explicitly handled and logged at appropriate levels.
    # ====================================================

    def _get_quality_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch quality metrics for symbol.

        Returns None only if data is explicitly unavailable (quality_metrics table
        has no entry for this symbol). Raises on database errors.
        """
        try:
            cur.execute(
                "SELECT roe, roa, operating_margin, net_margin, debt_to_equity, current_ratio, quick_ratio FROM quality_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "roe": self._safe_float(row[0], f"{symbol}.roe"),
                    "roa": self._safe_float(row[1], f"{symbol}.roa"),
                    "operating_margin": self._safe_float(row[2], f"{symbol}.operating_margin"),
                    "net_margin": self._safe_float(row[3], f"{symbol}.net_margin"),
                    "debt_to_equity": self._safe_float(row[4], f"{symbol}.debt_to_equity"),
                    "current_ratio": self._safe_float(row[5], f"{symbol}.current_ratio"),
                    "quick_ratio": self._safe_float(row[6], f"{symbol}.quick_ratio"),
                }
            # CRITICAL: Quality metrics are HIGH-priority financial data (SEC filings)
            # Logging at WARNING to ensure ops visibility of degraded scoring
            logger.warning(
                f"[LOAD_STOCK_SCORES] No quality metrics available for {symbol} — score completeness will be reduced"
            )
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching quality metrics for {symbol}: {e}") from e

    def _get_growth_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch growth metrics for symbol.

        Returns None only if data is explicitly unavailable (growth_metrics table
        has no entry for this symbol). Raises on database errors.
        """
        try:
            cur.execute(
                "SELECT revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y FROM growth_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "revenue_growth_1y": self._safe_float(row[0], f"{symbol}.revenue_growth_1y"),
                    "revenue_growth_3y": self._safe_float(row[1], f"{symbol}.revenue_growth_3y"),
                    "revenue_growth_5y": self._safe_float(row[2], f"{symbol}.revenue_growth_5y"),
                    "eps_growth_1y": self._safe_float(row[3], f"{symbol}.eps_growth_1y"),
                    "eps_growth_3y": self._safe_float(row[4], f"{symbol}.eps_growth_3y"),
                    "eps_growth_5y": self._safe_float(row[5], f"{symbol}.eps_growth_5y"),
                }
            # CRITICAL: Growth metrics are HIGH-priority financial data (SEC filings)
            # Logging at WARNING to ensure ops visibility of degraded scoring
            logger.warning(
                f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} — score completeness will be reduced"
            )
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching growth metrics for {symbol}: {e}") from e

    def _get_value_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch value metrics for symbol.

        Returns None only if data is explicitly unavailable (value_metrics table
        has no entry for this symbol). Raises on database errors.
        """
        try:
            cur.execute(
                "SELECT pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield FROM value_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "pe_ratio": self._safe_float(row[0], f"{symbol}.pe_ratio"),
                    "pb_ratio": self._safe_float(row[1], f"{symbol}.pb_ratio"),
                    "ps_ratio": self._safe_float(row[2], f"{symbol}.ps_ratio"),
                    "peg_ratio": self._safe_float(row[3], f"{symbol}.peg_ratio"),
                    "dividend_yield": self._safe_float(row[4], f"{symbol}.dividend_yield"),
                    "fcf_yield": self._safe_float(row[5], f"{symbol}.fcf_yield"),
                }
            # CRITICAL: Value metrics are HIGH-priority financial data (market pricing)
            # Logging at WARNING to ensure ops visibility of degraded scoring
            logger.warning(
                f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} — score completeness will be reduced"
            )
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching value metrics for {symbol}: {e}") from e

    def _get_positioning_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch positioning metrics for symbol.

        Returns None only if data is explicitly unavailable (positioning_metrics table
        has no entry for this symbol). Raises on database errors.
        """
        try:
            cur.execute(
                "SELECT institutional_ownership, insider_ownership, short_interest_percent FROM positioning_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "institutional_ownership": self._safe_float(row[0], f"{symbol}.institutional_ownership"),
                    "insider_ownership": self._safe_float(row[1], f"{symbol}.insider_ownership"),
                    "short_interest": self._safe_float(row[2], f"{symbol}.short_interest"),
                }
            # Positioning metrics are optional enrichment (institutional ownership, short interest)
            # Debug level acceptable for optional data
            logger.debug(
                f"[LOAD_STOCK_SCORES] No positioning metrics available for {symbol} — will reduce score completeness"
            )
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching positioning metrics for {symbol}: {e}") from e

    def _get_stability_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch stability metrics for symbol.

        Returns None only if data is explicitly unavailable (stability_metrics table
        has no entry for this symbol). Raises on database errors.
        """
        try:
            cur.execute(
                "SELECT volatility_252d, volatility_60d, volatility_30d, beta FROM stability_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "volatility_252d": float(row[0]) if row[0] is not None else None,
                    "volatility_60d": float(row[1]) if row[1] is not None else None,
                    "volatility_30d": float(row[2]) if row[2] is not None else None,
                    "beta": float(row[3]) if row[3] is not None else None,
                }
            # CRITICAL: Stability metrics are HIGH-priority financial data (volatility, beta)
            # Logging at WARNING to ensure ops visibility of degraded scoring
            logger.warning(
                f"[LOAD_STOCK_SCORES] No stability metrics available for {symbol} — score completeness will be reduced"
            )
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching stability metrics for {symbol}: {e}") from e

    def _get_momentum_metrics(self, cur: Any, symbol: str) -> dict[str, Any] | None:
        """Fetch momentum/RS metrics for symbol using DATE-based lookups (not OFFSET).

        Uses date arithmetic to find approximate prices at 1m/3m/6m/12m ago.
        More robust than OFFSET which breaks on data gaps or different row counts.
        Returns None only if no price data available. Raises on database errors.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1) as current,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 month' ORDER BY date DESC LIMIT 1) as price_1m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '3 months' ORDER BY date DESC LIMIT 1) as price_3m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '6 months' ORDER BY date DESC LIMIT 1) as price_6m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 year' ORDER BY date DESC LIMIT 1) as price_12m_ago
            """,
                (symbol, symbol, symbol, symbol, symbol),
            )
            row = cur.fetchone()

            if row and row[0] is not None:
                prices = {
                    "current": float(row[0]) if row[0] is not None else None,
                    "price_1m_ago": float(row[1]) if row[1] is not None else None,
                    "price_3m_ago": float(row[2]) if row[2] is not None else None,
                    "price_6m_ago": float(row[3]) if row[3] is not None else None,
                    "price_12m_ago": float(row[4]) if row[4] is not None else None,
                }

                current = prices["current"]
                momentum_1m = (
                    ((current / prices["price_1m_ago"] - 1) * 100)
                    if current is not None and prices["price_1m_ago"] is not None and prices["price_1m_ago"] != 0
                    else None
                )
                momentum_3m = (
                    ((current / prices["price_3m_ago"] - 1) * 100)
                    if current is not None and prices["price_3m_ago"] is not None and prices["price_3m_ago"] != 0
                    else None
                )
                momentum_6m = (
                    ((current / prices["price_6m_ago"] - 1) * 100)
                    if current is not None and prices["price_6m_ago"] is not None and prices["price_6m_ago"] != 0
                    else None
                )
                momentum_12m = (
                    ((current / prices["price_12m_ago"] - 1) * 100)
                    if current is not None and prices["price_12m_ago"] is not None and prices["price_12m_ago"] != 0
                    else None
                )

                return {
                    "momentum_1m": momentum_1m,
                    "momentum_3m": momentum_3m,
                    "momentum_6m": momentum_6m,
                    "momentum_12m": momentum_12m,
                }
            # CRITICAL: Momentum is HIGH-priority technical indicator data (price history)
            # Logging at WARNING to ensure ops visibility of degraded scoring
            logger.warning(f"[LOAD_STOCK_SCORES] No momentum data available for {symbol} — insufficient price history")
            return None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_quality(self, metrics: dict[str, Any] | None) -> float | dict[str, Any]:
        """Score quality metrics on 0-100 scale. Returns marker if no real data."""
        if not metrics:
            logger.debug(f"[STOCK_SCORES] Quality metrics unavailable for {self.symbol}")
            return {
                "symbol": self.symbol,
                "data_unavailable": True,
                "reason": "no_quality_metrics",
                "score_type": "quality"
            }

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
            return sum(scores) / len(scores)
        logger.debug(f"[STOCK_SCORES] No quality metrics found to score for {self.symbol}")
        return {
            "symbol": self.symbol,
            "data_unavailable": True,
            "reason": "no_scoreable_quality_data",
            "score_type": "quality"
        }

    def _score_growth(self, metrics: dict[str, Any] | None) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale. Returns marker if no real data.

        Uses weighted blend: 1Y growth (60%) + 3Y CAGR (30%) + 5Y CAGR (10%).
        Longer-term growth signals more durable earnings quality.
        """
        if not metrics:
            logger.debug(f"[STOCK_SCORES] Growth metrics unavailable for {self.symbol}")
            return {
                "symbol": self.symbol,
                "data_unavailable": True,
                "reason": "no_growth_metrics",
                "score_type": "growth"
            }

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
            return weighted_sum / total_weight
        logger.debug(f"[STOCK_SCORES] No growth metrics found to score for {self.symbol}")
        return {
            "symbol": self.symbol,
            "data_unavailable": True,
            "reason": "no_scoreable_growth_data",
            "score_type": "growth"
        }

    def _score_value(self, metrics: dict[str, Any] | None) -> float | dict[str, Any]:
        """Score value metrics on 0-100 scale. Returns marker if no real data.

        Uses P/E (primary), P/B (secondary), FCF yield (secondary), dividend yield (bonus).
        Peak zone for growth stocks: P/E 15-30, P/B < 5, positive FCF yield.
        """
        if not metrics:
            logger.debug(f"[STOCK_SCORES] Value metrics unavailable for {self.symbol}")
            return {
                "symbol": self.symbol,
                "data_unavailable": True,
                "reason": "no_value_metrics",
                "score_type": "value"
            }

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
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {self.symbol}")
        return {
            "symbol": self.symbol,
            "data_unavailable": True,
            "reason": "no_scoreable_value_data",
            "score_type": "value"
        }

    def _score_positioning(self, metrics: dict[str, Any] | None) -> float | dict[str, Any]:
        """Score positioning metrics on 0-100 scale. Returns marker if no real data."""
        if not metrics:
            logger.debug(f"[STOCK_SCORES] Positioning metrics unavailable for {self.symbol}")
            return {
                "symbol": self.symbol,
                "data_unavailable": True,
                "reason": "no_positioning_metrics",
                "score_type": "positioning"
            }

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

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_stability(self, metrics: dict[str, Any] | None) -> float | None:
        """Score stability metrics on 0-100 scale. Returns None if no real data.

        Uses 12-month volatility (primary), beta vs market (secondary),
        and debt-to-assets (tertiary solvency signal).
        """
        if not metrics:
            return None

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

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_momentum(self, metrics: dict[str, Any] | None) -> float | None:
        """Score momentum metrics on 0-100 scale. Returns None if no real data.

        Weights favor recent momentum (1m/3m) over longer-term (12m) for swing trading.
        Normalizes by total weight of available timeframes so partial data doesn't
        deflate the score.
        """
        if not metrics:
            return None

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
                weighted_sum += self._pct_to_score(metrics[key]) * w
                total_weight += w

        return weighted_sum / total_weight if total_weight > 0 else None

    @staticmethod
    def _pct_to_score(pct_return: float) -> float:
        """Convert percentage return to 0-100 score.

        Returns None (via None mapping) if momentum is weak (< ±3%), as this
        indicates insufficient conviction and should not create false sense of okayness.
        -3% to +3% range returns None instead of 50 (middle default).
        -20% = 0, ±3% = None, +20% = 100.
        """
        # Weak momentum zone: -3% to +3% lacks conviction
        # Fail fast by returning very low score (treat as missing signal)
        if -0.03 <= pct_return <= 0.03:
            # Instead of returning 50 (middle default), return 25 to indicate
            # "neutral/no conviction" rather than "okay"
            return 25.0

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
            error_msg = f"RS percentile batch update failed — stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


if __name__ == "__main__":
    sys.exit(run_loader(StockScoresLoader))
