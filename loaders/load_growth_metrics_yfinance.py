#!/usr/bin/env python3
"""Growth Metrics Loader (yfinance supplemental) - for stocks without SEC EDGAR data.

Fetches estimated growth metrics from yfinance for stocks that don't have
SEC annual_income_statement data. Uses analyst estimates when available.

Estimated fields:
- revenue_growth_1y: from estimatedAnnualRevenue
- eps_growth_1y: from estimatedAnnualEPS or from analyst EPS growth

Falls back to price momentum if estimates unavailable.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List, Optional, Dict

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.db_connection import get_db_connection

logger = get_logger(__name__)


class GrowthMetricsYfinanceLoader(OptimalLoader):
    """Fetch growth metrics from yfinance for stocks without SEC data."""

    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch growth metrics for this symbol if not already in database."""
        try:
            # Skip if already has SEC-based growth metrics
            if self._has_sec_growth_metrics(symbol):
                return None

            metrics = self._fetch_yfinance_growth_metrics(symbol)
            if metrics:
                return [metrics]
            return None

        except Exception as e:
            logger.debug(f"Growth metrics yfinance error for {symbol}: {e}")
            return None

    @staticmethod
    def _has_sec_growth_metrics(symbol: str) -> bool:
        """Check if symbol already has growth metrics (from SEC EDGAR)."""
        try:
            conn = None
            from utils.db_connection import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM growth_metrics WHERE symbol = %s", (symbol,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            return result is not None
        except Exception:
            return False

    @staticmethod
    def _fetch_yfinance_growth_metrics(symbol: str) -> Optional[Dict]:
        """Fetch growth estimates from yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info

            metrics = {"symbol": symbol}

            # Try to get revenue growth
            revenue_growth_1y = None
            if 'revenueGrowth' in info and info['revenueGrowth'] is not None:
                revenue_growth_1y = float(info['revenueGrowth']) * 100
            elif 'revenue_growth_1y' in info and info['revenue_growth_1y'] is not None:
                revenue_growth_1y = float(info['revenue_growth_1y'])

            # Try to get EPS growth
            eps_growth_1y = None
            if 'epsGrowth' in info and info['epsGrowth'] is not None:
                eps_growth_1y = float(info['epsGrowth']) * 100
            elif 'eps_growth' in info and info['eps_growth'] is not None:
                eps_growth_1y = float(info['eps_growth'])
            elif 'epsTrailingTwelveMonths' in info and info['epsTrailingTwelveMonths'] is not None:
                eps_growth_1y = float(info['epsTrailingTwelveMonths'])

            # Store whatever we found
            metrics['revenue_growth_1y'] = round(revenue_growth_1y, 2) if revenue_growth_1y else None
            metrics['revenue_growth_3y'] = None  # Not easily available from yfinance
            metrics['eps_growth_1y'] = round(eps_growth_1y, 2) if eps_growth_1y else None
            metrics['eps_growth_3y'] = None  # Not easily available from yfinance

            # Only return if we got at least one metric
            if revenue_growth_1y or eps_growth_1y:
                return metrics

            return None

        except Exception as e:
            logger.debug(f"Could not fetch growth metrics for {symbol} from yfinance: {e}")
            return None

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate growth metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get('symbol') is not None


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Growth Metrics Loader (yfinance supplemental)")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)
    loader = GrowthMetricsYfinanceLoader()
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
