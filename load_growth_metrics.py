#!/usr/bin/env python3
"""
Growth Metrics Loader - Optimal Pattern (Refactored)

Computes growth metrics from annual financials:
- Revenue Growth: YoY revenue growth
- EPS Growth: YoY earnings per share growth
- Gross Margin Expansion: Change in gross margin
- Operating Margin Trend: Change in operating margin
- Growth Score: Composite (0-100)

Requires: annual_income_statement populated
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


class GrowthMetricsLoader(OptimalLoader):
    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute growth metrics from annual income statement."""
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

            # Fetch latest 2 years of financials for YoY comparison
            cur.execute("""
                SELECT fiscal_year, revenue, cost_of_revenue, gross_profit,
                       operating_income, net_income, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 2
            """, (symbol,))

            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows or len(rows) < 1:
                return None

            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None

            metrics = self._compute_metrics(symbol, latest, prev)
            if metrics:
                return [metrics]
            return None

        except Exception as e:
            log.debug(f"Error computing growth metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple, prev: Optional[tuple]) -> Optional[dict]:
        """Compute growth metrics from financial data."""
        fiscal_year, revenue, cost_of_revenue, gross_profit, operating_income, net_income, eps = latest

        metrics = {
            "symbol": symbol,
            "fiscal_year": fiscal_year,
        }

        # Revenue Growth: YoY
        if prev and revenue and prev[1]:  # prev[1] = previous revenue
            rev_growth = ((revenue - prev[1]) / abs(prev[1])) * 100
            metrics['revenue_growth_pct'] = float(round(rev_growth, 2))
        else:
            metrics['revenue_growth_pct'] = None

        # EPS Growth: YoY
        if prev and eps and prev[6]:  # prev[6] = previous EPS
            eps_growth = ((eps - prev[6]) / abs(prev[6])) * 100
            metrics['eps_growth_pct'] = float(round(eps_growth, 2))
        else:
            metrics['eps_growth_pct'] = None

        # Gross Margin: (Gross Profit / Revenue) * 100
        if revenue and revenue > 0 and gross_profit is not None:
            latest_gm = (gross_profit / revenue) * 100
            metrics['gross_margin_pct'] = float(round(latest_gm, 2))

            # Gross Margin Expansion
            if prev and prev[1] and prev[1] > 0 and prev[3]:  # prev[3] = previous gross_profit
                prev_gm = (prev[3] / prev[1]) * 100
                metrics['gross_margin_expansion_pct'] = float(round(latest_gm - prev_gm, 2))
            else:
                metrics['gross_margin_expansion_pct'] = None
        else:
            metrics['gross_margin_pct'] = None
            metrics['gross_margin_expansion_pct'] = None

        # Operating Margin: (Operating Income / Revenue) * 100
        if revenue and revenue > 0 and operating_income is not None:
            latest_om = (operating_income / revenue) * 100
            metrics['operating_margin_pct'] = float(round(latest_om, 2))

            # Operating Margin Trend
            if prev and prev[1] and prev[1] > 0 and prev[4] is not None:  # prev[4] = previous operating_income
                prev_om = (prev[4] / prev[1]) * 100
                metrics['operating_margin_expansion_pct'] = float(round(latest_om - prev_om, 2))
            else:
                metrics['operating_margin_expansion_pct'] = None
        else:
            metrics['operating_margin_pct'] = None
            metrics['operating_margin_expansion_pct'] = None

        # Growth Score: Composite (0-100)
        # Higher is better: positive YoY growth, expanding margins
        score = 50.0  # Neutral baseline

        if metrics['revenue_growth_pct'] is not None:
            score += min(25, metrics['revenue_growth_pct'] / 4)  # Cap at +25

        if metrics['eps_growth_pct'] is not None:
            score += min(25, metrics['eps_growth_pct'] / 4)  # Cap at +25

        score = max(0, min(100, score))
        metrics['growth_score'] = float(round(score, 1))
        metrics['updated_at'] = date.today().isoformat()

        return metrics

    def transform(self, rows):
        """No transformation needed; metrics already computed."""
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
    parser = argparse.ArgumentParser(description="Growth metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = GrowthMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
