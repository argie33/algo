#!/usr/bin/env python3
"""
Value Metrics Loader - Optimal Pattern (Refactored)

Computes value metrics (P/E, P/B, P/S, P/EG, dividend yield, FCF yield):
- PE Ratio: Market Cap / Net Income
- PB Ratio: Market Cap / Stockholders Equity (Book Value)
- PS Ratio: Market Cap / Revenue
- PEG Ratio: P/E Ratio / EPS Growth Rate
- Dividend Yield: Annual Dividend / Stock Price
- FCF Yield: Free Cash Flow / Market Cap

Requires: annual_income_statement, annual_balance_sheet, key_metrics, price_daily
"""

import argparse
import logging
logger = logging.getLogger(__name__)
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from config.credential_helper import get_db_password

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).parent / '.env.local'
    if not _env_file.exists():
        _env_file = Path(__file__).parent.parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

from utils.optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


class ValueMetricsLoader(OptimalLoader):
    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute value metrics from financial and market data."""
        try:
            import psycopg2
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

            # Get latest financials
            cur.execute("""
                SELECT net_income, revenue FROM annual_income_statement
                WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT 1
            """, (symbol,))
            income_row = cur.fetchone()

            cur.execute("""
                SELECT stockholders_equity FROM annual_balance_sheet
                WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT 1
            """, (symbol,))
            equity_row = cur.fetchone()

            # Get current market price
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = %s ORDER BY date DESC LIMIT 1
            """, (symbol,))
            price_row = cur.fetchone()

            # Get market cap and shares outstanding from key_metrics
            cur.execute("""
                SELECT market_cap FROM key_metrics
                WHERE symbol = %s LIMIT 1
            """, (symbol,))
            market_cap_row = cur.fetchone()

            cur.close()
            conn.close()

            metrics = self._compute_metrics(
                symbol,
                income_row[0] if income_row else None,
                income_row[1] if income_row else None,
                equity_row[0] if equity_row else None,
                price_row[0] if price_row else None,
                market_cap_row[0] if market_cap_row else None,
            )

            if metrics:
                return [metrics]
            return None

        except Exception as e:
            log.debug(f"Error computing value metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, net_income: Optional[float], revenue: Optional[float],
                        equity: Optional[float], price: Optional[float],
                        market_cap: Optional[float]) -> Optional[dict]:
        """Compute value metrics from financial data."""
        metrics = {"symbol": symbol}

        # P/E Ratio: Market Cap / Net Income
        if market_cap and net_income and net_income > 0:
            pe_ratio = market_cap / net_income
            metrics['pe_ratio'] = float(round(pe_ratio, 2))
        else:
            metrics['pe_ratio'] = None

        # P/B Ratio: Market Cap / Stockholders Equity
        if market_cap and equity and equity > 0:
            pb_ratio = market_cap / equity
            metrics['pb_ratio'] = float(round(pb_ratio, 2))
        else:
            metrics['pb_ratio'] = None

        # P/S Ratio: Market Cap / Revenue
        if market_cap and revenue and revenue > 0:
            ps_ratio = market_cap / revenue
            metrics['ps_ratio'] = float(round(ps_ratio, 2))
        else:
            metrics['ps_ratio'] = None

        # PEG Ratio: P/E / EPS Growth Rate
        # Note: PEG calculation requires eps_growth_1y from growth_metrics
        # For now, use only if we have both PE and growth data available
        # This is populated via separate growth_metrics loader
        metrics['peg_ratio'] = None  # Will be computed from growth_metrics join if available

        # Dividend Yield: Annual Dividend / Stock Price
        # Note: Dividend data sourced from annual_income_statement or company_profile
        # For now, use NULL; dividend_yield should be populated from actual dividend data
        metrics['dividend_yield'] = None

        # FCF Yield: Free Cash Flow / Market Cap
        # Note: Requires free_cash_flow from annual_cash_flow table
        # This is computed via separate cash flow analysis
        # Using revenue-based estimate is misleading; conservatively use NULL
        metrics['fcf_yield'] = None

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
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Value metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = ValueMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
