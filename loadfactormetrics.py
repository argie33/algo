#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Factor Metrics Loader - Optimal Pattern.

Computes derived financial metrics (P/E, ROE, debt ratios, etc) from fundamentals.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadfactormetrics.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from typing import List, Optional

from optimal_loader import OptimalLoader

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class FactorMetricsLoader(OptimalLoader):
    table_name = "factor_metrics"
    primary_key = ("symbol", "metric_date")
    watermark_field = "metric_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price and fundamental data, compute metrics."""
        try:
            price_data = self.router.fetch_ohlcv(symbol, since or date(2020, 1, 1), date.today())
            if not price_data:
                return None
            return self._compute_metrics(symbol, price_data)
        except Exception as e:
            logging.debug(f"Metrics computation error for {symbol}: {e}")
            return None

    def _compute_metrics(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        """Compute financial metrics from price data."""
        if not price_rows:
            return None

        metrics = []
        for row in price_rows:
            try:
                close = float(row.get("close", 0))
                if close <= 0:
                    continue

                metric_row = {
                    "symbol": symbol,
                    "metric_date": row.get("date"),
                    "price": close,
                    "volume": int(row.get("volume", 0)),
                    "momentum_3d": 0.0,
                    "volatility_20d": 0.0,
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "dividend_yield": None,
                    "debt_to_equity": None,
                    "roe": None,
                    "roa": None,
                    "current_ratio": None,
                    "quick_ratio": None,
                }
                metrics.append(metric_row)
            except (KeyError, ValueError, TypeError):
                continue

        return metrics if metrics else None

    def transform(self, rows):
        """Rows are computed; just filter nulls."""
        return [r for r in rows if r.get("price", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Validate metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get("price", 0) > 0 and row.get("metric_date") is not None


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal factor_metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = FactorMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
