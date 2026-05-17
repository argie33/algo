#!/usr/bin/env python3
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
from utils.logging_setup import get_logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
logger = get_logger(__name__)
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import date
from pathlib import Path
from typing import List, Optional

from config.credential_helper import get_db_password
from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from utils.optimal_loader import OptimalLoader


log = logging.getLogger(__name__)


class QualityMetricsLoader(OptimalLoader):
    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute quality metrics from balance sheet and income statement."""
        try:
            from utils.db_connection import get_db_connection
        except ImportError:
            return None

        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "stocks"),
                password=get_db_password(),
                database=os.getenv("DB_NAME", "stocks"),
            )
            cur = conn.cursor()

            # Get latest income statement
            cur.execute("""
                SELECT revenue, operating_income, net_income
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            income_row = cur.fetchone()

            # Get latest balance sheet
            # Note: current_liabilities does not exist in annual_balance_sheet schema
            # Use total_liabilities as proxy for current obligations
            cur.execute("""
                SELECT total_assets, stockholders_equity, current_assets, total_liabilities
                FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            balance_row = cur.fetchone()

            cur.close()
            conn.close()

            # Require at least income statement; balance sheet is optional
            if not income_row:
                return None

            metrics = self._compute_metrics(symbol, income_row, balance_row)
            if metrics:
                return [metrics]
            return None

        except Exception as e:
            log.debug(f"Error computing quality metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, income: tuple, balance: Optional[tuple]) -> Optional[dict]:
        """Compute quality metrics from financial data. Balance sheet is optional."""
        revenue, operating_income, net_income = income
        if balance:
            total_assets, stockholders_equity, current_assets, total_liabilities = balance
        else:
            total_assets = stockholders_equity = current_assets = total_liabilities = None

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

        # ROE: Return on Equity = Net Income / Shareholders' Equity
        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            metrics['roe'] = float(round((net_income / stockholders_equity) * 100, 2))
        else:
            metrics['roe'] = None

        # ROA: Return on Assets = Net Income / Total Assets
        if total_assets and total_assets > 0 and net_income is not None:
            metrics['roa'] = float(round((net_income / total_assets) * 100, 2))
        else:
            metrics['roa'] = None

        # Debt/Equity: Total Liabilities / Equity
        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            metrics['debt_to_equity'] = float(round(total_liabilities / stockholders_equity, 2))
        else:
            metrics['debt_to_equity'] = None

        # Current Ratio: Current Assets / Total Liabilities (approximation due to missing current_liabilities column)
        # Note: This is an approximation using total_liabilities instead of current_liabilities
        if total_liabilities and total_liabilities > 0 and current_assets is not None:
            metrics['current_ratio'] = float(round(current_assets / total_liabilities, 2))
        else:
            metrics['current_ratio'] = None

        # Quick Ratio: (Current Assets - Inventory) / Total Liabilities (approximation due to missing current_liabilities column)
        # Note: Also approximated using 0.75 factor since inventory data is not available
        if total_liabilities and total_liabilities > 0 and current_assets is not None:
            quick_assets = float(current_assets) * 0.75
            metrics['quick_ratio'] = float(round(quick_assets / float(total_liabilities), 2))
        else:
            metrics['quick_ratio'] = None

        # Interest Coverage: EBIT / Interest Expense
        # Note: Interest_expense is not available in the current SEC EDGAR data source.
        # To implement interest coverage, add interest_expense column to annual_income_statement
        # and update load_income_statement.py loader to fetch it from EDGAR.
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
    load_env()
    parser = argparse.ArgumentParser(description="Quality metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = QualityMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
