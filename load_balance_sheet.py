#!/usr/bin/env python3
"""
Balance Sheet Loader — annual and quarterly from SEC EDGAR.

Period determined by LOADER_TYPE env var (financials_annual_balance / financials_quarterly_balance)
or --period CLI flag for manual runs.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
import os
import sys
from datetime import date
from typing import List, Optional
from credential_helper import get_db_password, get_db_config

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

_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_balance_sheet",
        "primary_key": ("symbol", "fiscal_year"),
        "schema_cols": frozenset({
            "symbol", "fiscal_year",
            "total_assets", "current_assets", "total_liabilities", "stockholders_equity",
        }),
        "field_mapping": {
            "assets": "total_assets",
            "assets_current": "current_assets",
            "liabilities": "total_liabilities",
        },
    },
    "quarterly": {
        "table_name": "quarterly_balance_sheet",
        "primary_key": ("symbol", "fiscal_year", "fiscal_period"),
        "schema_cols": frozenset({
            "symbol", "fiscal_year", "fiscal_quarter",
            "total_assets", "total_liabilities", "stockholders_equity",
        }),
        "field_mapping": {
            "assets": "total_assets",
            "liabilities": "total_liabilities",
        },
    },
}


def _resolve_period(cli_arg: Optional[str]) -> str:
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "quarterly" if "quarterly" in loader_type else "annual"


class BalanceSheetLoader(OptimalLoader):
    watermark_field = "fiscal_year"

    def __init__(self, period: str):
        assert period in ("annual", "quarterly")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name = cfg["table_name"]
        self.primary_key = cfg["primary_key"]
        self._schema_cols = cfg["schema_cols"]
        self._field_mapping = cfg.get("field_mapping", {})
        super().__init__()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        try:
            from sec_edgar_client import SecEdgarClient
        except ImportError as e:
            logging.error("SecEdgarClient import failed: %s — financial data unavailable", e)
            return None
        try:
            client = SecEdgarClient()
            if not client.symbol_to_cik(symbol):
                logging.debug("Symbol %s not found in SEC EDGAR", symbol)
                return None
            rows = client.get_balance_sheet(symbol, period=self.period)
            if not rows:
                logging.debug("No %s balance sheet data for %s", self.period, symbol)
                return None
            since_year = int(since) if since else 2000
            return [r for r in rows if r.get("fiscal_year", 0) > since_year] or None
        except Exception as e:
            logging.error("SEC EDGAR error for %s: %s", symbol, e)
            return None

    def transform(self, rows):
        transformed = []
        for r in rows:
            row = {}
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = self._field_mapping.get(sec_field, sec_field)
                # Only keep fields in schema
                if db_field in self._schema_cols:
                    row[db_field] = value
            transformed.append(row)

        seen = {}
        for row in transformed:
            if self.period == "annual":
                key = (row.get("symbol"), row.get("fiscal_year"))
            else:
                key = (row.get("symbol"), row.get("fiscal_year"), row.get("fiscal_quarter"))
            if key not in seen:
                seen[key] = row
        return list(seen.values())

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            return False
        if self.period == "quarterly" and row.get("fiscal_period") is None:
            return False
        return True


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
    parser = argparse.ArgumentParser(description="Balance sheet loader (annual/quarterly)")
    parser.add_argument("--period", choices=["annual", "quarterly"],
                        help="Statement period (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    period = _resolve_period(args.period)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = BalanceSheetLoader(period)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

