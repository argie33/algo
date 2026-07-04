#!/usr/bin/env python3
"""Annual Balance Sheet Loader - SEC EDGAR filing data.

Loads annual balance sheet data from SEC EDGAR using consolidated statements (10-K filings).
Extracts key metrics: total assets, current assets, liabilities, stockholders equity, etc.

Run:
    python3 load_balance_sheet.py [--symbols AAPL,MSFT] [--parallelism 2]
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


class AnnualBalanceSheetLoader(SecEdgarStatementLoader):
    """Load annual balance sheets from SEC EDGAR 10-K filings.

    Inherits from SecEdgarStatementLoader which handles:
    - Symbol-to-CIK conversion via SEC ticker cache
    - Rate limiting (8 req/sec per loader instance)
    - Watermark filtering (fiscal_year > last loaded year)
    - Data unavailability markers for companies without SEC data (REITs, IPOs, OTC)
    """

    def __init__(self, backfill_days: int | None = None):
        """Initialize with balance sheet configuration."""
        period_config = {
            "annual": {
                "table_name": "annual_balance_sheet",
                "primary_key": ("symbol", "fiscal_year"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "total_assets",
                        "current_assets",
                        "total_liabilities",
                        "current_liabilities",
                        "long_term_debt",
                        "stockholders_equity",
                        "cash_and_equivalents",
                        "accounts_receivable",
                        "inventory",
                        "ppe_net",
                        "goodwill",
                        "created_at",
                    ]
                ),
                "field_mapping": {
                    "total_assets": "total_assets",
                    "assets": "total_assets",
                    "current_assets": "current_assets",
                    "total_liabilities": "total_liabilities",
                    "liabilities": "total_liabilities",
                    "current_liabilities": "current_liabilities",
                    "long_term_debt": "long_term_debt",
                    "long_term_borrowings": "long_term_debt",
                    "debt": "long_term_debt",
                    "stockholders_equity": "stockholders_equity",
                    "shareholders_equity": "stockholders_equity",
                    "equity": "stockholders_equity",
                    "total_equity": "stockholders_equity",
                    "cash": "cash_and_equivalents",
                    "cash_and_equivalents": "cash_and_equivalents",
                    "cash_and_cash_equivalents": "cash_and_equivalents",
                    "accounts_receivable": "accounts_receivable",
                    "receivables": "accounts_receivable",
                    "inventory": "inventory",
                    "ppe_net": "ppe_net",
                    "property_plant_equipment": "ppe_net",
                    "property_plant_equipment_net": "ppe_net",
                    "goodwill": "goodwill",
                },
            },
            "quarterly": {
                "table_name": "quarterly_balance_sheet",
                "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "fiscal_quarter",
                        "total_assets",
                        "current_assets",
                        "total_liabilities",
                        "current_liabilities",
                        "long_term_debt",
                        "stockholders_equity",
                        "cash_and_equivalents",
                        "accounts_receivable",
                        "inventory",
                        "ppe_net",
                        "goodwill",
                        "created_at",
                    ]
                ),
                "field_mapping": {
                    "total_assets": "total_assets",
                    "assets": "total_assets",
                    "current_assets": "current_assets",
                    "total_liabilities": "total_liabilities",
                    "liabilities": "total_liabilities",
                    "current_liabilities": "current_liabilities",
                    "long_term_debt": "long_term_debt",
                    "long_term_borrowings": "long_term_debt",
                    "debt": "long_term_debt",
                    "stockholders_equity": "stockholders_equity",
                    "shareholders_equity": "stockholders_equity",
                    "equity": "stockholders_equity",
                    "total_equity": "stockholders_equity",
                    "cash": "cash_and_equivalents",
                    "cash_and_equivalents": "cash_and_equivalents",
                    "cash_and_cash_equivalents": "cash_and_equivalents",
                    "accounts_receivable": "accounts_receivable",
                    "receivables": "accounts_receivable",
                    "inventory": "inventory",
                    "ppe_net": "ppe_net",
                    "property_plant_equipment": "ppe_net",
                    "property_plant_equipment_net": "ppe_net",
                    "goodwill": "goodwill",
                },
            },
        }

        super().__init__(
            statement_type="balance_sheet",
            period_config=period_config,
            period=None,  # Resolved from LOADER_PERIOD env var
        )
        self.backfill_days = backfill_days

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch annual balance sheet data. Delegates to base class."""
        return super().fetch_incremental(symbol, since)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format. Delegates to base class."""
        return super().transform(rows)

    def run(self, symbols, parallelism: int = 1, backfill_days: int | None = None):
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    run_loader(AnnualBalanceSheetLoader, sys.argv[1:])
