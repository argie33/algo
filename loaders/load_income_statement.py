#!/usr/bin/env python3
"""
Income Statement Loader - annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var or --period CLI flag for manual runs.

This loader uses the consolidated SecEdgarStatementLoader base class.
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

import psycopg2

from loaders.runner import run_loader
from loaders.sec_edgar_statement_loader import SecEdgarStatementLoader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_income_statement",
        "primary_key": ("symbol", "fiscal_year"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "revenue",
                "cost_of_revenue",
                "gross_profit",
                "operating_income",
                "net_income",
                "earnings_per_share",
            }
        ),
        "field_mapping": {
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
            "cost_of_revenue": "cost_of_revenue",
            "costs_and_expenses": "cost_of_revenue",
            "gross_profit": "gross_profit",
            "operating_expenses": "operating_expenses",
            "operating_income_loss": "operating_income",
            "net_income_loss": "net_income",
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
            "weighted_average_number_of_shares_outstanding_basic": "shares_outstanding",
        },
    },
    "quarterly": {
        "table_name": "quarterly_income_statement",
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "fiscal_quarter",
                "revenue",
                "net_income",
                "earnings_per_share",
            }
        ),
        "field_mapping": {
            "fiscal_period": "fiscal_quarter",
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
            "net_income_loss": "net_income",
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
        },
    },
}


class IncomeStatementLoader(SecEdgarStatementLoader):
    """SEC EDGAR income statement loader for real stocks only (not ETFs/bonds).

    Financial data from SEC EDGAR is only available for companies that file with the SEC.
    ETFs, bonds, and other securities don't have income statements, so we exclude them.
    """

    exclude_etfs_from_symbols = True
    _QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    def __init__(self, period: str | None = None):
        super().__init__("income_statement", _PERIOD_CONFIG, period)

    def _get_null_revenue_years(self, symbol: str) -> set[Any]:
        """Return fiscal years in the DB where revenue is NULL (need backfill)."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SELECT fiscal_year FROM {self.table_name} WHERE symbol = %s AND revenue IS NULL",
                    (symbol,),
                )
                return {row[0] for row in cur.fetchall()}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[INCOME_STATEMENT] Failed to query {self.table_name} for {symbol} (revenue=NULL check): {e}. "
                "Database error prevents incremental loading. Cannot proceed."
            ) from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch with special handling for revenue NULL backfill."""
        rows = super().fetch_incremental(symbol, since)

        if since is None:
            raise ValueError(
                f"Income statement loader for {symbol} requires 'since' parameter for incremental loading. "
                f"Cannot load full historical data in incremental mode."
            )

        # Also include years already in DB where revenue is NULL (backfill ASC 606 gaps)
        null_revenue_years = self._get_null_revenue_years(symbol)
        filtered = []
        for r in rows:
            fiscal_year = r.get("fiscal_year")
            if fiscal_year > int(since.year) or fiscal_year in null_revenue_years:
                filtered.append(r)

        if len(filtered) < len(rows) or null_revenue_years:
            logger.info(
                f"[INCOME_STATEMENT] {symbol}: Filtered {len(rows) - len(filtered)} row(s) "
                f"(watermark incremental load — keeping {len(filtered)} newer rows; "
                f"{len(null_revenue_years)} null-revenue years also included for backfill)"
            )

        if not filtered:
            logger.warning(
                f"[INCOME_STATEMENT] {symbol}: No income statement rows after incremental filtering. "
                f"Original fetch returned {len(rows)} row(s), but all were filtered by watermark."
            )

        return filtered

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform with special handling for multiple revenue concepts."""
        if self._field_mapping is None:
            raise RuntimeError(
                f"[{self.table_name}] Field mapping not initialized. "
                "Configuration missing 'field_mapping' key. "
                "Cannot transform SEC EDGAR data without field mapping rules."
            )

        transformed = []
        skipped_invalid_fields = 0

        # Apply field mapping with precedence for non-None values
        for r in rows:
            row: dict[str, Any] = {}
            field_mapping = self._field_mapping
            for sec_field, value in r.items():
                db_field = field_mapping.get(sec_field, sec_field)
                # Only keep fields in schema; prefer non-None values
                if db_field in self._schema_cols:
                    if db_field not in row or (row[db_field] is None and value is not None):
                        row[db_field] = value

            # Convert fiscal_quarter
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                quarter_str = row["fiscal_quarter"]
                quarter_num = self._QUARTER_MAP.get(quarter_str)
                if quarter_num is None:
                    logger.error(
                        f"[{self.table_name}] Invalid fiscal_quarter format. "
                        f"Expected Q1-Q4, found '{quarter_str}'. Skipping row."
                    )
                    skipped_invalid_fields += 1
                    continue
                row["fiscal_quarter"] = quarter_num

            transformed.append(row)

        # Call parent transform to handle deduplication and validation
        result = super().transform(transformed)

        # Add created_at watermark for downstream loaders
        now = datetime.now().isoformat()
        for row in result:
            row["created_at"] = now

        return result

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate income statement-specific constraints."""
        if not super()._validate_row(row):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(f"[{self.table_name}] Row failed parent validation for symbol '{symbol}'.")
            return False

        fy = row.get("fiscal_year")
        if not fy or not (1990 < fy < 2100):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Row has invalid or missing fiscal_year for symbol '{symbol}'. "
                f"Expected 4-digit year between 1990 and 2100, got: {fy}."
            )
            return False

        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Quarterly row missing required 'fiscal_quarter' "
                f"for symbol '{symbol}' fiscal_year {fy}."
            )
            return False

        # Reject rows where all key financial fields are NULL
        financial_fields = ["gross_profit", "operating_income", "net_income", "cost_of_revenue"]
        if all(row.get(field) is None for field in financial_fields):
            symbol = row.get("symbol", "UNKNOWN")
            logger.error(
                f"[{self.table_name}] Row has all critical financial fields NULL for symbol '{symbol}' "
                f"fiscal_year {fy}. This indicates incomplete data from SEC EDGAR. "
                f"Rejecting row — cannot trust incomplete financial data."
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(IncomeStatementLoader))
