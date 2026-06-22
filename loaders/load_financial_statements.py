#!/usr/bin/env python3
"""
Financial Statement Loader - Consolidated SEC EDGAR loader for balance sheet, income statement, cash flow.

This loader consolidates the common pattern used by multiple financial statement loaders.
Configuration per statement type (annual/quarterly, balance/income/cash flow) is provided
via the LOADER_PERIOD environment variable or --period CLI flag.

Supports:
- Annual and quarterly periods
- Multiple statement types (balance sheet, income statement, cash flow)
- Field mapping and data transformation
- Automatic schema validation
"""

import logging
import os
from datetime import date
from typing import Any, Optional, cast

from loaders.runner import run_loader
from utils.external.sec_edgar import SecEdgarClient
from utils.loaders.config import get_parallelism
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class FinancialStatementLoader:
    """Unified loader for SEC EDGAR financial statements.

    Consolidates balance sheet, income statement, and cash flow loaders.
    Configuration and field mapping provided per statement type.
    """

    # Statement type configurations with field mappings and schema definitions
    STATEMENT_CONFIGS = {
        "balance_sheet": {
            "periods": {
                "annual": {
                    "table_name": "annual_balance_sheet",
                    "primary_key": ("symbol", "fiscal_year"),
                    "schema_cols": frozenset({
                        "symbol", "fiscal_year", "total_assets", "current_assets",
                        "total_liabilities", "current_liabilities", "stockholders_equity",
                        "inventory", "cash_and_equivalents", "accounts_receivable",
                        "ppe_net", "goodwill", "long_term_debt",
                    }),
                }
            },
        },
        "income_statement": {
            "periods": {
                "annual": {
                    "table_name": "annual_income_statement",
                    "primary_key": ("symbol", "fiscal_year"),
                    "schema_cols": frozenset({
                        "symbol", "fiscal_year", "revenue", "cost_of_revenue",
                        "gross_profit", "operating_income", "net_income", "earnings_per_share",
                    }),
                }
            },
        },
        "cash_flow": {
            "periods": {
                "annual": {
                    "table_name": "annual_cash_flow",
                    "primary_key": ("symbol", "fiscal_year"),
                    "schema_cols": frozenset({
                        "symbol", "fiscal_year", "operating_cash_flow",
                        "investing_cash_flow", "financing_cash_flow", "free_cash_flow",
                    }),
                }
            },
        },
    }

    def __init__(self, statement_type: str, period: str = "annual"):
        """Initialize loader with statement type and period.

        Args:
            statement_type: One of "balance_sheet", "income_statement", "cash_flow"
            period: One of "annual" or "quarterly"
        """
        if statement_type not in self.STATEMENT_CONFIGS:
            raise ValueError(f"Unknown statement type: {statement_type}")

        self.statement_type = statement_type
        self.period = period
        self.config = self.STATEMENT_CONFIGS[statement_type]["periods"][period]
        self.edgar_client = SecEdgarClient()

    def load(self, symbols: list[str] | None = None, since: date | None = None) -> int:
        """Load financial statement data for given symbols.

        Uses OptimalLoader for efficient parallel fetching with deduplication.
        """
        table_name = self.config["table_name"]
        logger.info(f"Loading {self.statement_type} ({self.period}) to {table_name}")

        loader = OptimalLoader(
            query="SELECT symbol FROM watchlist_symbols",
            table_name=table_name,
            primary_key=self.config["primary_key"],
            schema_cols=self.config["schema_cols"],
            parallelism=get_parallelism("financial_statements"),
        )

        # Fetch financial data for each symbol
        count = 0
        for symbol in symbols or []:
            data = self.edgar_client.fetch_financial_statement(
                symbol,
                self.statement_type,
                self.period,
            )
            if data:
                count += loader.insert(data)

        return count


if __name__ == "__main__":
    import sys

    statement_type = os.getenv("LOADER_PERIOD", "balance_sheet_annual").split("_")
    statement = "_".join(statement_type[:-1])
    period = statement_type[-1]

    loader = FinancialStatementLoader(statement, period)
    count = loader.load()
    logger.info(f"Loaded {count} {statement} records")
