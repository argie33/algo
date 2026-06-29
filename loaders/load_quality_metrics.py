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
    """Quality metrics loader for real stocks only (not ETFs/bonds).

    Quality metrics require SEC financial data (balance sheet, income statement),
    which is only available for companies, not ETFs or bonds.
    """

    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute quality metrics from balance sheet and income statement.

        Returns record with data_unavailable=True if financial data not found
        (expected for micro-caps, OTC stocks, ADRs lacking SEC filings).
        Absence must be explicit (not silent None) for downstream systems.
        """
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

        metrics["data_unavailable"] = False
        metrics["updated_at"] = date.today().isoformat()

        return metrics

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No transformation needed."""
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(QualityMetricsLoader))
