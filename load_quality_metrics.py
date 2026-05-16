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

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from credential_helper import get_db_password

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


class QualityMetricsLoader(OptimalLoader):
    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute quality metrics from balance sheet and income statement."""
        try:
            import psycopg2
        except ImportError:
            return None

        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "postgres"),
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
            cur.execute("""
                SELECT total_assets, stockholders_equity, current_assets, current_liabilities
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
            total_assets, stockholders_equity, current_assets, current_liabilities = balance
        else:
            total_assets = stockholders_equity = current_assets = current_liabilities = None

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

        # Debt/Equity: (Total Assets - Equity) / Equity
        if stockholders_equity and stockholders_equity > 0 and total_assets:
            debt = total_assets - stockholders_equity
            metrics['debt_to_equity'] = float(round(debt / stockholders_equity, 2))
        else:
            metrics['debt_to_equity'] = None

        # Current Ratio: Current Assets / Current Liabilities
        if current_liabilities and current_liabilities > 0:
            metrics['current_ratio'] = float(round(current_assets / current_liabilities, 2))
        else:
            metrics['current_ratio'] = None

        # Quick Ratio: (Current Assets - Inventory) / Current Liabilities
        # For simplicity, using current_assets / 1.5 as proxy (assume inventory ~40% of CA)
        if current_liabilities and current_liabilities > 0:
            quick_assets = current_assets * 0.6 if current_assets else 0
            metrics['quick_ratio'] = float(round(quick_assets / current_liabilities, 2))
        else:
            metrics['quick_ratio'] = None

        # Interest Coverage: EBIT / Interest Expense
        # Approximated as Operating Income / 0 (no interest data), so set to None
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
        metrics['quality_score'] = float(round(score, 1))

        return metrics

    def transform(self, rows):
        """No transformation needed."""
        return rows


def get_active_symbols() -> List[str]:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            # Get symbols with income statement (balance sheet optional)
            cur.execute("""
                SELECT DISTINCT symbol
                FROM annual_income_statement
                ORDER BY symbol
            """)
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
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
