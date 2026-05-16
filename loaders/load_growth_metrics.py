#!/usr/bin/env python3
"""
Growth Metrics Loader - Optimal Pattern (Refactored)

Computes multi-year growth metrics from annual financials:
- Revenue Growth: 1Y, 3Y, 5Y YoY growth
- EPS Growth: 1Y, 3Y, 5Y YoY growth
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
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute multi-year growth metrics from annual income statement."""
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

            # Fetch up to 10 years of financials to calculate 1Y, 3Y, 5Y growth
            cur.execute("""
                SELECT fiscal_year, revenue, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 10
            """, (symbol,))

            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows or len(rows) < 1:
                return None

            # Sort by year ascending for easier calculation
            rows = list(reversed(rows))

            latest = rows[-1]  # Most recent year
            metrics = self._compute_metrics(symbol, latest, rows)

            if metrics:
                return [metrics]
            return None

        except Exception as e:
            log.debug(f"Error computing growth metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple, all_years: list) -> Optional[dict]:
        """Compute multi-year growth metrics."""
        latest_year, latest_rev, latest_eps = latest

        metrics = {"symbol": symbol}

        # Calculate 1Y, 3Y, 5Y growth rates
        for lookback in [1, 3, 5]:
            # Revenue growth
            idx = -(lookback + 1)
            if len(all_years) > lookback and all_years[idx] and latest_rev:
                prev_year, prev_rev, prev_eps = all_years[idx]
                if prev_rev and prev_rev > 0:
                    rev_growth = (((latest_rev / prev_rev) ** (1.0 / lookback)) - 1) * 100
                    metrics[f'revenue_growth_{lookback}y'] = float(round(rev_growth, 2))
                else:
                    metrics[f'revenue_growth_{lookback}y'] = None
            else:
                metrics[f'revenue_growth_{lookback}y'] = None

            # EPS growth
            if len(all_years) > lookback and all_years[idx] and latest_eps:
                prev_year, prev_rev, prev_eps = all_years[idx]
                if prev_eps and prev_eps > 0:
                    eps_growth = (((latest_eps / prev_eps) ** (1.0 / lookback)) - 1) * 100
                    metrics[f'eps_growth_{lookback}y'] = float(round(eps_growth, 2))
                else:
                    metrics[f'eps_growth_{lookback}y'] = None
            else:
                metrics[f'eps_growth_{lookback}y'] = None

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
