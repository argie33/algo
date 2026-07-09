#!/usr/bin/env python3
"""Annual Balance Sheet Loader - SEC EDGAR filing data.

Loads annual balance sheet data from SEC EDGAR using consolidated statements (10-K filings).
Extracts key metrics: total assets, current assets, liabilities, stockholders equity, etc.

Run:
    python3 load_balance_sheet.py [--symbols AAPL,MSFT] [--parallelism 2]
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
                        "data_unavailable",
                        "reason",
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
                        "data_unavailable",
                        "reason",
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
        """Fetch balance sheet data with exception handling.

        Re-raises fetch errors to maintain fail-fast semantics.
        Caller (load_incremental) is responsible for handling fetch failures per-symbol.
        """
        try:
            return super().fetch_incremental(symbol, since)
        except Exception as e:
            logger.error(f"[BALANCE_SHEET] Failed to fetch balance sheet for {symbol}: {type(e).__name__}: {e}")
            raise RuntimeError(
                f"[BALANCE_SHEET] Cannot fetch balance sheet for {symbol}: {type(e).__name__}: {str(e)[:200]}"
            ) from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format with exception handling and data_unavailable markers.

        - Adds data_unavailable=FALSE and reason=NULL to successful fetches
        - Preserves data_unavailable/reason from marker rows returned by fetch_incremental
        - Re-raises transform errors to maintain fail-fast semantics
        """
        try:
            transformed = super().transform(rows)
        except Exception as e:
            logger.error(f"[BALANCE_SHEET] Failed to transform balance sheet data: {type(e).__name__}: {e}")
            symbol = rows[0].get("symbol", "unknown") if rows else "unknown"
            raise RuntimeError(
                f"[BALANCE_SHEET] Cannot transform balance sheet data for {symbol}: {type(e).__name__}: {str(e)[:200]}"
            ) from e

        # Build map of input rows by key to preserve data_unavailable/reason from marker rows
        input_map: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")
            if self.period == "annual":
                if symbol and fiscal_year is not None:
                    input_map[(symbol, fiscal_year)] = row
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                if symbol and fiscal_year is not None and fiscal_quarter is not None:
                    input_map[(symbol, fiscal_year, fiscal_quarter)] = row

        # Ensure all rows have data_unavailable and reason columns
        for row in transformed:
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")

            # Build key to look up in input map
            key: tuple[Any, ...] | None
            if self.period == "annual":
                key = (symbol, fiscal_year) if symbol and fiscal_year is not None else None
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                key = (
                    (symbol, fiscal_year, fiscal_quarter)
                    if symbol and fiscal_year is not None and fiscal_quarter is not None
                    else None
                )

            if "data_unavailable" not in row:
                # Check if input row had data_unavailable (marker row from fetch)
                if key and key in input_map and "data_unavailable" in input_map[key]:
                    # Preserve marker data from input
                    row["data_unavailable"] = input_map[key]["data_unavailable"]
                    row["reason"] = input_map[key].get("reason")
                else:
                    # Successful fetch - mark data as available
                    row["data_unavailable"] = False
                    row["reason"] = None

        return transformed

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(run_loader(AnnualBalanceSheetLoader))
