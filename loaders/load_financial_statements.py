#!/usr/bin/env python3
"""Consolidated Financial Statements Loader - SEC EDGAR filing data.

Loads financial statements (income, balance sheet, cash flow) across all periods
(annual, quarterly, TTM) from SEC EDGAR using consolidated statements.

This consolidated loader replaces 8 separate loaders:
  - load_income_statement.py (annual/quarterly/ttm)
  - load_balance_sheet.py (annual/quarterly/ttm)
  - load_cash_flow.py (annual/quarterly/ttm)

The statement type and period are determined by environment variables set by terraform:
  LOADER_STATEMENT_TYPE: income, balance, or cashflow
  LOADER_PERIOD: annual, quarterly, or ttm

Run:
    python3 load_financial_statements.py
    (with LOADER_STATEMENT_TYPE and LOADER_PERIOD env vars set by terraform)

Or directly:
    LOADER_STATEMENT_TYPE=income LOADER_PERIOD=annual python3 load_financial_statements.py
"""

import os
import sys

from loaders.loader_helper import setup_imports
from loaders.timeout_config import configure_socket_timeout

setup_imports()

import logging  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from loaders.sec_edgar_statement_loader import SecEdgarStatementLoader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


def get_statement_config(statement_type: str, period: str) -> dict[str, Any]:
    """Return configuration for a specific statement type and period.

    Args:
        statement_type: 'income', 'balance', or 'cashflow'
        period: 'annual', 'quarterly', or 'ttm'

    Returns:
        Dict with table_name, primary_key, schema_cols, field_mapping
    """
    if statement_type == "income":
        return get_income_statement_config(period)
    elif statement_type == "balance":
        return get_balance_sheet_config(period)
    elif statement_type == "cashflow":
        return get_cash_flow_config(period)
    else:
        raise ValueError(f"Unknown statement type: {statement_type}")


def get_income_statement_config(period: str) -> dict[str, Any]:
    """Income statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
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
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "quarterly":
        return {
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
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_income_statement",
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "earnings_per_share",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")


def get_balance_sheet_config(period: str) -> dict[str, Any]:
    """Balance sheet configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
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
                    "stockholders_equity",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "quarterly":
        return {
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
                    "stockholders_equity",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_balance_sheet",
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")


def get_cash_flow_config(period: str) -> dict[str, Any]:
    """Cash flow statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
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
        }
    elif period == "quarterly":
        return {
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
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_cash_flow",
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
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
        }
    else:
        raise ValueError(f"Unknown period: {period}")


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(ConsolidatedFinancialStatementsLoader)
    except Exception as e:
        logger.error(
            f"[FINANCIAL_STATEMENTS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True
        )
        try:
            statement_type = os.environ.get("LOADER_STATEMENT_TYPE", "income")
            period = os.environ.get("LOADER_PERIOD", "annual")
            config = get_statement_config(statement_type, period)
            table_name = config["table_name"]

            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT {get_conflict_target(config["primary_key"])} DO UPDATE SET
                          data_unavailable = TRUE,
                          reason = EXCLUDED.reason,
                          updated_at = NOW()
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark {table_name} data unavailable: {mark_err}")
        return 1


def get_conflict_target(primary_key: tuple[str, ...]) -> str:
    """Generate SQL CONFLICT target from primary key tuple."""
    cols = ", ".join(primary_key)
    return f"({cols})"


class ConsolidatedFinancialStatementsLoader(SecEdgarStatementLoader):
    """Unified loader for all financial statements (income, balance, cashflow x annual/quarterly/ttm).

    Consolidates 8 separate loaders into one, parametrized by:
    - LOADER_STATEMENT_TYPE env var: 'income', 'balance', or 'cashflow'
    - LOADER_PERIOD env var: 'annual', 'quarterly', or 'ttm'

    This eliminates redundant ECS task definitions and reduces scheduler complexity.
    """

    def __init__(self, backfill_days: int | None = None):
        """Initialize with dynamic statement configuration from env vars."""
        statement_type = os.environ.get("LOADER_STATEMENT_TYPE", "income").lower()
        period = os.environ.get("LOADER_PERIOD", "annual").lower()

        logger.info(
            f"[FINANCIAL_STATEMENTS] Initializing: statement_type={statement_type}, period={period}"
        )

        config = get_statement_config(statement_type, period)
        self.table_name = config["table_name"]

        period_config = {period: config}

        super().__init__(
            statement_type=statement_type,
            period_config=period_config,
            period=period,
        )
        self.backfill_days = backfill_days

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch financial data for the configured statement type and period."""
        return super().fetch_incremental(symbol, since)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format and add data_unavailable/reason flags."""
        transformed = super().transform(rows)

        result = []
        for row in transformed:
            if row.get("data_unavailable") is True:
                result.append(row)
            else:
                row["data_unavailable"] = False
                row["reason"] = None
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
