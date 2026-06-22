#!/usr/bin/env python3
import sys


"""
Income Statement Loader -â€ annual and quarterly from SEC EDGAR.

Period determined by LOADER_PERIOD env var (financials_annual_income / financials_quarterly_income)
or --period CLI flag for manual runs.
"""

import logging

import psycopg2


logger = logging.getLogger(__name__)
import os
from datetime import date
from typing import Optional, cast

from loaders.runner import run_loader
from utils.external.sec_edgar import SecEdgarClient
from utils.loaders.config import get_parallelism
from utils.optimal_loader import OptimalLoader


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
    watermark_field = "fiscal_year"

    def __init__(self, period: str | None = None):
        period = _resolve_period(period)
        assert period in ("annual", "quarterly")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name = cast(str, cfg["table_name"])
        self.primary_key = cast(tuple[str, ...], cfg["primary_key"])
        self._edgar_period = cast(str, cfg["edgar_period"])
        self._schema_cols = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping = cast(dict[str, str] | None, cfg.get("field_mapping"))
        super().__init__()
        self._sec_client = SecEdgarClient()

    def _get_null_revenue_years(self, symbol: str) -> set:
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
            )

    def fetch_incremental(self, symbol: str, since: date | None):
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError:
            logger.debug("%s: not in SEC ticker cache, skipping", symbol)
            return None
        if not cik:
            raise RuntimeError(
                f"[INCOME_STATEMENT] CIK resolution failed for {symbol}. "
                "Cannot fetch income statement data without CIK."
            )
        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)
        try:
            rows = self._sec_client.get_income_statement(symbol, period=self._edgar_period)
            if not rows:
                logger.debug("%s: no %s income statement data in SEC EDGAR, skipping", symbol, self._edgar_period)
                return None
            logger.info("%s: Fetched %d %s income statement row(s)", symbol, len(rows), self._edgar_period)

            since_year = int(since.year) if since else 2000
            # Also include years already in DB where revenue is NULL (backfill ASC 606 gaps)
            null_revenue_years = self._get_null_revenue_years(symbol)
            filtered = [
                r for r in rows if r.get("fiscal_year", 0) > since_year or r.get("fiscal_year") in null_revenue_years
            ]
            if len(filtered) < len(rows):
                logger.debug(
                    f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year} "
                    f"(watermark incremental load — keeping {len(filtered)} newer rows; "
                    f"{len(null_revenue_years)} null-revenue years also included)"
                )
            return filtered or None
        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[INCOME_STATEMENT] SEC EDGAR error for {symbol}: {e}. "
                "API failure prevents data fetch. Cannot proceed."
            ) from e

    _QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    def transform(self, rows):
        transformed = []
        for r in rows:
            row = {}
            for sec_field, value in r.items():
                # Apply field mapping first
                db_field = self._field_mapping.get(sec_field, sec_field)
                # Only keep fields in schema
                if db_field in self._schema_cols:
                    # Prefer non-None: set if not yet set, or replace None with a real value.
                    # This handles multiple concepts mapping to the same column (e.g., legacy
                    # "Revenues" vs. post-ASC 606 "RevenueFromContractWithCustomer...").
                    if db_field not in row or (row[db_field] is None and value is not None):
                        row[db_field] = value
            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                row["fiscal_quarter"] = self._QUARTER_MAP.get(row["fiscal_quarter"])
            transformed.append(row)

        seen = {}
        for row in transformed:
            if self.period == "annual":
                key = (row.get("symbol"), row.get("fiscal_year"))
            else:
                key = (
                    row.get("symbol"),
                    row.get("fiscal_year"),
                    row.get("fiscal_quarter"),
                )
            if key not in seen:
                seen[key] = row
        return list(seen.values())

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            return False
        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
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
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(IncomeStatementLoader))
