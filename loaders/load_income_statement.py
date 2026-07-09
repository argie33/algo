#!/usr/bin/env python3
"""Annual Income Statement Loader - SEC EDGAR filing data.

Loads annual income statement data from SEC EDGAR using consolidated statements (10-K filings).
Extracts key metrics: revenue, cost of revenue, gross profit, operating income, net income, EPS.

Run:
    python3 load_income_statement.py [--symbols AAPL,MSFT] [--parallelism 2]
"""

import socket
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

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(AnnualIncomeStatementLoader)
    except Exception as e:
        logger.error(f"[INCOME_STATEMENT FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable for all symbols
        try:
            from utils.db.context import DatabaseContext

            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO annual_income_statement (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO UPDATE SET
                          data_unavailable = TRUE,
                          reason = EXCLUDED.reason,
                          updated_at = NOW()
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark annual_income_statement data unavailable: {mark_err}")
        return 1


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
                        "data_unavailable",
                        "reason",
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
                        "data_unavailable",
                        "reason",
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
        """Transform to schema format and add data_unavailable/reason flags.

        Adds explicit data_unavailable=False and reason=NULL to successful rows.
        Preserves data_unavailable=True markers from fetch_incremental for companies
        with no SEC data (REITs, investment trusts, IPOs, OTC stocks).
        """
        # Call parent transform to handle field mapping and validation
        transformed = super().transform(rows)

        # Add data_unavailable and reason fields to all rows
        result = []
        for row in transformed:
            # If row already has data_unavailable=True (marker from fetch_incremental),
            # preserve it with its reason
            if row.get("data_unavailable") is True:
                # Marker row: already has data_unavailable=True and reason set
                result.append(row)
            else:
                # Successful data row: add explicit data_unavailable=False and reason=NULL
                row["data_unavailable"] = False
                row["reason"] = None
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
