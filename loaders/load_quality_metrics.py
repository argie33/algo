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
from utils.loaders import fetch_one
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class QualityMetricsLoader(OptimalLoader):
    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute quality metrics from balance sheet and income statement."""
        income_row = fetch_one(
            """
            SELECT revenue, operating_income, net_income
            FROM annual_income_statement
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 1
        """,
            (symbol,),
        )

        balance_row = fetch_one(
            """
            SELECT total_assets, stockholders_equity, current_assets,
                   total_liabilities, current_liabilities, inventory
            FROM annual_balance_sheet
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 1
        """,
            (symbol,),
        )

        # Require at least income statement; balance sheet is optional
        if not income_row:
            raise RuntimeError(
                f"[QUALITY_METRICS] No income statement data for {symbol}. "
                "Cannot compute quality metrics without revenue and earnings data."
            )

        metrics = self._compute_metrics(symbol, income_row, balance_row)
        if not metrics:
            raise RuntimeError(
                f"[QUALITY_METRICS] Failed to compute quality metrics for {symbol}. "
                "Invalid or insufficient financial data."
            )
        return [metrics]

    @staticmethod
    def _compute_metrics(
        symbol: str, income: tuple[Any, Any, Any], balance: tuple[Any, Any, Any, Any, Any, Any] | None
    ) -> dict[str, Any]:
        """Compute quality metrics from financial data. Balance sheet is optional."""
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

        # Operating Margin: Operating Income / Revenue
        if revenue and revenue > 0 and operating_income is not None:
            metrics["operating_margin"] = float(round((operating_income / revenue) * 100, 2))
        else:
            metrics["operating_margin"] = None

        # Net Margin: Net Income / Revenue
        if revenue and revenue > 0 and net_income is not None:
            metrics["net_margin"] = float(round((net_income / revenue) * 100, 2))
        else:
            metrics["net_margin"] = None

        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            metrics["roe"] = float(round((net_income / stockholders_equity) * 100, 2))
        else:
            metrics["roe"] = None

        if total_assets and total_assets > 0 and net_income is not None:
            metrics["roa"] = float(round((net_income / total_assets) * 100, 2))
        else:
            metrics["roa"] = None

        # Debt/Equity: Total Liabilities / Equity
        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            metrics["debt_to_equity"] = float(round(total_liabilities / stockholders_equity, 2))
        else:
            metrics["debt_to_equity"] = None

        # Current Ratio: Current Assets / Current Liabilities
        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            metrics["current_ratio"] = float(round(current_assets / current_liabilities, 2))
        else:
            metrics["current_ratio"] = None

        # Quick Ratio: (Current Assets - Inventory) / Current Liabilities
        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            if inventory and inventory > 0:
                quick_assets = float(current_assets) - float(inventory)
            else:
                quick_assets = float(current_assets)  # No inventory data, use all current assets
            metrics["quick_ratio"] = float(round(quick_assets / float(current_liabilities), 2))
        else:
            metrics["quick_ratio"] = None

        metrics["interest_coverage"] = None

        # Quality Score: Composite (0-100) based on profitability and financial health
        score = 50.0  # Neutral baseline

        if metrics["operating_margin"] is not None:
            # Higher is better (up to 20% = +25 points)
            om_score = min(25, metrics["operating_margin"] / 0.8)
            score += om_score

        if metrics["net_margin"] is not None:
            # Higher is better (up to 10% = +25 points)
            nm_score = min(25, metrics["net_margin"] / 0.4)
            score += nm_score

        if metrics["roe"] is not None and metrics["roe"] > 0:
            # Higher ROE is better (up to 15% = +25 points)
            roe_score = min(25, metrics["roe"] / 0.6)
            score += roe_score

        score = max(0, min(100, score))
        metrics["quality_score"] = float(round(score, 2))

        # Debt/Assets: Total Liabilities / Total Assets (solvency metric)
        if total_assets and total_assets > 0 and total_liabilities is not None:
            metrics["debt_to_assets"] = float(round(total_liabilities / total_assets, 2))
        else:
            metrics["debt_to_assets"] = None

        return metrics

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No transformation needed."""
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(QualityMetricsLoader))
