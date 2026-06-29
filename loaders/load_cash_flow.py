#!/usr/bin/env python3
"""
Cash Flow Loader - annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var or --period CLI flag for manual runs.

This loader uses the consolidated SecEdgarStatementLoader base class.
"""

import logging
import sys
from datetime import datetime
from typing import Any

from loaders.runner import run_loader
from loaders.sec_edgar_statement_loader import SecEdgarStatementLoader

logger = logging.getLogger(__name__)

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
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
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
            "fiscal_period": "fiscal_quarter",
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
        },
    },
}


class CashFlowLoader(SecEdgarStatementLoader):
    """SEC EDGAR cash flow statement loader for real stocks only (not ETFs/bonds).

    Financial data from SEC EDGAR is only available for companies that file with the SEC.
    ETFs, bonds, and other securities don't have cash flow statements, so we exclude them.
    """

    exclude_etfs_from_symbols = True

    def __init__(self, period: str | None = None):
        super().__init__("cash_flow", _PERIOD_CONFIG, period)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform and add created_at watermark for downstream loaders."""
        result = super().transform(rows)
        now = datetime.now().isoformat()
        for row in result:
            row["created_at"] = now
        return result

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate cash flow-specific constraints."""
        if not super()._validate_row(row):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Row failed parent validation (missing primary key fields) "
                f"for symbol '{symbol}'. Row: {row}."
            )
            return False

        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Row has invalid or missing fiscal_year for symbol '{symbol}'. "
                f"Expected 4-digit year between 1990 and 2100, got: {fy}."
            )
            return False

        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Quarterly row missing required 'fiscal_quarter' "
                f"for symbol '{symbol}' fiscal_year {fy}."
            )
            return False

        # Reject rows where all key cash flow fields are NULL
        flow_fields = ["operating_cash_flow", "investing_cash_flow", "financing_cash_flow"]
        if all(row.get(field) is None for field in flow_fields):
            symbol = row.get("symbol", "UNKNOWN")
            logger.error(
                f"[{self.table_name}] Row has all critical cash flow fields NULL for symbol '{symbol}' "
                f"fiscal_year {fy}. This indicates incomplete data from SEC EDGAR. "
                f"Row: {row}. Rejecting row — cannot trust incomplete financial data."
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(CashFlowLoader))
