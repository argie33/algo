#!/usr/bin/env python3
"""
Income Statement Loader — annual and quarterly from SEC EDGAR.

Period determined by LOADER_TYPE env var (financials_annual_income / financials_quarterly_income)
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
        "table_name": "annual_income_statement",
        "primary_key": ("symbol", "fiscal_year"),
        "edgar_period": "annual",
        "schema_cols": frozenset({
            "symbol", "fiscal_year", "revenue", "cost_of_revenue",
            "gross_profit", "operating_expenses", "operating_income", "net_income", "earnings_per_share",
            "shares_outstanding",
        }),
        "field_mapping": {
            # Revenue: SEC EDGAR returns "Revenues" (FY2018+) or "SalesRevenueNet" (FY2009-2017)
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            # Cost of Revenue: SEC EDGAR returns "CostOfRevenue" or "CostsAndExpenses"
            "cost_of_revenue": "cost_of_revenue",
            "costs_and_expenses": "cost_of_revenue",
            # Gross Profit
            "gross_profit": "gross_profit",
            # Operating metrics
            "operating_expenses": "operating_expenses",
            "operating_income_loss": "operating_income",
            # Net Income
            "net_income_loss": "net_income",
            # EPS: SEC EDGAR returns both basic and diluted, we prefer basic
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
            # Shares outstanding
            "weighted_average_number_of_shares_outstanding_basic": "shares_outstanding",
        },
    },
    "quarterly": {
        "table_name": "quarterly_income_statement",
        "primary_key": ("symbol", "fiscal_year", "fiscal_period"),
        "edgar_period": "quarterly",
        "schema_cols": frozenset({
            "symbol", "fiscal_year", "fiscal_period", "revenue", "net_income", "earnings_per_share",
        }),
        "field_mapping": {
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "net_income_loss": "net_income",
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
        },
    },
}


def _resolve_period(cli_arg: Optional[str]) -> str:
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "quarterly" if "quarterly" in loader_type else "annual"


class IncomeStatementLoader(OptimalLoader):
    watermark_field = "fiscal_year"

    def __init__(self, period: str):
        assert period in ("annual", "quarterly")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name = cfg["table_name"]
        self.primary_key = cfg["primary_key"]
        self._edgar_period = cfg["edgar_period"]
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
            rows = client.get_income_statement(symbol, period=self._edgar_period)
            if not rows:
                logging.debug("No %s income statement data for %s", self._edgar_period, symbol)
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
                    if db_field not in row:  # Don't overwrite if already set (e.g., prefer basic over diluted EPS)
                        row[db_field] = value
            transformed.append(row)

        seen = {}
        for row in transformed:
            if self.period == "annual":
                key = (row.get("symbol"), row.get("fiscal_year"))
            else:
                key = (row.get("symbol"), row.get("fiscal_year"), row.get("fiscal_period"))
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

        # Reject rows where all key financial fields are NULL
        # (indicates API failure or no data available for this symbol/year)
        financial_fields = ["gross_profit", "operating_income", "net_income", "cost_of_revenue"]
        if all(row.get(field) is None for field in financial_fields):
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
    parser = argparse.ArgumentParser(description="Income statement loader (annual/quarterly)")
    parser.add_argument("--period", choices=["annual", "quarterly"],
                        help="Statement period (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    period = _resolve_period(args.period)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = IncomeStatementLoader(period)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

