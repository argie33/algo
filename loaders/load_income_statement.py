#!/usr/bin/env python3
"""
Income Statement Loader - annual and quarterly from SEC EDGAR (single authoritative source).

Period determined by LOADER_PERIOD env var or --period CLI flag for manual runs.
"""

import logging
import os
import sys
from datetime import date, datetime
from typing import Any, cast

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.external import SecEdgarClient, sec_statements
from utils.optimal_loader import OptimalLoader

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


class IncomeStatementLoader(OptimalLoader):
    """Income statement loader from SEC EDGAR (official, authoritative source only)."""

    watermark_field = "fiscal_year"
    exclude_etfs_from_symbols = True
    _QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    def __init__(self, period: str | None = None):
        if period:
            self.period = period
        else:
            self.period = os.getenv("LOADER_PERIOD", "annual")

        if self.period not in ("annual", "quarterly"):
            raise ValueError(f"Invalid period: {self.period!r}; must be 'annual' or 'quarterly'")

        cfg = _PERIOD_CONFIG[self.period]
        self.table_name: str = cast(str, cfg["table_name"])
        self.primary_key: tuple[str, ...] = cast(tuple[str, ...], cfg["primary_key"])
        self._schema_cols: frozenset[str] = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping: dict[str, str] | None = cast(dict[str, str] | None, cfg.get("field_mapping"))

        super().__init__()
        self._sec_client = SecEdgarClient()

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
            raise RuntimeError(f"[INCOME_STATEMENT] Failed to query {self.table_name} for {symbol}: {e}") from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        try:
            rows = sec_statements.get_income_statement(self._sec_client, symbol, period=self.period)

            if not rows:
                raise RuntimeError(
                    f"[INCOME_STATEMENT] {symbol}: No {self.period} income statement data available in SEC EDGAR. "
                    f"SEC filing data is critical for financial analysis. Cannot proceed without income statement."
                )

            logger.info("%s: Fetched %d %s income statement row(s)", symbol, len(rows), self.period)

            # Use default year if since is None (initial load)
            since_year = int(since.year) if since else 2000

            # Also include years already in DB where revenue is NULL (backfill ASC 606 gaps)
            null_revenue_years = self._get_null_revenue_years(symbol)
            filtered = []
            for r in rows:
                if isinstance(r, dict):
                    fiscal_year = r.get("fiscal_year")
                    if fiscal_year and (fiscal_year > since_year or fiscal_year in null_revenue_years):
                        filtered.append(r)

            if len(filtered) < len(rows) or null_revenue_years:
                logger.info(
                    f"[INCOME_STATEMENT] {symbol}: Filtered {len(rows) - len(filtered)} row(s) "
                    f"(keeping {len(filtered)} newer rows; {len(null_revenue_years)} null-revenue years for backfill)"
                )

            return self.transform(filtered)
        except Exception as e:
            logger.error(f"[INCOME_STATEMENT] Failed to fetch income statement for {symbol}: {type(e).__name__}: {e}")
            raise RuntimeError(f"[INCOME_STATEMENT] Failed to fetch income statement for {symbol}: {e}") from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._field_mapping is None:
            raise RuntimeError(f"[{self.table_name}] Field mapping not initialized.")

        transformed = []
        skipped_invalid_fields = 0

        for r in rows:
            row: dict[str, Any] = {}
            # CRITICAL: Ensure symbol and fiscal_year are always preserved
            if "symbol" in r:
                row["symbol"] = r["symbol"]
            if "fiscal_year" in r:
                row["fiscal_year"] = r["fiscal_year"]

            for sec_field, value in r.items():
                # Skip fields we already handled above
                if sec_field in ("symbol", "fiscal_year"):
                    continue

                db_field = self._field_mapping.get(sec_field, sec_field)
                if db_field in self._schema_cols:
                    if db_field not in row or (row[db_field] is None and value is not None):
                        row[db_field] = value

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

        seen: dict[tuple[Any, ...], dict[str, Any]] = {}
        skipped_missing_keys = 0

        for row in transformed:
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")

            if not symbol:
                logger.warning(
                    f"[{self.table_name}] Row missing required 'symbol' field. Row keys: {list(row.keys())}. Skipping."
                )
                skipped_missing_keys += 1
                continue

            if fiscal_year is None:
                logger.warning(
                    f"[{self.table_name}] Row missing required 'fiscal_year' field for {symbol}. Row keys: {list(row.keys())}. Skipping."
                )
                skipped_missing_keys += 1
                continue

            if self.period == "annual":
                key: tuple[Any, ...] = (symbol, fiscal_year)
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                if fiscal_quarter is None:
                    logger.warning(f"[{self.table_name}] Row missing required 'fiscal_quarter'. Skipping.")
                    skipped_missing_keys += 1
                    continue
                key = (symbol, fiscal_year, fiscal_quarter)

            if key not in seen:
                seen[key] = row

        if not seen:
            logger.error(
                f"[{self.table_name}] CRITICAL: No valid rows after transformation. "
                f"Processed {len(transformed)} transformed rows, skipped {skipped_missing_keys} for missing keys, "
                f"{skipped_invalid_fields} for invalid fields."
            )
            raise RuntimeError(f"[{self.table_name}] CRITICAL: No valid rows after transformation.")

        if skipped_invalid_fields + skipped_missing_keys > 0:
            logger.warning(f"[{self.table_name}] Skipped {skipped_invalid_fields + skipped_missing_keys} rows.")

        now = datetime.now().isoformat()
        result = list(seen.values())
        for row in result:
            row["created_at"] = now

        return result

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate income statement-specific constraints."""
        # Fail-fast: symbol is required (primary key). No fallback to placeholder.
        if "symbol" not in row or not row["symbol"]:
            logger.warning(
                f"[{self.table_name}] Row missing required 'symbol' (primary key): {row}. Rejecting."
            )
            return False

        symbol = row["symbol"]

        if not super()._validate_row(row):
            logger.warning(f"[{self.table_name}] Row failed parent validation for symbol '{symbol}'.")
            return False

        fy = row.get("fiscal_year")
        if not fy or not (1990 < fy < 2100):
            logger.warning(
                f"[{self.table_name}] Row has invalid or missing fiscal_year for symbol '{symbol}'. "
                f"Expected 4-digit year between 1990 and 2100, got: {fy}."
            )
            return False

        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            logger.warning(
                f"[{self.table_name}] Quarterly row missing required 'fiscal_quarter' "
                f"for symbol '{symbol}' fiscal_year {fy}."
            )
            return False

        # Reject rows where all key financial fields are NULL
        financial_fields = ["gross_profit", "operating_income", "net_income", "cost_of_revenue"]
        if all(row.get(field) is None for field in financial_fields):
            logger.error(
                f"[{self.table_name}] Row has all critical financial fields NULL for symbol '{symbol}' "
                f"fiscal_year {fy}. This indicates incomplete data from SEC EDGAR. "
                f"Rejecting row — cannot trust incomplete financial data."
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(IncomeStatementLoader))
