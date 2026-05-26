#!/usr/bin/env python3
"""Stability Metrics Loader - Volatility (from price_daily) and Beta (from yfinance).

Computes:
- 30-day volatility: rolling std dev of daily returns
- 60-day volatility: rolling std dev of daily returns
- 252-day volatility: rolling std dev of daily returns (1 year)
- Beta: relative to S&P 500 (from yfinance)

Requires: price_daily table populated with at least 252 days of data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
import math
from datetime import date, timedelta
from typing import List, Optional, Dict

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.db_connection import get_db_connection

logger = get_logger(__name__)


class StabilityMetricsLoader(OptimalLoader):
    """Compute volatility and beta metrics."""

    table_name = "stability_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute stability metrics for this symbol."""
        try:
            metrics = self._compute_stability_metrics(symbol)
            if metrics:
                return [metrics]
            return None
        except Exception as e:
            logger.debug(f"Stability metrics error for {symbol}: {e}")
            return None

    def _compute_stability_metrics(self, symbol: str) -> Optional[Dict]:
        """Compute volatility from price_daily and beta from yfinance."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Fetch last 252 trading days of price data
            cur.execute("""
                SELECT date, close FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 252
            """, (symbol,))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows or len(rows) < 30:
                return None

            # Sort chronologically (oldest to newest)
            prices = sorted([(date(row[0].year, row[0].month, row[0].day) if hasattr(row[0], 'year') else row[0], float(row[1])) for row in rows])

            # Calculate returns
            returns = []
            for i in range(1, len(prices)):
                if prices[i-1][1] > 0:
                    ret = math.log(prices[i][1] / prices[i-1][1])
                    returns.append(ret)

            if not returns:
                return None

            # Calculate volatilities (annualized: sqrt(252) * daily_std)
            volatility_30d = self._calculate_volatility(returns[-30:]) if len(returns) >= 30 else None
            volatility_60d = self._calculate_volatility(returns[-60:]) if len(returns) >= 60 else None
            volatility_252d = self._calculate_volatility(returns) if len(returns) >= 252 else self._calculate_volatility(returns)

            # Get beta from yfinance
            beta = self._get_beta_yfinance(symbol)

            return {
                'symbol': symbol,
                'volatility_30d': round(volatility_30d, 4) if volatility_30d else None,
                'volatility_60d': round(volatility_60d, 4) if volatility_60d else None,
                'volatility_252d': round(volatility_252d, 4) if volatility_252d else None,
                'beta': round(beta, 4) if beta else None,
            }

        except Exception as e:
            logger.debug(f"Stability metrics computation failed for {symbol}: {e}")
            return None

    @staticmethod
    def _calculate_volatility(returns: List[float]) -> Optional[float]:
        """Calculate annualized volatility from returns."""
        if not returns or len(returns) < 2:
            return None

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        daily_std = math.sqrt(variance)

        # Annualize: multiply by sqrt(252)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _get_beta_yfinance(symbol: str) -> Optional[float]:
        """Fetch beta from yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # yfinance returns beta, try common keys
            if 'beta' in info and info['beta'] is not None:
                return float(info['beta'])
            if 'beta3Year' in info and info['beta3Year'] is not None:
                return float(info['beta3Year'])

            return None
        except Exception as e:
            logger.debug(f"Could not fetch beta for {symbol}: {e}")
            return None

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate stability metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get('symbol') is not None


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Stability Metrics Loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)
    loader = StabilityMetricsLoader()
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
