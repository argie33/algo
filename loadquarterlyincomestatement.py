#!/usr/bin/env python3
"""
Quarterly Income Statement Loader - Optimal Pattern using SEC EDGAR.

Uses official SEC EDGAR XBRL API (free, unlimited, accurate).
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadquarterlyincomestatement.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from typing import List, Optional

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class QuarterlyIncomeStatementLoader(OptimalLoader):
    table_name = "quarterly_income_statement"
    primary_key = ("symbol", "fiscal_year", "fiscal_period")
    watermark_field = "fiscal_year"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch quarterly income statement from SEC EDGAR."""
        try:
            from sec_edgar_client import SecEdgarClient
        except ImportError:
            return None

        client = SecEdgarClient()
        cik = client.symbol_to_cik(symbol)
        if not cik:
            return None

        try:
            rows = client.get_income_statement(symbol, period="quarterly")
            if not rows:
                return None

            since_year = int(since) if since else 2000
            filtered = [r for r in rows if r.get("fiscal_year", 0) > since_year]
            return filtered if filtered else None
        except Exception as e:
            logging.debug(f"SEC EDGAR error for {symbol}: {e}")
            return None

    def transform(self, rows):
        """Rows are already clean from SEC EDGAR."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate quarterly income statement row."""
        if not super()._validate_row(row):
            return False
        return (
            row.get("fiscal_year") is not None
            and row.get("fiscal_period") is not None
            and row.get("fiscal_year") > 1990
            and row.get("fiscal_year") < 2100
        )


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
            cur.execute("SELECT DISTINCT symbol FROM stocks ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal quarterly_income_statement loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = QuarterlyIncomeStatementLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
