#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Quality Metrics Loader - Optimal Pattern (Refactored)

Computes fundamental quality metrics from annual financials:
- Operating Margin: Operating Income / Revenue
- Net Margin: Net Income / Revenue
- ROE: Return on Equity
- ROA: Return on Assets
- Debt/Equity: Financial leverage
- Quality Score: Composite (0-100)

Requires: annual_income_statement, annual_balance_sheet populated
"""
import logging

import argparse
import os
from datetime import date
from typing import List, Optional

from utils.loader_helpers import get_active_symbols
from utils.database_context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

class QualityMetricsLoader(OptimalLoader):
    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute quality metrics from balance sheet and income statement."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute("""
                    SELECT revenue, operating_income, net_income
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 1
                """, (symbol,))
                income_row = cur.fetchone()

                cur.execute("""
                    SELECT total_assets, stockholders_equity, current_assets, total_liabilities,
                           current_liabilities, inventory
                    FROM annual_balance_sheet
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 1
                """, (symbol,))
                balance_row = cur.fetchone()

                # Require at least income statement; balance sheet is optional
                if not income_row:
                    return None

                metrics = self._compute_metrics(symbol, income_row, balance_row)
                if metrics:
                    return [metrics]
                return None

        except Exception as e:
            logger.debug(f"Error computing quality metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, income: tuple, balance: Optional[tuple]) -> Optional[dict]:
        """Compute quality metrics from financial data. Balance sheet is optional."""
        revenue, operating_income, net_income = income
        if balance:
            total_assets, stockholders_equity, current_assets, total_liabilities, current_liabilities, inventory = balance
        else:
            total_assets = stockholders_equity = current_assets = total_liabilities = current_liabilities = inventory = None

        metrics = {"symbol": symbol}

        # Operating Margin: Operating Income / Revenue
        if revenue and revenue > 0 and operating_income is not None:
            metrics['operating_margin'] = float(round((operating_income / revenue) * 100, 2))
        else:
            metrics['operating_margin'] = None

        # Net Margin: Net Income / Revenue
        if revenue and revenue > 0 and net_income is not None:
            metrics['net_margin'] = float(round((net_income / revenue) * 100, 2))
        else:
            metrics['net_margin'] = None

        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            metrics['roe'] = float(round((net_income / stockholders_equity) * 100, 2))
        else:
            metrics['roe'] = None

        if total_assets and total_assets > 0 and net_income is not None:
            metrics['roa'] = float(round((net_income / total_assets) * 100, 2))
        else:
            metrics['roa'] = None

        # Debt/Equity: Total Liabilities / Equity
        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            metrics['debt_to_equity'] = float(round(total_liabilities / stockholders_equity, 2))
        else:
            metrics['debt_to_equity'] = None

        # Current Ratio: Current Assets / Current Liabilities
        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            metrics['current_ratio'] = float(round(current_assets / current_liabilities, 2))
        else:
            metrics['current_ratio'] = None

        # Quick Ratio: (Current Assets - Inventory) / Current Liabilities
        if current_liabilities and current_liabilities > 0 and current_assets is not None:
            if inventory and inventory > 0:
                quick_assets = float(current_assets) - float(inventory)
            else:
                quick_assets = float(current_assets)  # No inventory data, use all current assets
            metrics['quick_ratio'] = float(round(quick_assets / float(current_liabilities), 2))
        else:
            metrics['quick_ratio'] = None

        metrics['interest_coverage'] = None

        # Quality Score: Composite (0-100) based on profitability and financial health
        score = 50.0  # Neutral baseline

        if metrics['operating_margin'] is not None:
            # Higher is better (up to 20% = +25 points)
            om_score = min(25, metrics['operating_margin'] / 0.8)
            score += om_score

        if metrics['net_margin'] is not None:
            # Higher is better (up to 10% = +25 points)
            nm_score = min(25, metrics['net_margin'] / 0.4)
            score += nm_score

        if metrics['roe'] is not None and metrics['roe'] > 0:
            # Higher ROE is better (up to 15% = +25 points)
            roe_score = min(25, metrics['roe'] / 0.6)
            score += roe_score

        score = max(0, min(100, score))
        # Note: quality_score is computed but not stored in DB (no column in quality_metrics table)
        # metrics['quality_score'] = float(round(score, 1))

        return metrics

    def transform(self, rows):
        """No transformation needed."""
        return rows

def main():
    parser = argparse.ArgumentParser(description="Quality metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=int(os.getenv("LOADER_PARALLELISM", "8")))
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols(timeout_secs=60)

    loader = QualityMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

