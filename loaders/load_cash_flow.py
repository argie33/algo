#!/usr/bin/env python3
import sys

"""
Cash Flow Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_cashflow / financials_quarterly_cashflow)
or --period CLI flag for manual runs.
"""

import logging

logger = logging.getLogger(__name__)
import os
from datetime import date
from typing import Any, cast

from loaders.runner import run_loader
from utils.external.sec_edgar import SecEdgarClient
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


def _resolve_period(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    period_env = os.getenv("LOADER_PERIOD", "annual")
    return period_env


class CashFlowLoader(OptimalLoader):
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
                f"[CASH_FLOW] {symbol}: CIK not found in SEC ticker cache. "
                "Cannot fetch cash flow without SEC EDGAR CIK."
            ) from e
        if not cik:
            raise RuntimeError(
                f"[CASH_FLOW] CIK resolution failed for {symbol}. Cannot fetch cash flow data without SEC EDGAR CIK."
            )
        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)
        try:
            rows = self._sec_client.get_cash_flow(symbol, period=self.period)
            if not rows:
                raise RuntimeError(
                    f"[CASH_FLOW] {symbol}: No {self.period} cash flow data in SEC EDGAR. "
                    "Cannot proceed without fundamental data."
                )
            logger.info("%s: Fetched %d %s cash flow row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = []
            for r in rows:
                if "fiscal_year" not in r or r["fiscal_year"] is None:
                    raise ValueError(
                        f"Cash flow row missing required 'fiscal_year' field: {r}. "
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
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {e}. Cannot proceed without fundamental data."
            ) from e

    def transform(self, rows):
        transformed = []
        for r in rows:
            row: dict[str, Any] = {}
            capex = None
            field_mapping = self._field_mapping or {}
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = field_mapping.get(sec_field, sec_field)
                if db_field == "capex":
                    capex = value
                elif db_field in self._schema_cols:
                    row[db_field] = value
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
                quarter_value = row["fiscal_quarter"]
                if quarter_value not in quarter_map:
                    raise ValueError(
                        f"Invalid fiscal_quarter value '{quarter_value}' for {r.get('symbol')}. "
                        f"Expected one of {list(quarter_map.keys())}"
                    )
                row["fiscal_quarter"] = quarter_map[quarter_value]
            # Calculate free_cash_flow: OCF - CapEx (both required; omit FCF if capex missing)
            if "free_cash_flow" in self._schema_cols:
                ocf = row.get("operating_cash_flow")
                if ocf is not None and capex is not None:
                    row["free_cash_flow"] = ocf - capex
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
            raise ValueError(
                f"Cash flow row failed base validation (missing primary key): {row}. "
                f"All cash flow records must have symbol and date."
            )

        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            raise ValueError(
                f"Cash flow row has invalid fiscal_year={fy}: {row}. Fiscal year must be between 1990 and 2100."
            )

        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            raise ValueError(
                f"Quarterly cash flow row missing fiscal_quarter: {row}. "
                f"Quarterly data must include quarter information."
            )

        # Reject rows where all key cash flow fields are NULL
        cash_fields = [
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ]
        if all(row.get(field) is None for field in cash_fields):
            raise ValueError(
                f"Cash flow row has all NULL cash flow fields: {row}. "
                f"At least one of operating_cash_flow, investing_cash_flow, financing_cash_flow must be present."
            )

        return True


if __name__ == "__main__":
    sys.exit(run_loader(CashFlowLoader))
