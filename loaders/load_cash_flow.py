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
from typing import Optional

from loaders.runner import run_loader
from utils.external.sec_edgar import SecEdgarClient
from utils.loaders.config import get_parallelism
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

    def __init__(self, period: str):
        assert period in ("annual", "quarterly")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name: str = cfg["table_name"]  # type: ignore[assignment]
        self.primary_key: tuple[str, ...] = cfg["primary_key"]  # type: ignore[assignment]
        self._schema_cols: frozenset[str] = cfg["schema_cols"]  # type: ignore[assignment]
        self._field_mapping: dict[str, str] | None = cfg.get("field_mapping")
        super().__init__()
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None):
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
            if not cik:
                raise RuntimeError(
                    f"[CASH_FLOW] CIK resolution failed for {symbol}. "
                    "Cannot fetch cash flow data without SEC EDGAR CIK."
                )
            logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

            rows = self._sec_client.get_cash_flow(symbol, period=self.period)
            if not rows:
                raise RuntimeError(
                    f"[CASH_FLOW] No {self.period} cash flow data found for {symbol} (CIK={cik}). "
                    "Cannot load fundamentals without cash flow data."
                )
            logger.info("%s: Fetched %d %s cash flow row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = [r for r in rows if r.get("fiscal_year", 0) > since_year]
            if len(filtered) < len(rows):
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows)"
                )
            if not filtered:
                raise RuntimeError(
                    f"[CASH_FLOW] No new cash flow data for {symbol} after watermark (since {since}). "
                    "Cannot proceed with empty incremental load."
                )
            return filtered
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {e}. Cannot proceed without fundamental data."
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
                quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
                quarter_value = row["fiscal_quarter"]
                if quarter_value not in quarter_map:
                    raise ValueError(
                        f"Invalid fiscal_quarter value '{quarter_value}' for {r.get('symbol')}. "
                        f"Expected one of {list(quarter_map.keys())}"
                    )
                row["fiscal_quarter"] = quarter_map[quarter_value]
            # Calculate free_cash_flow: OCF - CapEx (both required)
            if "free_cash_flow" in self._schema_cols:
                ocf = row.get("operating_cash_flow")
                if ocf is not None and capex is not None:
                    row["free_cash_flow"] = ocf - capex
                elif ocf is not None and capex is None:
                    raise ValueError(
                        f"CapEx data missing for {r.get('symbol')} fiscal_year {r.get('fiscal_year')} — "
                        "Cannot calculate FCF without capital expenditure data (FCF ≠ OCF)"
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

        # Reject rows where all key cash flow fields are NULL
        cash_fields = [
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ]
        if all(row.get(field) is None for field in cash_fields):
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(CashFlowLoader))
