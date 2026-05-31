#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Income Statement Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_income / financials_quarterly_income)
or --period CLI flag for manual runs.
"""
import logging
import argparse
logger = logging.getLogger(__name__)
import os
from datetime import date
from typing import List, Optional
from utils.loader_helpers import get_active_symbols
from utils.sec_edgar_client import SecEdgarClient

from utils.optimal_loader import OptimalLoader

_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_income_statement",
        "primary_key": ("symbol", "fiscal_year"),
        "edgar_period": "annual",
        "schema_cols": frozenset({
            "symbol", "fiscal_year", "revenue", "cost_of_revenue",
            "gross_profit", "operating_income", "net_income", "earnings_per_share",
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
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "edgar_period": "quarterly",
        "schema_cols": frozenset({
            "symbol", "fiscal_year", "fiscal_quarter", "revenue", "net_income", "earnings_per_share",
        }),
        "field_mapping": {
            "fiscal_period": "fiscal_quarter",   # "Q1".."Q4"  ->  integer (converted in transform)
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "net_income_loss": "net_income",
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
        },
    },
}

def _resolve_period(cli_arg: Optional[str]) -> str:
    """Resolve period from CLI arg or LOADER_PERIOD env var (not LOADER_TYPE)."""
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "annual")

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
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        try:
            if not self._sec_client.symbol_to_cik(symbol):
                logging.debug("Symbol %s not found in SEC EDGAR", symbol)
                return None
            rows = self._sec_client.get_income_statement(symbol, period=self._edgar_period)
            if not rows:
                logging.debug("No %s income statement data for %s", self._edgar_period, symbol)
                return None
            since_year = int(since.year) if since else 2000
            return [r for r in rows if r.get("fiscal_year", 0) > since_year] or None
        except Exception as e:
            logging.error("SEC EDGAR error for %s: %s", symbol, e)
            return None

    _QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

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
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                row["fiscal_quarter"] = self._QUARTER_MAP.get(row["fiscal_quarter"])
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
        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            return False

        # Reject rows where all key financial fields are NULL
        # (indicates API failure or no data available for this symbol/year)
        financial_fields = ["gross_profit", "operating_income", "net_income", "cost_of_revenue"]
        if all(row.get(field) is None for field in financial_fields):
            return False

        return True

def main():
    parser = argparse.ArgumentParser(description="Income statement loader (annual/quarterly)")
    parser.add_argument("--period", choices=["annual", "quarterly"],
                        help="Statement period (defaults to LOADER_PERIOD env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    default_parallelism = int(os.getenv("LOADER_PARALLELISM", "1"))
    parser.add_argument("--parallelism", type=int, default=default_parallelism,
                        help=f"Worker threads (default from LOADER_PARALLELISM env var: {default_parallelism})")
    args = parser.parse_args()

    period = _resolve_period(args.period)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols(timeout_secs=60)

    loader = IncomeStatementLoader(period)
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

