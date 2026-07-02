#!/usr/bin/env python3
"""
Growth Metrics Loader - Computes multi-year growth metrics from annual financials.

Metrics: Revenue Growth (1Y, 3Y, 5Y), EPS Growth (1Y, 3Y, 5Y), Growth Score (0-100).
Requires: annual_income_statement populated.
"""

import logging
import sys
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.loaders import execute_query
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class GrowthMetricsLoader(OptimalLoader):
    """Growth metrics loader for real stocks only (not ETFs/bonds).

    Growth metrics are computed from annual income statement data, which is only available
    for companies that file with the SEC. ETFs and bonds don't have financial statements.

    CRITICAL FIX 2026-07-01: Auto-heals missing schema columns on first run.
    Similar to quality_metrics, growth_metrics tables may be missing unavailable_reason columns
    in incomplete deployments. Auto-creates them to prevent data loss.
    """

    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    # Required columns with data types (auto-created if missing)
    REQUIRED_COLUMNS = {
        "revenue_growth_1y_unavailable_reason": "VARCHAR(255)",
        "revenue_growth_3y_unavailable_reason": "VARCHAR(255)",
        "revenue_growth_5y_unavailable_reason": "VARCHAR(255)",
        "eps_growth_1y_unavailable_reason": "VARCHAR(255)",
        "eps_growth_3y_unavailable_reason": "VARCHAR(255)",
        "eps_growth_5y_unavailable_reason": "VARCHAR(255)",
    }

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        # Ensure schema is healed before loading
        self._ensure_schema_ready()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute multi-year growth metrics from annual income statement.

        Returns record with data_unavailable marker if financial data unavailable (normal for small caps, new IPOs).
        Growth metrics are optional enrichment; their absence does not prevent trading.
        But unavailability should be explicit (data_unavailable flag), not silent skips.
        """
        from decimal import Decimal

        try:
            # Fetch up to 10 years of financials to calculate 1Y, 3Y, 5Y growth
            rows = execute_query(
                """
                SELECT fiscal_year, revenue, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 10
            """,
                (symbol,),
            )

            # Convert NaN Decimal values to None (SEC data quality issue)
            if rows:
                rows = [
                    (
                        fy,
                        None if isinstance(rev, Decimal) and rev.is_nan() else rev,
                        None if isinstance(eps, Decimal) and eps.is_nan() else eps,
                    )
                    for fy, rev, eps in rows
                ]

            if not rows or len(rows) < 1:
                logger.info(
                    f"[GROWTH_METRICS] No annual income statement data for {symbol} (new stock/no financials yet)"
                )
                return [
                    {
                        "symbol": symbol,
                        "revenue_growth_1y": None,
                        "revenue_growth_3y": None,
                        "revenue_growth_5y": None,
                        "eps_growth_1y": None,
                        "eps_growth_3y": None,
                        "eps_growth_5y": None,
                        "data_unavailable": True,
                        "reason": "No annual income statement data available",
                        "updated_at": date.today(),
                    }
                ]

            # Sort by year ascending for easier calculation
            rows_list = list(reversed(rows))

            latest = rows_list[-1]  # Most recent year
            metrics = self._compute_metrics(symbol, latest, rows_list)

            if not metrics:
                logger.warning(f"[GROWTH_METRICS] Failed to compute metrics for {symbol} (calculation error)")
                return [
                    {
                        "symbol": symbol,
                        "revenue_growth_1y": None,
                        "revenue_growth_3y": None,
                        "revenue_growth_5y": None,
                        "eps_growth_1y": None,
                        "eps_growth_3y": None,
                        "eps_growth_5y": None,
                        "data_unavailable": True,
                        "reason": "Metrics computation failed",
                        "updated_at": date.today(),
                    }
                ]
            return [metrics]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[GROWTH_METRICS] Database error for {symbol}: {e}")
            raise RuntimeError(
                f"[GROWTH_METRICS] Database error fetching financials for {symbol}: {e}. "
                f"Cannot compute growth metrics without access to financial data."
            ) from e

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple[Any, Any, Any], all_years: list[Any]) -> dict[str, Any] | None:
        """Compute multi-year growth metrics.

        Returns dict with explicit unavailability reasons for each metric when data insufficient.
        Each metric has a corresponding _unavailable_reason field when None.

        CRITICAL FIX: Handle REITs and companies with NULL revenue/EPS values gracefully.
        Many REITs and special entities in SEC filings have missing or NULL financial data,
        particularly for concepts like "Revenues" or "EarningsPerShareBasic".
        Return data_unavailable marker instead of raising exception.
        """
        if not latest or len(latest) != 3:
            raise ValueError(
                f"[GROWTH_METRICS] Malformed latest data for {symbol}: expected (year, revenue, eps), got {latest}"
            )
        if not all_years or not isinstance(all_years, list):
            raise ValueError(f"[GROWTH_METRICS] Malformed all_years for {symbol}: expected list, got {type(all_years)}")

        _latest_year, latest_rev, latest_eps = latest

        # CHANGE: Don't bail out if revenue is NULL. REITs and special entities often have NULL revenue
        # but DO have EPS data. Let the loop below handle both revenue AND eps growth separately.
        # If both are NULL, the check at line 194 will mark as unavailable.

        if latest_rev is None or (isinstance(latest_rev, (int, float)) and float(latest_rev) == 0):
            logger.info(
                f"[GROWTH_METRICS] {symbol}: Revenue is NULL/zero but will attempt EPS-only growth. "
                f"Company may be REIT, investment trust, or special entity."
            )

        metrics: dict[str, Any] = {"symbol": symbol}

        for lookback in [1, 3, 5]:
            idx = -(lookback + 1)
            if len(all_years) > lookback and all_years[idx] and latest_rev:
                _prev_year, prev_rev, _prev_eps = all_years[idx]
                try:
                    # Allow revenue growth even with negative revenue. Only skip if:
                    # - prev_rev is None (missing data), or
                    # - prev_rev = 0 (would divide by zero)
                    # Negative revenue is real data that should be included.
                    if prev_rev is not None and float(prev_rev) != 0:
                        latest_rev_f = float(latest_rev)
                        prev_rev_f = float(prev_rev)
                        rev_growth = (((latest_rev_f / prev_rev_f) ** (1.0 / lookback)) - 1) * 100
                        metrics[f"revenue_growth_{lookback}y"] = float(round(rev_growth, 2))
                        metrics[f"revenue_growth_{lookback}y_unavailable_reason"] = None
                    else:
                        metrics[f"revenue_growth_{lookback}y"] = None
                        metrics[f"revenue_growth_{lookback}y_unavailable_reason"] = "insufficient_revenue_data"
                except (TypeError, ValueError):
                    metrics[f"revenue_growth_{lookback}y"] = None
                    metrics[f"revenue_growth_{lookback}y_unavailable_reason"] = "revenue_calculation_error"
            else:
                metrics[f"revenue_growth_{lookback}y"] = None
                metrics[f"revenue_growth_{lookback}y_unavailable_reason"] = f"insufficient_history_{lookback}y"

            if len(all_years) > lookback and all_years[idx] and latest_eps:
                _prev_year, _prev_rev, prev_eps = all_years[idx]
                try:
                    # Allow EPS growth even with negative earnings. Only skip if:
                    # - prev_eps is None (missing data), or
                    # - prev_eps = 0 (would divide by zero)
                    # Negative earnings are real data that should be included.
                    if prev_eps is not None and float(prev_eps) != 0:
                        latest_eps_f = float(latest_eps)
                        prev_eps_f = float(prev_eps)
                        eps_growth = (((latest_eps_f / prev_eps_f) ** (1.0 / lookback)) - 1) * 100
                        metrics[f"eps_growth_{lookback}y"] = float(round(eps_growth, 2))
                        metrics[f"eps_growth_{lookback}y_unavailable_reason"] = None
                    else:
                        metrics[f"eps_growth_{lookback}y"] = None
                        metrics[f"eps_growth_{lookback}y_unavailable_reason"] = "insufficient_eps_data"
                except (TypeError, ValueError):
                    metrics[f"eps_growth_{lookback}y"] = None
                    metrics[f"eps_growth_{lookback}y_unavailable_reason"] = "eps_calculation_error"
            else:
                metrics[f"eps_growth_{lookback}y"] = None
                metrics[f"eps_growth_{lookback}y_unavailable_reason"] = f"insufficient_history_{lookback}y"

        # Check if we actually have any real data (not all NULL)
        # Explicitly check that computed growth metrics exist and are not None
        has_revenue_growth = any(metrics.get(f"revenue_growth_{y}y") is not None for y in [1, 3, 5])
        has_eps_growth = any(metrics.get(f"eps_growth_{y}y") is not None for y in [1, 3, 5])

        if has_revenue_growth or has_eps_growth:
            metrics["data_unavailable"] = False
        else:
            # All growth metrics are NULL - mark as unavailable
            metrics["data_unavailable"] = True
            metrics["reason"] = "Insufficient historical data to compute growth rates"

        metrics["updated_at"] = date.today()

        return metrics

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No transformation needed; metrics already computed."""
        return rows

    def _ensure_schema_ready(self) -> None:
        """Ensure all required columns exist, auto-creating if needed.

        CRITICAL FIX 2026-07-01: Auto-heals incomplete migration 0044.
        Creates missing unavailable_reason columns on first loader run to prevent
        silent data loss when BulkInsertManager encounters columns not in DB schema.
        """
        from utils.db.context import DatabaseContext
        from utils.schema_healer import ensure_columns_exist

        try:
            with DatabaseContext("write") as cur:
                _all_exist, created = ensure_columns_exist(cur, self.table_name, self.REQUIRED_COLUMNS)
                if created:
                    logger.warning(
                        f"[GROWTH_METRICS] Auto-healed {len(created)} missing columns: {created}. "
                        f"Migration 0044 was incomplete in this environment."
                    )
        except Exception as e:
            logger.error(f"[GROWTH_METRICS] Schema healing failed: {e}")
            raise RuntimeError(f"[GROWTH_METRICS] Cannot verify schema is ready: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(GrowthMetricsLoader))
