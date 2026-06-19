#!/usr/bin/env python3

"""

Balance Sheet Loader â€" annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_balance / financials_quarterly_balance)
or --period CLI flag for manual runs.
"""

import argparse
import logging
import sys


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
        "table_name": "annual_balance_sheet",
        "primary_key": ("symbol", "fiscal_year"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "total_assets",
                "current_assets",
                "total_liabilities",
                "current_liabilities",
                "stockholders_equity",
                "inventory",
                "cash_and_equivalents",
                "accounts_receivable",
                "ppe_net",
                "goodwill",
                "long_term_debt",
            }
        ),
        "field_mapping": {
            # SEC EDGAR client converts concept names to snake_case before returning
            # Total assets
            "assets": "total_assets",
            # Current assets
            "assets_current": "current_assets",
            "cash_and_cash_equivalents_at_carrying_value": "cash_and_equivalents",
            "accounts_receivable_net_current": "accounts_receivable",
            "inventory_net": "inventory",
            # Fixed assets
            "property_plant_and_equipment_net": "ppe_net",
            "goodwill": "goodwill",
            # Total liabilities
            "liabilities": "total_liabilities",
            # Current liabilities
            "liabilities_current": "current_liabilities",
            # Equity
            "stockholders_equity": "stockholders_equity",
            # Long-term debt
            "long_term_debt": "long_term_debt",
        },
    },
    "quarterly": {
        "table_name": "quarterly_balance_sheet",
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "fiscal_quarter",
                "total_assets",
                "current_assets",
                "total_liabilities",
                "stockholders_equity",
            }
        ),
        "field_mapping": {
            "fiscal_period": "fiscal_quarter",  # "Q1".."Q4"  ->  integer (converted in transform)
            # SEC EDGAR client converts concept names to snake_case before returning
            "assets": "total_assets",
            "assets_current": "current_assets",
            "liabilities": "total_liabilities",
            "stockholders_equity": "stockholders_equity",
        },
    },
}


def _resolve_period(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    period_env = os.getenv("LOADER_PERIOD", "annual")
    return period_env


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
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None):
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
            if not cik:
                raise RuntimeError(
                    f"[BALANCE_SHEET] CIK resolution failed for {symbol}. "
                    "Cannot fetch balance sheet data without SEC EDGAR CIK."
                )
            logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

            rows = self._sec_client.get_balance_sheet(symbol, period=self.period)
            if not rows:
                raise RuntimeError(
                    f"[BALANCE_SHEET] No {self.period} balance sheet data found for {symbol} (CIK={cik}). "
                    "Cannot load fundamentals without balance sheet data."
                )
            logger.info("%s: Fetched %d %s balance sheet row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = [r for r in rows if r.get("fiscal_year", 0) > since_year]
            if len(filtered) < len(rows):
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows)"
                )
            if not filtered:
                raise RuntimeError(
                    f"[BALANCE_SHEET] No new balance sheet data for {symbol} after watermark (since {since}). "
                    "Cannot proceed with empty incremental load."
                )
            return filtered
        except Exception as e:
            raise RuntimeError(
                f"[BALANCE_SHEET] Failed to fetch balance sheet for {symbol}: {e}. "
                "Cannot proceed without fundamental data."
            )

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
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                row["fiscal_quarter"] = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(
                    row["fiscal_quarter"]
                )
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

        # Reject rows where all key balance sheet fields are NULL
        balance_fields = ["total_assets", "current_assets", "total_liabilities"]
        if all(row.get(field) is None for field in balance_fields):
            return False

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Balance sheet loader (annual/quarterly)"
    )
    parser.add_argument(
        "--period",
        choices=["annual", "quarterly"],
        help="Statement period (defaults to LOADER_PERIOD env var)",
    )
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    default_parallelism = get_parallelism("balance_sheet")
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

    loader = BalanceSheetLoader(period)
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
