#!/usr/bin/env python3
import sys

"""
Cash Flow Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_cashflow / financials_quarterly_cashflow)
or --period CLI flag for manual runs.
"""

import logging  # noqa: E402

logger = logging.getLogger(__name__)
import os  # noqa: E402
from datetime import date, datetime  # noqa: E402
from typing import Any, cast  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.data.source_router import DataSourceRouter  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

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
    """Cash flow loader with multi-source support for real stocks only (not ETFs/bonds).

    Data sources (in priority order):
    1. SEC EDGAR (preferred - official, most complete)
    2. yfinance (fallback for stocks without SEC filings - REITs, micro-caps, etc.)

    Uses DataSourceRouter to handle automatic fallback when SEC EDGAR returns no data.
    """

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
        self._router = DataSourceRouter()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch cash flow data from multi-source (SEC EDGAR + yfinance fallback)."""
        try:
            rows = self._router.fetch_cash_flow(symbol, period=self.period)

            if not rows:
                logger.warning(
                    f"[CASH_FLOW] {symbol}: No {self.period} cash flow data from any source "
                    f"(SEC EDGAR + yfinance). Stock may lack SEC filings and yfinance data."
                )
                return []

            # Handle data_unavailable marker
            if isinstance(rows, dict) and rows.get("data_unavailable") is True:
                logger.info(
                    f"[CASH_FLOW] {symbol}: {rows.get('reason', 'Data unavailable from all sources')}. "
                    f"Stock may be micro-cap, REIT, or lack financial data."
                )
                return []

            if not isinstance(rows, list):
                rows = [rows] if rows else []

            logger.info("%s: Fetched %d %s cash flow row(s)", symbol, len(rows), self.period)

            if since is None:
                raise ValueError(
                    f"Cash flow loader for {symbol} requires 'since' parameter for incremental loading. "
                    f"Cannot load full historical data in incremental mode."
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
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows)"
                )

            if not filtered and len(rows) > 0:
                logger.info(
                    "[CASH_FLOW] %s: No new cash flow rows after incremental filter (since %s). "
                    "All rows have fiscal_year <= %s.",
                    symbol,
                    since,
                    since_year,
                )

            return filtered
        except Exception as e:
            logger.error(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {type(e).__name__}: {e}"
            )
            raise RuntimeError(
                f"[CASH_FLOW] Failed to fetch cash flow for {symbol}: {e}. Cannot proceed without fundamental data."
            ) from e

    def _process_single_row(self, r: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single cash flow row from raw data to schema format."""
        row: dict[str, Any] = {}
        capex_value = None
        field_mapping = self._field_mapping

        # Handle both SEC EDGAR dicts and yfinance dicts
        fields_to_process = r.items()
        if len(r) == 1:
            inner_value = next(iter(r.values()))
            if isinstance(inner_value, dict):
                # Likely yfinance format: {date_or_period: {field: value, ...}}
                fields_to_process = inner_value.items()
            # Try to extract fiscal_year from the date key
            for key_val in r.keys():
                if isinstance(key_val, str) and len(key_val) >= 4:
                    try:
                        r["fiscal_year"] = int(key_val[-4:])
                    except (ValueError, TypeError):
                        pass

        for sec_field, value in fields_to_process:
            # Apply field mapping first
            db_field = field_mapping.get(sec_field, sec_field)
            if db_field == "capex":
                capex_value = value
            elif db_field in self._schema_cols:
                row[db_field] = value

        if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
            quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
            quarter_value = row["fiscal_quarter"]
            if quarter_value not in quarter_map:
                logger.error(
                    f"[{self.table_name}] Invalid fiscal_quarter value '{quarter_value}' for {r.get('symbol')}. "
                    f"Expected one of {list(quarter_map.keys())}"
                )
                return None
            row["fiscal_quarter"] = quarter_map[quarter_value]

        # Calculate free_cash_flow: OCF - CapEx (both required; omit FCF if capex missing)
        if "free_cash_flow" in self._schema_cols:
            ocf = row.get("operating_cash_flow")
            if ocf is not None and capex_value is not None:
                row["free_cash_flow"] = ocf - capex_value
            elif ocf is not None and capex_value is None:
                logger.warning(
                    "[CASH_FLOW] Free cash flow cannot be calculated: capex missing for %s FY%s. "
                    "Using only operating cash flow.",
                    row.get("symbol"),
                    row.get("fiscal_year"),
                )
        return row

    def transform(self, rows: Any) -> list[dict[str, Any]]:
        if self._field_mapping is None:
            raise RuntimeError(
                f"[{self.table_name}] Field mapping not initialized. "
                f"Configuration missing 'field_mapping' key. "
                f"Cannot transform cash flow data without field mapping rules."
            )
        transformed = []
        for r in rows:
            row = self._process_single_row(r)
            if row is not None:
                transformed.append(row)

        seen = {}
        for row in transformed:
            key: tuple[Any, ...]
            # Validate required key fields before building key tuple
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")
            if symbol is None or fiscal_year is None:
                logger.error(
                    "[CASH_FLOW] Cannot build primary key: symbol=%s, fiscal_year=%s. "
                    "Row missing required key fields: %s",
                    symbol,
                    fiscal_year,
                    row,
                )
                raise ValueError(
                    f"Cash flow row missing required key fields. Symbol: {symbol}, Fiscal Year: {fiscal_year}. "
                    f"Cannot deduplicate records without complete primary key."
                )
            if self.period == "annual":
                key = (symbol, fiscal_year)
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                if fiscal_quarter is None:
                    logger.error(
                        "[CASH_FLOW] Cannot build quarterly key: symbol=%s, fiscal_year=%s, fiscal_quarter=%s. "
                        "Quarterly record missing fiscal_quarter.",
                        symbol,
                        fiscal_year,
                        fiscal_quarter,
                    )
                    raise ValueError(
                        f"Quarterly cash flow row missing fiscal_quarter for deduplication. "
                        f"Symbol: {symbol}, Fiscal Year: {fiscal_year}. "
                        f"Cannot build complete primary key."
                    )
                key = (symbol, fiscal_year, fiscal_quarter)
            if key not in seen:
                seen[key] = row

        # Add created_at watermark for downstream loaders (growth_metrics, quality_metrics, etc.)
        now = datetime.now().isoformat()
        result = list(seen.values())
        for row in result:
            row["created_at"] = now
        return result

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

        # Validate key cash flow fields and log missing HIGH-priority financial data
        cash_fields = [
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ]
        missing_fields = [field for field in cash_fields if row.get(field) is None]

        if all(row.get(field) is None for field in cash_fields):
            raise ValueError(
                f"Cash flow row has all NULL cash flow fields: {row}. "
                f"At least one of operating_cash_flow, investing_cash_flow, financing_cash_flow must be present."
            )

        if missing_fields:
            logger.warning(
                "[CASH_FLOW] Missing HIGH-priority financial data for %s FY%s: %s. "
                "Proceeding with available cash flow data.",
                row.get("symbol"),
                row.get("fiscal_year"),
                missing_fields,
            )

        return True


if __name__ == "__main__":
    sys.exit(run_loader(CashFlowLoader))
