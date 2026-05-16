#!/usr/bin/env python3
"""
Value Metrics Loader - Optimal Pattern (Refactored)

Computes value metrics from financials:
- Price to Book: Market Cap / Stockholders Equity
- Price to Sales: Market Cap / Revenue
- Dividend Yield: Annual Dividend / Stock Price
- Value Score: Composite (0-100)

Requires: annual_balance_sheet, annual_income_statement, key_metrics populated
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


class ValueMetricsLoader(OptimalLoader):
    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute value metrics from financial data."""
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

            # Get latest balance sheet equity
            cur.execute("""
                SELECT stockholders_equity FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            equity_row = cur.fetchone()

            # Get latest income statement revenue
            cur.execute("""
                SELECT revenue FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            revenue_row = cur.fetchone()

            # Get current price (most recent daily price)
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))
            price_row = cur.fetchone()

            # Get market cap from key_metrics
            cur.execute("""
                SELECT market_cap FROM key_metrics
                WHERE symbol = %s
                LIMIT 1
            """, (symbol,))
            market_cap_row = cur.fetchone()

            cur.close()
            conn.close()

            if not any([equity_row, revenue_row, price_row, market_cap_row]):
                return None

            metrics = self._compute_metrics(
                symbol,
                equity_row[0] if equity_row else None,
                revenue_row[0] if revenue_row else None,
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
    def _compute_metrics(symbol: str, equity: Optional[float], revenue: Optional[float],
                        price: Optional[float], market_cap: Optional[float]) -> Optional[dict]:
        """Compute value metrics from financial data."""
        metrics = {"symbol": symbol}

        # Price to Book: Market Cap / Stockholders Equity
        if market_cap and equity and equity > 0:
            pb = market_cap / equity
            metrics['price_to_book'] = float(round(pb, 2))
        else:
            metrics['price_to_book'] = None

        # Price to Sales: Market Cap / Revenue
        if market_cap and revenue and revenue > 0:
            ps = market_cap / revenue
            metrics['price_to_sales'] = float(round(ps, 2))
        else:
            metrics['price_to_sales'] = None

        # Value Score: Inverse of P/B and P/S (lower is better)
        # Formula: Score based on attractive valuation multiples
        score = 50.0  # Neutral baseline

        if metrics['price_to_book'] is not None:
            # Lower PB is better (max +25 for PB < 1.0, scales down)
            pb_score = max(0, 25 * (2.0 - metrics['price_to_book']))
            score += min(25, pb_score)

        if metrics['price_to_sales'] is not None:
            # Lower PS is better (max +25 for PS < 1.0)
            ps_score = max(0, 25 * (3.0 - metrics['price_to_sales']))
            score += min(25, ps_score)

        score = max(0, min(100, score))
        metrics['value_score'] = float(round(score, 1))
        metrics['updated_at'] = date.today().isoformat()

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
