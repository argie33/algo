#!/usr/bin/env python3

"""

Balance Sheet Loader â€" annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_balance / financials_quarterly_balance)
or --period CLI flag for manual runs.
"""

import logging
import os
import sys
from datetime import date
from typing import Any, cast

from loaders.runner import run_loader
from utils.external.sec_edgar import SecEdgarClient
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

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

    def __init__(self, period: str | None = None):
        period = _resolve_period(period)
        assert period in ("annual", "quarterly")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name: str = cast(str, cfg["table_name"])
        self.primary_key: tuple[str, ...] = cast(tuple[str, ...], cfg["primary_key"])
        self._schema_cols: frozenset[str] = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping: dict[str, str] | None = cast(dict[str, str] | None, cfg.get("field_mapping"))
        super().__init__()
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None):
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError as e:
            raise RuntimeError(
                f"[BALANCE_SHEET] {symbol}: CIK not found in SEC ticker cache. "
                "Cannot fetch balance sheet without SEC EDGAR CIK."
            ) from e
        if not cik:
            raise RuntimeError(
                f"[BALANCE_SHEET] CIK resolution failed for {symbol}. "
                "Cannot fetch balance sheet data without SEC EDGAR CIK."
            )
        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)
        try:
            rows = self._sec_client.get_balance_sheet(symbol, period=self.period)
            if not rows:
                raise RuntimeError(
                    f"[BALANCE_SHEET] {symbol}: No {self.period} balance sheet data in SEC EDGAR. "
                    "Cannot proceed without fundamental data."
                )
            logger.info("%s: Fetched %d %s balance sheet row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = []
            for r in rows:
                if "fiscal_year" not in r or r["fiscal_year"] is None:
                    raise ValueError(
                        f"Balance sheet row missing required 'fiscal_year' field: {r}. "
                        f"Cannot filter incremental data without fiscal_year."
                    )
                if r["fiscal_year"] > since_year:
                    filtered.append(r)

            if len(filtered) < len(rows):
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows)"
                )
            return filtered or None
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[BALANCE_SHEET] Failed to fetch balance sheet for {symbol}: {e}. "
                "Cannot proceed without fundamental data."
            ) from e

    def transform(self, rows):
        transformed = []
        for r in rows:
            row: dict[str, Any] = {}
            field_mapping = self._field_mapping or {}
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = field_mapping.get(sec_field, sec_field)
                # Only keep fields in schema
                if db_field in self._schema_cols:
                    row[db_field] = value
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                row["fiscal_quarter"] = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(row["fiscal_quarter"])
            transformed.append(row)

        seen = {}
        for row in transformed:
            key: tuple[Any, ...]
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

    def _validate_row(self, row: dict[str, Any]) -> bool:
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


if __name__ == "__main__":
    sys.exit(run_loader(BalanceSheetLoader))
