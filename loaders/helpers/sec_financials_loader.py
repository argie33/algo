#!/usr/bin/env python3
"""SecFinancialsLoader - Pattern B SEC data reader (metrics computation).

EXTRACTED from sec_base.py 2026-09-17 (file-size ratchet: sec_base.py hit the 2000-line hard
ceiling after the AUID/AVA concept-priority fixes). Pure extraction, no behavior change -
SecFinancialsLoader is currently unused dead code (see .vulture_whitelist.py), kept intact
rather than deleted since it documents Pattern B (DB-table readers, as opposed to
SecEdgarStatementLoader's Pattern A direct-from-EDGAR fetch) for any future
load_quality_growth_metrics.py-style consumer - see sec_base.py's own module docstring for the
two-pattern overview.
"""

from typing import Any

from loaders.helpers.sec_base import SecLoaderBase, logger


class SecFinancialsLoader(SecLoaderBase):
    """Pattern B: Read SEC data from already-loaded DB tables (metrics computation).

    Used by: load_quality_growth_metrics.py
    Reads from annual_income_statement and annual_balance_sheet tables.
    """

    def _fetch_annual_income_statement(self, symbol: str) -> tuple[Any, Any, Any] | None:
        """Fetch latest annual income statement for a symbol.

        Returns:
            Tuple of (revenue, operating_income, net_income) or None if not available.
            All NaN Decimal values are cleaned to None.
        """
        from utils.loaders import fetch_one

        try:
            row = fetch_one(
                """
                SELECT revenue, operating_income, net_income
                FROM annual_income_statement
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY fiscal_year DESC
                LIMIT 1
            """,
                (symbol,),
            )
            if row:
                return self._clean_row(row)
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
        """
        from utils.loaders import fetch_one

        try:
            row = fetch_one(
                """
                SELECT total_assets, stockholders_equity, current_assets,
                       total_liabilities, current_liabilities, inventory
                FROM annual_balance_sheet
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY fiscal_year DESC
                LIMIT 1
            """,
                (symbol,),
            )
            if row:
                return self._clean_row(row)
            logger.debug(
                f"[{self.table_name}] No annual balance sheet for {symbol}: "
                "SEC filing data not available (micro-cap, OTC, ADR, new IPO, or non-US company)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch balance sheet for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch balance sheet for {symbol}: {e}") from e

    def _fetch_annual_income_statement_history(self, symbol: str, years: int = 10) -> list[tuple[Any, ...]] | None:
        """Fetch historical annual income statements for multi-year analysis.

        Args:
            symbol: Stock symbol
            years: Number of years to fetch (default 10 for 1Y/3Y/5Y lookback)

        Returns:
            List of tuples (revenue, operating_income, net_income, earnings_per_share) ordered by fiscal_year DESC.
            Omits fiscal_year to allow _compute_growth_metrics to treat row[0] as revenue (matching quality metrics).
            All NaN Decimal values are cleaned to None.
            Returns None if no data found.
        """
        from utils.loaders import execute_query

        try:
            rows = execute_query(
                f"""
                SELECT revenue, operating_income, net_income, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY fiscal_year DESC
                LIMIT {years}
            """,
                (symbol,),
            )
            if rows:
                return [self._clean_row(row) for row in rows]
            logger.debug(
                f"[{self.table_name}] No income statement history for {symbol}: "
                "SEC filing data not available or insufficient history (young company, new IPO, or lack of coverage)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch income statement history for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch income statement history for {symbol}: {e}") from e
