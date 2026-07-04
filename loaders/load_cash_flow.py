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
        """Transform to schema format. Delegates to base class."""
        return super().transform(rows)

    def run(self, symbols, parallelism: int = 1, backfill_days: int | None = None):
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    run_loader(AnnualCashFlowLoader, sys.argv[1:])
