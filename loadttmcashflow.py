#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Ttm Cash Flow Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadttmcashflow.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

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


class TtmCashFlowLoader(OptimalLoader):
    table_name = "ttm_cash_flow"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute TTM by summing the 4 most recent quarters from quarterly_cash_flow."""
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT fiscal_year, fiscal_quarter, operating_cash_flow, free_cash_flow
                FROM quarterly_cash_flow
                WHERE symbol = %s
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT 4
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        finally:
            cur.close()

        if len(rows) < 4:
            return None

        def _sum(idx):
            return sum(r[idx] for r in rows if r[idx] is not None) or None

        as_of_date = date(rows[0][0], 12, 31).isoformat()
        return [{
            "symbol": symbol,
            "date": as_of_date,
            "operating_cash_flow": _sum(2),
            "free_cash_flow": _sum(3),
        }]

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row) and row.get("date") is not None


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
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
    parser = argparse.ArgumentParser(description="Optimal ttm_cash_flow loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = TtmCashFlowLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
