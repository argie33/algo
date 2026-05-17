#!/usr/bin/env python3
import sys
from utils.logging_setup import get_logger
from pathlib import Path

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Ttm Cash Flow Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadttmcashflow.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
logger = get_logger(__name__)
from config.credential_helper import get_db_password, get_db_config
from utils.loader_helpers import get_active_symbols
import os
import sys
from config.env_loader import load_env
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader




class TtmCashFlowLoader(OptimalLoader):
    table_name = "ttm_cash_flow"
    primary_key = ("symbol", "date", "item_name")
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
        """Transform wide format to long format (item_name, value)."""
        transformed = []
        for row in rows:
            symbol = row.get("symbol")
            date_val = row.get("date")
            for field, value in row.items():
                if field not in ("symbol", "date") and value is not None:
                    transformed.append({
                        "symbol": symbol,
                        "date": date_val,
                        "item_name": field,
                        "value": value,
                    })
        return transformed

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row) and row.get("date") is not None



def main():
    load_env()
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

