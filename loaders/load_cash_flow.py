#!/usr/bin/env python3
"""Annual Cash Flow Statement Loader - SEC EDGAR filing data.

Loads annual cash flow statement data from SEC EDGAR using consolidated statements (10-K filings).
Extracts key metrics: operating cash flow, investing cash flow, financing cash flow, free cash flow.

Run:
    python3 load_cash_flow.py [--symbols AAPL,MSFT] [--parallelism 2]
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from loaders.sec_edgar_statement_loader import SecEdgarStatementLoader  # noqa: E402

logger = logging.getLogger(__name__)


class AnnualCashFlowLoader(SecEdgarStatementLoader):
    """Load annual cash flow statements from SEC EDGAR 10-K filings.

    Inherits from SecEdgarStatementLoader which handles:
    - Symbol-to-CIK conversion via SEC ticker cache
    - Rate limiting (8 req/sec per loader instance)
    - Watermark filtering (fiscal_year > last loaded year)
    - Data unavailability markers for companies without SEC data (REITs, IPOs, OTC)
    - Explicit data_unavailable=FALSE/TRUE + reason field population
    """

    def __init__(self, backfill_days: int | None = None):
        """Initialize with cash flow statement configuration."""
        period_config = {
            "annual": {
                "table_name": "annual_cash_flow",
                "primary_key": ("symbol", "fiscal_year"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "operating_cash_flow",
                        "investing_cash_flow",
                        "financing_cash_flow",
                        "net_change_in_cash",
                        "free_cash_flow",
                        "capital_expenditures",
                        "created_at",
                        "data_unavailable",
                        "reason",
                    ]
                ),
                "field_mapping": {
                    "operating_cash_flow": "operating_cash_flow",
                    "cash_from_operations": "operating_cash_flow",
                    "cash_flow_from_operations": "operating_cash_flow",
                    "net_cash_provided_by_operating_activities": "operating_cash_flow",
                    "investing_cash_flow": "investing_cash_flow",
                    "cash_from_investing": "investing_cash_flow",
                    "cash_flow_from_investing": "investing_cash_flow",
                    "net_cash_used_in_investing_activities": "investing_cash_flow",
                    "financing_cash_flow": "financing_cash_flow",
                    "cash_from_financing": "financing_cash_flow",
                    "cash_flow_from_financing": "financing_cash_flow",
                    "net_cash_used_in_financing_activities": "financing_cash_flow",
                    "net_change_in_cash": "net_change_in_cash",
                    "net_increase_decrease_in_cash": "net_change_in_cash",
                    "free_cash_flow": "free_cash_flow",
                    "fcf": "free_cash_flow",
                    "capital_expenditures": "capital_expenditures",
                    "capex": "capital_expenditures",
                    "purchases_of_property_plant_equipment": "capital_expenditures",
                },
            },
            "quarterly": {
                "table_name": "quarterly_cash_flow",
                "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "fiscal_quarter",
                        "operating_cash_flow",
                        "investing_cash_flow",
                        "financing_cash_flow",
                        "net_change_in_cash",
                        "free_cash_flow",
                        "capital_expenditures",
                        "created_at",
                        "data_unavailable",
                        "reason",
                    ]
                ),
                "field_mapping": {
                    "operating_cash_flow": "operating_cash_flow",
                    "cash_from_operations": "operating_cash_flow",
                    "cash_flow_from_operations": "operating_cash_flow",
                    "net_cash_provided_by_operating_activities": "operating_cash_flow",
                    "investing_cash_flow": "investing_cash_flow",
                    "cash_from_investing": "investing_cash_flow",
                    "cash_flow_from_investing": "investing_cash_flow",
                    "net_cash_used_in_investing_activities": "investing_cash_flow",
                    "financing_cash_flow": "financing_cash_flow",
                    "cash_from_financing": "financing_cash_flow",
                    "cash_flow_from_financing": "financing_cash_flow",
                    "net_cash_used_in_financing_activities": "financing_cash_flow",
                    "net_change_in_cash": "net_change_in_cash",
                    "net_increase_decrease_in_cash": "net_change_in_cash",
                    "free_cash_flow": "free_cash_flow",
                    "fcf": "free_cash_flow",
                    "capital_expenditures": "capital_expenditures",
                    "capex": "capital_expenditures",
                    "purchases_of_property_plant_equipment": "capital_expenditures",
                },
            },
        }

        super().__init__(
            statement_type="cash_flow",
            period_config=period_config,
            period=None,  # Resolved from LOADER_PERIOD env var
        )
        self.backfill_days = backfill_days

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch annual cash flow data. Delegates to base class."""
        return super().fetch_incremental(symbol, since)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format and add data_unavailable markers.

        Delegates to base class for field mapping, then ensures all rows have
        data_unavailable and reason columns set appropriately.
        """
        transformed = super().transform(rows)

        # Ensure all rows have data_unavailable and reason columns
        # For rows already marked with data_unavailable=True (e.g., REITs without SEC data),
        # keep those markers. For all other rows, set data_unavailable=FALSE and reason=NULL
        # to indicate successful data population.
        for row in transformed:
            if "data_unavailable" not in row:
                row["data_unavailable"] = False
            if "reason" not in row and row.get("data_unavailable") is False:
                row["reason"] = None

        return transformed

    def load_symbol(self, symbol: str) -> int:
        """Load data for a symbol, with explicit error handling for data_unavailable markers.

        Wraps parent load_symbol to catch ANY exception and insert marker row with:
        - data_unavailable=TRUE
        - reason=<error_description>

        This ensures that when a symbol fails to load due to API errors, network issues,
        or data processing errors, we insert an explicit marker row so downstream consumers
        know that data was unavailable (not just missing/skipped).
        """
        try:
            # Call parent's load_symbol which handles fetch, transform, validate, insert
            return super().load_symbol(symbol)
        except Exception as e:
            # On ANY error, insert a marker row with data_unavailable=TRUE
            error_msg = str(e)[:500]  # Truncate to VARCHAR(500) limit
            logger.error(
                f"[{self.table_name}] {symbol}: Load failed with exception, inserting data_unavailable marker. "
                f"Error: {error_msg}"
            )

            try:
                # Build marker row with data_unavailable=TRUE
                # Use fiscal_year=0 as sentinel (not a real fiscal year) to indicate failure marker
                marker_row = {
                    "symbol": symbol,
                    "fiscal_year": 0,
                    "data_unavailable": True,
                    "reason": error_msg,
                }

                # Insert the marker row via bulk insert
                inserted = self._bulk_insert_mgr.bulk_insert([marker_row])
                logger.info(
                    f"[{self.table_name}] {symbol}: Inserted data_unavailable marker (fiscal_year=0). "
                    f"Rows inserted: {inserted}"
                )

                # Still count this as a failed symbol for stats
                self._stats.increment("symbols_failed")
                # Re-raise original error after inserting marker; caller must know load failed
                raise
            except Exception as marker_err:
                # If we can't even insert the marker, log and re-raise original error
                logger.error(
                    f"[{self.table_name}] {symbol}: CRITICAL - Could not insert data_unavailable marker: {marker_err}. "
                    f"Original error was: {error_msg}"
                )
                self._stats.increment("symbols_failed")
                raise

    def run(self, symbols, parallelism: int = 1, backfill_days: int | None = None):
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    run_loader(AnnualCashFlowLoader, sys.argv[1:])
