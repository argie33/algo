#!/usr/bin/env python3
"""Annual Income Statement Loader - SEC EDGAR filing data.

Loads annual income statement data from SEC EDGAR using consolidated statements (10-K filings).
Extracts key metrics: revenue, cost of revenue, gross profit, operating income, net income, EPS.

Run:
    python3 load_income_statement.py [--symbols AAPL,MSFT] [--parallelism 2]
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


class AnnualIncomeStatementLoader(SecEdgarStatementLoader):
    """Load annual income statements from SEC EDGAR 10-K filings.

    Inherits from SecEdgarStatementLoader which handles:
    - Symbol-to-CIK conversion via SEC ticker cache
    - Rate limiting (8 req/sec per loader instance)
    - Watermark filtering (fiscal_year > last loaded year)
    - Data unavailability markers for companies without SEC data (REITs, IPOs, OTC)
    """

    def __init__(self, backfill_days: int | None = None):
        """Initialize with income statement configuration."""
        period_config = {
            "annual": {
                "table_name": "annual_income_statement",
                "primary_key": ("symbol", "fiscal_year"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "revenue",
                        "cost_of_revenue",
                        "gross_profit",
                        "operating_income",
                        "net_income",
                        "earnings_per_share",
                        "created_at",
                    ]
                ),
                "field_mapping": {
                    "revenue": "revenue",
                    "cost_of_goods_sold": "cost_of_revenue",
                    "cost_of_revenue": "cost_of_revenue",
                    "gross_profit": "gross_profit",
                    "operating_income": "operating_income",
                    "income_from_operations": "operating_income",
                    "net_income": "net_income",
                    "net_income_loss": "net_income",
                    "earnings_per_share_basic": "earnings_per_share",
                    "earnings_per_share": "earnings_per_share",
                    "eps": "earnings_per_share",
                },
            },
            "quarterly": {
                "table_name": "quarterly_income_statement",
                "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
                "schema_cols": frozenset(
                    [
                        "symbol",
                        "fiscal_year",
                        "fiscal_quarter",
                        "revenue",
                        "cost_of_revenue",
                        "gross_profit",
                        "operating_income",
                        "net_income",
                        "earnings_per_share",
                        "created_at",
                    ]
                ),
                "field_mapping": {
                    "revenue": "revenue",
                    "cost_of_goods_sold": "cost_of_revenue",
                    "cost_of_revenue": "cost_of_revenue",
                    "gross_profit": "gross_profit",
                    "operating_income": "operating_income",
                    "income_from_operations": "operating_income",
                    "net_income": "net_income",
                    "net_income_loss": "net_income",
                    "earnings_per_share_basic": "earnings_per_share",
                    "earnings_per_share": "earnings_per_share",
                    "eps": "earnings_per_share",
                },
            },
        }

        super().__init__(
            statement_type="income_statement",
            period_config=period_config,
            period=None,  # Resolved from LOADER_PERIOD env var
        )
        self.backfill_days = backfill_days

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch annual income statement data. Delegates to base class."""
        return super().fetch_incremental(symbol, since)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format. Delegates to base class."""
        return super().transform(rows)

    def run(self, symbols, parallelism: int = 1, backfill_days: int | None = None):
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    run_loader(AnnualIncomeStatementLoader, sys.argv[1:])
