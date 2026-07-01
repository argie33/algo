#!/usr/bin/env python3
"""
Cash Flow Loader - annual and quarterly from SEC EDGAR (single authoritative source).

Period determined by LOADER_PERIOD env var or --period CLI flag for manual runs.
"""

import logging
import os
import sys
from datetime import date, datetime
from typing import Any, cast

from loaders.runner import run_loader
from utils.external import SecEdgarClient
from utils.optimal_loader import OptimalLoader

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


def _resolve_period(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "annual")


class CashFlowLoader(OptimalLoader):
    """Cash flow loader from SEC EDGAR (official, authoritative source only)."""

    watermark_field = "fiscal_year"
    exclude_etfs_from_symbols = True

    def __init__(self, period: str | None = None):
        period = _resolve_period(period)
        if period not in ("annual", "quarterly"):
            raise ValueError(f"Invalid period: {period!r}; must be 'annual' or 'quarterly'")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name: str = cast(str, cfg["table_name"])
        self.primary_key: tuple[str, ...] = cast(tuple[str, ...], cfg["primary_key"])
        self._schema_cols: frozenset[str] = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping: dict[str, str] | None = cast(dict[str, str] | None, cfg.get("field_mapping"))
        super().__init__()
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        try:
            rows = self._sec_client.get_cash_flow(symbol, period=self.period)

            if not rows:
                logger.warning(
                    f"[CASH_FLOW] {symbol}: No {self.period} cash flow data in SEC EDGAR."
                )
                return []

            logger.info("%s: Fetched %d %s cash flow row(s)", symbol, len(rows), self.period)

            if since is None:
                raise ValueError(
                    f"Cash flow loader for {symbol} requires 'since' parameter for incremental loading."
                )

            since_year = int(since.year)
            filtered = []
            for r in rows:
                if isinstance(r, dict):
                    if "fiscal_year" not in r or r["fiscal_year"] is None:
                        logger.warning(
                            f"[CASH_FLOW] {symbol}: Row missing required 'fiscal_year' field. Skipping."
                        )
                        continue
                    if r["fiscal_year"] > since_year:
                        filtered.append(r)

            if len(filtered) < len(rows) and len(rows) > 0:
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year}"
                )

            return filtered
        except Exception as e:
            logger.error(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {type(e).__name__}: {e}"
            )
            raise RuntimeError(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {e}"
            ) from e

    def _process_single_row(self, r: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single cash flow row from SEC EDGAR data."""
        if self._field_mapping is None:
            raise RuntimeError(f"[{self.table_name}] Field mapping not initialized.")
        row: dict[str, Any] = {}
        capex_value = None

        for sec_field, value in r.items():
            db_field = self._field_mapping.get(sec_field, sec_field)
            if db_field == "capex":
                capex_value = value
            elif db_field in self._schema_cols:
                row[db_field] = value

        if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
            quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
            quarter_value = row["fiscal_quarter"]
            if quarter_value not in quarter_map:
                logger.error(
                    f"[{self.table_name}] Invalid fiscal_quarter value '{quarter_value}' for {r.get('symbol')}."
                )
                return None
            row["fiscal_quarter"] = quarter_map[quarter_value]

        if "free_cash_flow" in self._schema_cols:
            ocf = row.get("operating_cash_flow")
            if ocf is not None and capex_value is not None:
                row["free_cash_flow"] = ocf - capex_value

        return row

    def transform(self, rows: Any) -> list[dict[str, Any]]:
        if self._field_mapping is None:
            raise RuntimeError(f"[{self.table_name}] Field mapping not initialized.")

        transformed = []
        for r in rows:
            row = self._process_single_row(r)
            if row is not None:
                transformed.append(row)

        seen = {}
        for row in transformed:
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")
            if symbol is None or fiscal_year is None:
                logger.error(
                    "[CASH_FLOW] Cannot build primary key: symbol=%s, fiscal_year=%s",
                    symbol,
                    fiscal_year,
                )
                raise ValueError(
                    f"Cash flow row missing required key fields. Symbol: {symbol}, Fiscal Year: {fiscal_year}."
                )
            if self.period == "annual":
                key: tuple[Any, ...] = (symbol, fiscal_year)
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                if fiscal_quarter is None:
                    logger.error(
                        "[CASH_FLOW] Quarterly record missing fiscal_quarter: symbol=%s, fiscal_year=%s",
                        symbol,
                        fiscal_year,
                    )
                    raise ValueError(
                        f"Quarterly cash flow row missing fiscal_quarter. Symbol: {symbol}, Fiscal Year: {fiscal_year}."
                    )
                key = (symbol, fiscal_year, fiscal_quarter)
            if key not in seen:
                seen[key] = row

        now = datetime.now().isoformat()
        result = list(seen.values())
        for row in result:
            row["created_at"] = now
        return result

    def _validate_row(self, row: dict[str, Any]) -> bool:
        if not super()._validate_row(row):
            raise ValueError(f"Cash flow row failed base validation: {row}")

        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            raise ValueError(f"Cash flow row has invalid fiscal_year={fy}: {row}")

        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            raise ValueError(f"Quarterly cash flow row missing fiscal_quarter: {row}")

        cash_fields = ["operating_cash_flow", "investing_cash_flow", "financing_cash_flow"]
        if all(row.get(field) is None for field in cash_fields):
            raise ValueError(f"Cash flow row has all NULL cash flow fields: {row}")

        return True


if __name__ == "__main__":
    sys.exit(run_loader(CashFlowLoader))
