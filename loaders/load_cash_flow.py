#!/usr/bin/env python3
import sys


"""
Cash Flow Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_cashflow / financials_quarterly_cashflow)
or --period CLI flag for manual runs.
"""

import argparse
import logging


logger = logging.getLogger(__name__)
import os
from datetime import date
from typing import Optional

from utils.external.sec_edgar import SecEdgarClient
from utils.loaders.config import get_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_cash_flow",
        "primary_key": ("symbol", "fiscal_year"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "operating_cash_flow",
                "investing_cash_flow",
                "financing_cash_flow",
                "free_cash_flow",
            }
        ),
        "field_mapping": {
            # SEC EDGAR client converts concept names to snake_case before returning
            # Operating activities
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            # Investing activities
            "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            # Financing activities
            "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
            # Depreciation metrics
            "depreciation": "depreciation",
            "depreciation_and_amortization": "depreciation_and_amortization",
        },
    },
    "quarterly": {
        "table_name": "quarterly_cash_flow",
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "fiscal_quarter",
                "operating_cash_flow",
                "investing_cash_flow",
                "financing_cash_flow",
                "free_cash_flow",
            }
        ),
        "field_mapping": {
            "fiscal_period": "fiscal_quarter",  # "Q1".."Q4"  ->  integer (converted in transform)
            # SEC EDGAR client converts concept names to snake_case before returning
            # Operating activities
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            # Investing activities
            "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            # Financing activities
            "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
        },
    },
}


def _resolve_period(cli_arg: Optional[str]) -> str:
    if cli_arg:
        return cli_arg
    period_env = os.getenv("LOADER_PERIOD", "annual")
    return period_env


class CashFlowLoader(OptimalLoader):
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
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
            if not cik:
                logger.warning("Symbol %s not found in SEC EDGAR (CIK resolution failed)", symbol)
                return None
            logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

            rows = self._sec_client.get_cash_flow(symbol, period=self.period)
            if not rows:
                logger.warning("No %s cash flow data for %s (symbol=%s, cik=%s)",
                               self.period, symbol, symbol, cik)
                return None
            logger.info("%s: Fetched %d %s cash flow row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = [r for r in rows if r.get("fiscal_year", 0) > since_year]
            if len(filtered) < len(rows):
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows)"
                )
            return filtered or None
        except Exception as e:
            raise RuntimeError(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {e}. "
                "Cannot proceed without fundamental data."
            )

    def transform(self, rows):
        transformed = []
        for r in rows:
            row = {}
            capex = None
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = self._field_mapping.get(sec_field, sec_field)
                if db_field == "capex":
                    capex = value
                elif db_field in self._schema_cols:
                    row[db_field] = value
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                row["fiscal_quarter"] = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(
                    row["fiscal_quarter"]
                )
            # Calculate free_cash_flow if we have operating_cash_flow and capex
            if "free_cash_flow" in self._schema_cols:
                ocf = row.get("operating_cash_flow")
                if ocf and capex:
                    row["free_cash_flow"] = ocf - capex
                elif ocf:
                    row["free_cash_flow"] = ocf  # Fallback if no capex data
            transformed.append(row)

        seen = {}
        for row in transformed:
            if self.period == "annual":
                key = (row.get("symbol"), row.get("fiscal_year"))
            else:
                key = (
                    row.get("symbol"),
                    row.get("fiscal_year"),
                    row.get("fiscal_quarter"),
                )
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

        # Reject rows where all key cash flow fields are NULL
        cash_fields = [
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ]
        if all(row.get(field) is None for field in cash_fields):
            return False

        return True


def main():
    parser = argparse.ArgumentParser(description="Cash flow loader (annual/quarterly)")
    parser.add_argument(
        "--period",
        choices=["annual", "quarterly"],
        help="Statement period (defaults to LOADER_PERIOD env var)",
    )
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    default_parallelism = get_parallelism("cash_flow")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=default_parallelism,
        help=f"Worker threads (default from LOADER_PARALLELISM env var: {default_parallelism})",
    )
    args = parser.parse_args()

    period = _resolve_period(args.period)
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",")]
        if args.symbols
        else get_active_symbols(timeout_secs=60)
    )

    loader = CashFlowLoader(period)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        logger.error(
            f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
