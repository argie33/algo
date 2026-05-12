#!/usr/bin/env python3
"""
Factor Metrics Loader - Optimal Pattern.

Computes price-derived metrics (momentum, volatility) per symbol per day from
OHLCV data. Fundamental ratios (PE, PB, etc.) are left NULL until financial
statement data is joined in a future enrichment step.

Run:
    python3 loadfactormetrics.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import logging
import math
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class FactorMetricsLoader(OptimalLoader):
    table_name = "factor_metrics"
    primary_key = ("symbol", "metric_date")
    watermark_field = "metric_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        start = (since - timedelta(days=30)) if since else date(2020, 1, 1)
        end = date.today()
        try:
            price_rows = self.router.fetch_ohlcv(symbol, start, end)
            if not price_rows:
                return None
            return self._compute_metrics(symbol, price_rows, since)
        except Exception as e:
            logging.debug("Metrics error for %s: %s", symbol, e)
            return None

    def _compute_metrics(self, symbol: str, rows: List[dict],
                         since: Optional[date]) -> Optional[List[dict]]:
        rows_sorted = sorted(rows, key=lambda r: r.get("date", ""))
        closes = [float(r["close"]) for r in rows_sorted if r.get("close")]
        dates = [r["date"] for r in rows_sorted if r.get("close")]
        volumes = [int(r.get("volume") or 0) for r in rows_sorted if r.get("close")]

        if len(closes) < 4:
            return None

        daily_returns = [
            (closes[i] / closes[i - 1] - 1) if closes[i - 1] > 0 else 0.0
            for i in range(1, len(closes))
        ]

        metrics = []
        since_str = since.isoformat() if since else None

        for i in range(len(closes)):
            row_date = dates[i]
            if since_str and row_date <= since_str:
                continue

            momentum_3d = None
            if i >= 3 and closes[i - 3] > 0:
                momentum_3d = round((closes[i] / closes[i - 3] - 1) * 100, 4)

            volatility_20d = None
            if i >= 20:
                window = daily_returns[i - 20:i]
                if len(window) >= 20:
                    mean = sum(window) / len(window)
                    variance = sum((r - mean) ** 2 for r in window) / len(window)
                    volatility_20d = round(math.sqrt(variance) * math.sqrt(252) * 100, 4)

            if momentum_3d is None and volatility_20d is None:
                continue

            metrics.append({
                "symbol": symbol,
                "metric_date": row_date,
                "price": round(closes[i], 4),
                "volume": volumes[i],
                "momentum_3d": momentum_3d,
                "volatility_20d": volatility_20d,
                "pe_ratio": None,
                "pb_ratio": None,
                "dividend_yield": None,
                "debt_to_equity": None,
                "roe": None,
                "roa": None,
                "current_ratio": None,
                "quick_ratio": None,
            })

        return metrics or None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return row.get("price", 0) > 0 and row.get("metric_date") is not None


def get_active_symbols() -> List[str]:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=credential_manager.get_db_credentials()["password"],
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Factor metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = FactorMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
