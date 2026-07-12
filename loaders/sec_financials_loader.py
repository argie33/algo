#!/usr/bin/env python3
"""SEC Financials Loader Base Class - Shared logic for quality and growth metrics.

Extracted common patterns:
- Annual income statement and balance sheet fetching
- NaN handling for Decimal values (SEC data quality issue)
- Schema healing with auto-column creation for unavailable_reason fields
- Data unavailability markers (explicit instead of silent fallbacks)
- ETF exclusion pattern (these loaders need real companies with SEC filings)

This base class eliminates ~200 lines of duplication across:
- load_quality_metrics.py
- load_growth_metrics.py
"""

import logging
from abc import abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any

from loaders.timeout_config import configure_socket_timeout
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class SecFinancialsLoader(OptimalLoader):
    """Base class for loaders requiring SEC financial data.

    Subclasses must set:
    - table_name: Target table (quality_metrics, growth_metrics, etc)
    - primary_key: Primary key fields
    - exclude_etfs_from_symbols: Should always be True (SEC data only for companies)
    - REQUIRED_COLUMNS: Schema columns to auto-create (with data types)

    Pattern: Loaders that depend on annual_income_statement and/or annual_balance_sheet
    need to handle:
    1. NaN Decimal values (common in SEC XBRL filings)
    2. Missing data markers (explicit data_unavailable, not silent None)
    3. Auto-healing incomplete schema (migrations may not create all columns)
    4. ETF exclusion (SEC filings don't exist for ETFs/bonds)
    """

    # Must be True: SEC filings only exist for companies, not ETFs/bonds
    exclude_etfs_from_symbols = True

    # Subclasses must define their own REQUIRED_COLUMNS
    REQUIRED_COLUMNS: dict[str, str] = {}

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        # Ensure schema is healed before loading
        self._ensure_schema_ready()

    @staticmethod
    def _clean_decimal(val: Any) -> Any:
        """Convert NaN Decimal values to None (SEC data quality issue).

        SEC XBRL filings often encode missing data as NaN Decimal values.
        This method normalizes them to None for easier downstream handling.

        Args:
            val: Value to clean (may be Decimal, None, or other type)

        Returns:
            None if val is a NaN Decimal, otherwise returns val unchanged
        """
        if isinstance(val, Decimal):
            if val.is_nan():
                return None
        return val

    @staticmethod
    def _clean_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
        """Clean all NaN Decimal values in a row.

        Args:
            row: Tuple of values from database query

        Returns:
            Tuple with all NaN Decimals converted to None
        """
        return tuple(SecFinancialsLoader._clean_decimal(v) for v in row)

    def _fetch_annual_income_statement(self, symbol: str) -> tuple[Any, Any, Any] | None:
        """Fetch latest annual income statement for a symbol.

        Returns:
            Tuple of (revenue, operating_income, net_income) or None if not available.
            All NaN Decimal values are cleaned to None.

        Data Unavailability Patterns:
            - None: No SEC filing data available (common for micro-caps, OTC, ADRs, new IPOs)
            - RuntimeError: Database connectivity or permission issue (fail-fast - re-raised)
        """
        from utils.loaders import fetch_one

        try:
            row = fetch_one(
                """
                SELECT revenue, operating_income, net_income
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """,
                (symbol,),
            )
            if row:
                return self._clean_row(row)
            # EXPLICIT: No SEC filing data for this symbol (not an error, expected for ~55% of symbols)
            logger.debug(
                f"[{self.table_name}] No annual income statement for {symbol}: "
                "SEC filing data not available (micro-cap, OTC, ADR, new IPO, or non-US company)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch income statement for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch income statement for {symbol}: {e}") from e

    def _fetch_annual_balance_sheet(self, symbol: str) -> tuple[Any, ...] | None:
        """Fetch latest annual balance sheet for a symbol.

        Returns:
            Tuple of (total_assets, stockholders_equity, current_assets,
                     total_liabilities, current_liabilities, inventory)
            or None if not available. All NaN Decimal values are cleaned to None.

        Data Unavailability Patterns:
            - None: No SEC filing data available (common for micro-caps, OTC, ADRs, new IPOs)
            - RuntimeError: Database connectivity or permission issue (fail-fast - re-raised)
        """
        from utils.loaders import fetch_one

        try:
            row = fetch_one(
                """
                SELECT total_assets, stockholders_equity, current_assets,
                       total_liabilities, current_liabilities, inventory
                FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """,
                (symbol,),
            )
            if row:
                return self._clean_row(row)
            # EXPLICIT: No SEC filing data for this symbol (not an error, expected for ~55% of symbols)
            logger.debug(
                f"[{self.table_name}] No annual balance sheet for {symbol}: "
                "SEC filing data not available (micro-cap, OTC, ADR, new IPO, or non-US company)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch balance sheet for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch balance sheet for {symbol}: {e}") from e

    def _fetch_annual_income_statement_history(self, symbol: str, years: int = 10) -> list[tuple[Any, Any, Any]] | None:
        """Fetch historical annual income statements for multi-year analysis.

        Args:
            symbol: Stock symbol
            years: Number of years to fetch (default 10 for 1Y/3Y/5Y lookback)

        Returns:
            List of tuples (fiscal_year, revenue, earnings_per_share) ordered by fiscal_year DESC.
            All NaN Decimal values are cleaned to None.
            Returns None if no data found.

        Data Unavailability Patterns:
            - None: No multi-year SEC filing history available (common for young companies or those without coverage)
            - RuntimeError: Database connectivity or permission issue (fail-fast - re-raised)
        """
        from utils.loaders import execute_query

        try:
            rows = execute_query(
                f"""
                SELECT fiscal_year, revenue, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT {years}
            """,
                (symbol,),
            )
            if rows:
                return [self._clean_row(row) for row in rows]
            # EXPLICIT: No multi-year SEC filing history for this symbol (not an error, expected for young companies)
            logger.debug(
                f"[{self.table_name}] No income statement history for {symbol}: "
                "SEC filing data not available or insufficient history (young company, new IPO, or lack of coverage)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch income statement history for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch income statement history for {symbol}: {e}") from e

    def _ensure_schema_ready(self) -> None:
        """Ensure all required columns exist, auto-creating if needed.

        CRITICAL FIX 2026-07-01: Auto-heals incomplete migrations.
        Some migrations may be incomplete, leaving required columns missing in RDS.
        This method creates missing columns on first loader run to prevent silent data loss
        when BulkInsertManager encounters columns not in DB schema.

        Subclasses must define REQUIRED_COLUMNS with data types:
            REQUIRED_COLUMNS = {
                "column_name": "VARCHAR(255)",
                "other_column": "DECIMAL(8, 4)",
            }
        """
        if not self.REQUIRED_COLUMNS:
            # No required columns defined, skip schema healing
            return

        from utils.db.context import DatabaseContext
        from utils.schema_healer import ensure_columns_exist

        try:
            with DatabaseContext("write") as cur:
                _all_exist, created = ensure_columns_exist(cur, self.table_name, self.REQUIRED_COLUMNS)
                if created:
                    logger.warning(
                        f"[{self.table_name}] Auto-healed {len(created)} missing columns: {created}. "
                        f"Migration may have been incomplete in this environment."
                    )
        except Exception as e:
            logger.error(f"[{self.table_name}] Schema healing failed: {e}")
            raise RuntimeError(f"[{self.table_name}] Cannot verify schema is ready: {e}") from e

    @abstractmethod
    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Subclasses must implement fetch_incremental.

        Should use _fetch_annual_income_statement, _fetch_annual_balance_sheet,
        and _fetch_annual_income_statement_history helper methods.
        """
        raise NotImplementedError("Subclass must implement fetch_incremental")

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Default transform: no transformation needed."""
        return rows
