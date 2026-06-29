#!/usr/bin/env python3
import sys

"""
Income Statement Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_income / financials_quarterly_income)
or --period CLI flag for manual runs.
"""

import logging  # noqa: E402

import psycopg2  # noqa: E402

logger = logging.getLogger(__name__)
import os  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any, cast  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.external.sec_edgar import SecEdgarClient  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_income_statement",
        "primary_key": ("symbol", "fiscal_year"),
        "edgar_period": "annual",
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
            # Revenue: legacy concepts (pre-ASC 606, before 2018)
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            # Revenue: post-ASC 606 concepts (2018+) used by most large-cap companies
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
            # Cost of Revenue
            "cost_of_revenue": "cost_of_revenue",
            "costs_and_expenses": "cost_of_revenue",
            # Gross Profit
            "gross_profit": "gross_profit",
            # Operating metrics
            "operating_expenses": "operating_expenses",
            "operating_income_loss": "operating_income",
            # Net Income
            "net_income_loss": "net_income",
            # EPS: prefer basic over diluted
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_diluted": "earnings_per_share",
            # Shares outstanding
            "weighted_average_number_of_shares_outstanding_basic": "shares_outstanding",
        },
    },
    "quarterly": {
        "table_name": "quarterly_income_statement",
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "edgar_period": "quarterly",
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
            "fiscal_period": "fiscal_quarter",  # "Q1".."Q4"  ->  integer (converted in transform)
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


def _resolve_period(cli_arg: str | None) -> str:
    """Resolve period from CLI arg or LOADER_PERIOD env var (not LOADER_TYPE)."""
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "annual")


class IncomeStatementLoader(OptimalLoader):
    """SEC EDGAR income statement loader for real stocks only (not ETFs/bonds).

    Financial data from SEC EDGAR is only available for companies that file with the SEC.
    ETFs, bonds, and other securities don't have income statements, so we exclude them.
    """

    watermark_field = "fiscal_year"
    exclude_etfs_from_symbols = True

    def __init__(self, period: str | None = None):
        period = _resolve_period(period)
        if period not in ("annual", "quarterly"):
            raise ValueError(f"Invalid period: {period!r}; must be 'annual' or 'quarterly'")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name = cast(str, cfg["table_name"])
        self.primary_key = cast(tuple[str, ...], cfg["primary_key"])
        self._edgar_period = cast(str, cfg["edgar_period"])
        self._schema_cols = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping = cast(dict[str, str] | None, cfg.get("field_mapping"))
        super().__init__()
        self._sec_client = SecEdgarClient()

    def _get_null_revenue_years(self, symbol: str) -> set[Any]:
        """Return fiscal years in the DB where revenue is NULL (need backfill)."""
        try:
            from utils.db.context import DatabaseContext

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
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError as e:
            raise RuntimeError(
                f"[INCOME_STATEMENT] {symbol}: CIK not found in SEC ticker cache. "
                "Cannot fetch income statement without SEC EDGAR CIK."
            ) from e
        if not cik:
            raise RuntimeError(
                f"[INCOME_STATEMENT] CIK resolution failed for {symbol}. "
                "Cannot fetch income statement data without CIK."
            )
        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)
        try:
            rows = self._sec_client.get_income_statement(symbol, period=self._edgar_period)
            if not rows:
                raise RuntimeError(
                    f"[INCOME_STATEMENT] {symbol}: No {self._edgar_period} income statement data in SEC EDGAR. "
                    "Cannot proceed without fundamental data."
                )
            logger.info(
                "%s: Fetched %d %s income statement row(s)",
                symbol,
                len(rows),
                self._edgar_period,
            )

            if since is None:
                raise ValueError(
                    f"Income statement loader for {symbol} requires 'since' parameter for incremental loading. "
                    f"Cannot load full historical data in incremental mode."
                )
            since_year = int(since.year)
            # Also include years already in DB where revenue is NULL (backfill ASC 606 gaps)
            null_revenue_years = self._get_null_revenue_years(symbol)
            filtered = []
            for r in rows:
                if "fiscal_year" not in r or r["fiscal_year"] is None:
                    raise ValueError(
                        f"Income statement row missing required 'fiscal_year' field: {r}. "
                        f"Cannot filter incremental data without fiscal_year."
                    )
                if r["fiscal_year"] > since_year or r["fiscal_year"] in null_revenue_years:
                    filtered.append(r)

            if len(filtered) < len(rows):
                logger.info(
                    f"[INCOME_STATEMENT] {symbol}: Filtered {len(rows) - len(filtered)} row(s) "
                    f"with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows; "
                    f"{len(null_revenue_years)} null-revenue years also included for backfill)"
                )
            if not filtered:
                logger.warning(
                    f"[INCOME_STATEMENT] {symbol}: No {self._edgar_period} income statement rows "
                    f"after incremental filtering (since={since_year}). "
                    f"Original fetch returned {len(rows)} row(s), but all were filtered by watermark."
                )
            return filtered
        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[INCOME_STATEMENT] SEC EDGAR error for {symbol}: {e}. "
                "API failure prevents data fetch. Cannot proceed."
            ) from e

    _QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    def transform(self, rows: Any) -> list[dict[str, Any]]:
        if self._field_mapping is None:
            raise RuntimeError(
                f"[{self.table_name}] Field mapping not initialized. "
                f"Configuration missing 'field_mapping' key. "
                f"Cannot transform SEC EDGAR data without field mapping rules."
            )
        transformed = []
        for r in rows:
            row: dict[str, Any] = {}
            field_mapping = self._field_mapping
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = field_mapping.get(sec_field, sec_field)
                # Only keep fields in schema
                if db_field in self._schema_cols:
                    # Prefer non-None: set if not yet set, or replace None with a real value.
                    # This handles multiple concepts mapping to the same column (e.g., legacy
                    # "Revenues" vs. post-ASC 606 "RevenueFromContractWithCustomer...").
                    if db_field not in row or (row[db_field] is None and value is not None):
                        row[db_field] = value
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                quarter_str = row["fiscal_quarter"]
                quarter_num = self._QUARTER_MAP.get(quarter_str)
                if quarter_num is None:
                    logger.error(
                        f"[{self.table_name}] Invalid fiscal_quarter format '%s'. "
                        f"Expected Q1-Q4, found '%s'. Skipping row.",
                        quarter_str,
                        quarter_str,
                    )
                    continue  # Skip this row instead of silently setting None
                row["fiscal_quarter"] = quarter_num
            transformed.append(row)

        seen = {}
        for row in transformed:
            key: tuple[Any, ...]
            symbol = row.get("symbol")
            fiscal_year = row.get("fiscal_year")

            if not symbol:
                logger.warning(
                    f"[{self.table_name}] Row missing required 'symbol' field. Row data: {row}. Skipping."
                )
                continue
            if fiscal_year is None:
                logger.warning(
                    f"[{self.table_name}] Row missing required 'fiscal_year' field for symbol '{symbol}'. "
                    f"Row data: {row}. Skipping."
                )
                continue

            if self.period == "annual":
                key = (symbol, fiscal_year)
            else:
                fiscal_quarter = row.get("fiscal_quarter")
                if fiscal_quarter is None:
                    logger.warning(
                        f"[{self.table_name}] Row missing required 'fiscal_quarter' field for symbol '{symbol}' "
                        f"fiscal_year {fiscal_year}. Row data: {row}. Skipping."
                    )
                    continue
                key = (symbol, fiscal_year, fiscal_quarter)

            if key not in seen:
                seen[key] = row

        if not seen:
            logger.warning(
                f"[{self.table_name}] No valid transformed rows after deduplication. "
                f"All rows were filtered due to missing required fields or validation failures."
            )

        return list(seen.values())

    def _validate_row(self, row: dict[str, Any]) -> bool:
        if not super()._validate_row(row):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Row failed parent validation for symbol '{symbol}'. "
                f"Row: {row}."
            )
            return False

        fy = row.get("fiscal_year")
        if not fy or not (1990 < fy < 2100):
            symbol = row.get("symbol", "UNKNOWN")
            logger.warning(
                f"[{self.table_name}] Row has invalid or missing fiscal_year for symbol '{symbol}'. "
                f"Expected 4-digit year between 1990 and 2100, got: {fy}."
            )
            return False

        if self.period == "quarterly":
            fiscal_quarter = row.get("fiscal_quarter")
            if fiscal_quarter is None:
                symbol = row.get("symbol", "UNKNOWN")
                logger.warning(
                    f"[{self.table_name}] Quarterly income statement row missing required 'fiscal_quarter' "
                    f"for symbol '{symbol}' fiscal_year {fy}."
                )
                return False

        # Reject rows where all key financial fields are NULL
        # (indicates API failure or no data available for this symbol/year)
        financial_fields = [
            "gross_profit",
            "operating_income",
            "net_income",
            "cost_of_revenue",
        ]
        if all(row.get(field) is None for field in financial_fields):
            symbol = row.get("symbol", "UNKNOWN")
            logger.error(
                f"[{self.table_name}] Row has all critical financial fields NULL for symbol '{symbol}' "
                f"fiscal_year {fy}. This indicates incomplete data from SEC EDGAR. "
                f"Row: {row}. Rejecting row — cannot trust incomplete financial data."
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(IncomeStatementLoader))
