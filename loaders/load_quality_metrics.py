#!/usr/bin/env python3
"""Quality Metrics Loader - Optimal Pattern.

Computes fundamental quality metrics from annual financials:
- Operating Margin: Operating Income / Revenue
- Net Margin: Net Income / Revenue
- ROE: Return on Equity
- ROA: Return on Assets
- Debt/Equity: Financial leverage
- Quality Score: Composite (0-100)

Requires: annual_income_statement, annual_balance_sheet populated

Run:
    python3 load_quality_metrics.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from loaders.sec_financials_loader import SecFinancialsLoader

logger = logging.getLogger(__name__)


class QualityMetricsLoader(SecFinancialsLoader):
    """Quality metrics loader for real stocks only (not ETFs/bonds).

    Quality metrics require SEC financial data (balance sheet, income statement),
    which is only available for companies, not ETFs or bonds.

    CRITICAL FIX 2026-07-01: Auto-heals missing schema columns on first run.
    Migration 0044 was incomplete, leaving 11 required columns missing in AWS RDS.
    This loader now creates missing columns automatically, preventing silent data loss.

    Inherits from SecFinancialsLoader to eliminate 200+ lines of duplication with
    growth_metrics.py (shared NaN handling, balance sheet/income statement fetching,
    schema healing, and data_unavailable patterns).
    """

    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    # Required columns with data types (auto-created if missing)
    REQUIRED_COLUMNS = {
        "quality_score": "DECIMAL(5, 2)",
        "debt_to_assets": "DECIMAL(8, 4)",
        "operating_margin_unavailable_reason": "VARCHAR(255)",
        "net_margin_unavailable_reason": "VARCHAR(255)",
        "roe_unavailable_reason": "VARCHAR(255)",
        "roa_unavailable_reason": "VARCHAR(255)",
        "debt_to_equity_unavailable_reason": "VARCHAR(255)",
        "current_ratio_unavailable_reason": "VARCHAR(255)",
        "quick_ratio_unavailable_reason": "VARCHAR(255)",
        "interest_coverage_unavailable_reason": "VARCHAR(255)",
        "debt_to_assets_unavailable_reason": "VARCHAR(255)",
    }

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute quality metrics from balance sheet and income statement.

        Returns record with data_unavailable=True if financial data not found
        (expected for micro-caps, OTC stocks, ADRs lacking SEC filings).
        Absence must be explicit (not silent None) for downstream systems.

        Uses SecFinancialsLoader helper methods for NaN-safe financial data fetching.
        """
        # Use base class helpers to fetch financials with NaN cleaning
        income_row = self._fetch_annual_income_statement(symbol)
        balance_row = self._fetch_annual_balance_sheet(symbol)

        # If no income statement, return explicit data_unavailable record
        # (many stocks lack SEC filings: micro-caps, OTC, ADRs, new IPOs - about 55% of universe)
        if not income_row:
            logger.info(
                f"[QUALITY_METRICS] [SEC_DATA_UNAVAILABLE] {symbol}: no SEC filing data (micro-cap, OTC, ADR, or new IPO)"
            )
            return [
                {
                    "symbol": symbol,
                    "roe": None,
                    "roa": None,
                    "operating_margin": None,
                    "net_margin": None,
                    "debt_to_equity": None,
                    "current_ratio": None,
                    "quick_ratio": None,
                    "data_unavailable": True,
                    "reason": "No SEC filing data available (micro-cap, OTC, ADR, or new IPO)",
                    "updated_at": date.today().isoformat(),
                }
            ]

        metrics = self._compute_metrics(symbol, income_row, balance_row)
        if not metrics:
            logger.warning(
                f"[QUALITY_METRICS] Failed to compute metrics for {symbol} (check logs for calculation errors)"
            )
            return [
                {
                    "symbol": symbol,
                    "roe": None,
                    "roa": None,
                    "operating_margin": None,
                    "net_margin": None,
                    "debt_to_equity": None,
                    "current_ratio": None,
                    "quick_ratio": None,
                    "data_unavailable": True,
                    "reason": "Metrics computation failed (insufficient or invalid financial data)",
                    "updated_at": date.today().isoformat(),
                }
            ]
        return [metrics]

    @staticmethod
    def _compute_metrics(
        symbol: str, income: tuple[Any, Any, Any], balance: tuple[Any, Any, Any, Any, Any, Any] | None
    ) -> dict[str, Any]:
        """Compute quality metrics from financial data. Balance sheet is optional.

        Returns dict with explicit reason strings when individual metrics unavailable:
        - operating_margin_unavailable_reason, net_margin_unavailable_reason, etc.
        Callers check these strings to understand why each metric is None.
        """
        revenue, operating_income, net_income = income
        if balance:
            (
                total_assets,
                stockholders_equity,
                current_assets,
                total_liabilities,
                current_liabilities,
                inventory,
            ) = balance
        else:
            total_assets = stockholders_equity = current_assets = total_liabilities = current_liabilities = (
                inventory
            ) = None

        metrics: dict[str, Any] = {"symbol": symbol}

        if revenue and revenue > 0 and operating_income is not None:
            metrics["operating_margin"] = float(round((operating_income / revenue) * 100, 2))
            metrics["operating_margin_unavailable_reason"] = None
        else:
            metrics["operating_margin"] = None
            metrics["operating_margin_unavailable_reason"] = (
                "insufficient_income_statement_data" if not revenue or revenue <= 0 else "missing_operating_income"
            )

        if revenue and revenue > 0 and net_income is not None:
            metrics["net_margin"] = float(round((net_income / revenue) * 100, 2))
            metrics["net_margin_unavailable_reason"] = None
        else:
            metrics["net_margin"] = None
            metrics["net_margin_unavailable_reason"] = (
                "insufficient_income_statement_data" if not revenue or revenue <= 0 else "missing_net_income"
            )

        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            metrics["roe"] = float(round((net_income / stockholders_equity) * 100, 2))
            metrics["roe_unavailable_reason"] = None
        else:
            metrics["roe"] = None
            metrics["roe_unavailable_reason"] = (
                "missing_equity_data" if not stockholders_equity or stockholders_equity <= 0 else "missing_net_income"
            )

        if total_assets and total_assets > 0 and net_income is not None:
            metrics["roa"] = float(round((net_income / total_assets) * 100, 2))
            metrics["roa_unavailable_reason"] = None
        else:
            metrics["roa"] = None
            metrics["roa_unavailable_reason"] = (
                "missing_asset_data" if not total_assets or total_assets <= 0 else "missing_net_income"
            )

        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            metrics["debt_to_equity"] = float(round(total_liabilities / stockholders_equity, 2))
            metrics["debt_to_equity_unavailable_reason"] = None
        else:
            metrics["debt_to_equity"] = None
            metrics["debt_to_equity_unavailable_reason"] = "missing_balance_sheet_data"

        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            metrics["current_ratio"] = float(round(current_assets / current_liabilities, 2))
            metrics["current_ratio_unavailable_reason"] = None
        else:
            metrics["current_ratio"] = None
            metrics["current_ratio_unavailable_reason"] = "missing_balance_sheet_data"

        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            if inventory and inventory > 0:
                quick_assets = float(current_assets) - float(inventory)
            else:
                quick_assets = float(current_assets)
            metrics["quick_ratio"] = float(round(quick_assets / float(current_liabilities), 2))
            metrics["quick_ratio_unavailable_reason"] = None
        else:
            metrics["quick_ratio"] = None
            metrics["quick_ratio_unavailable_reason"] = "missing_balance_sheet_data"

        metrics["interest_coverage"] = None
        metrics["interest_coverage_unavailable_reason"] = "not_implemented"

        if total_assets and total_assets > 0 and total_liabilities is not None:
            metrics["debt_to_assets"] = float(round(total_liabilities / total_assets, 2))
            metrics["debt_to_assets_unavailable_reason"] = None
        else:
            metrics["debt_to_assets"] = None
            metrics["debt_to_assets_unavailable_reason"] = "missing_balance_sheet_data"

        # Check if ANY metrics were actually computed (not all NULL)
        computed_metrics = [
            metrics.get(k)
            for k in ["operating_margin", "net_margin", "roe", "roa", "debt_to_equity", "current_ratio", "quick_ratio"]
        ]
        has_real_data = any(m is not None for m in computed_metrics)

        # Fail-fast: only compute quality_score if we have real data. Governance principle: no silent defaults.
        if not has_real_data:
            metrics["quality_score"] = None
            metrics["data_unavailable"] = True
            metrics["reason"] = "Metrics computation failed (insufficient or invalid financial data)"
        else:
            score = 50.0
            if metrics["operating_margin"] is not None:
                om_score = min(25, metrics["operating_margin"] / 0.8)
                score += om_score
            if metrics["net_margin"] is not None:
                nm_score = min(25, metrics["net_margin"] / 0.4)
                score += nm_score
            if metrics["roe"] is not None and metrics["roe"] > 0:
                roe_score = min(25, metrics["roe"] / 0.6)
                score += roe_score

            score = max(0, min(100, score))
            metrics["quality_score"] = float(round(score, 2))
            metrics["data_unavailable"] = False
        metrics["updated_at"] = date.today().isoformat()

        return metrics

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No transformation needed."""
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(QualityMetricsLoader))
