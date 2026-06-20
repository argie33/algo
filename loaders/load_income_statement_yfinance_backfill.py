#!/usr/bin/env python3
"""Income Statement Backfill Loader - fill missing SEC EDGAR data with yfinance.

Backfills annual_income_statement rows where revenue or EPS are NULL.
Uses yfinance as authoritative source for public companies.
Skips if yfinance data also missing or mismatches validation checks.

Run:
    python3 load_income_statement_yfinance_backfill.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date
from typing import Optional

import yfinance

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader
import psycopg2


logger = logging.getLogger(__name__)


class IncomeStatementYFinanceBackfillLoader(OptimalLoader):
    """Backfill missing revenue/EPS data from yfinance for symbols with NULL values."""

    table_name = "annual_income_statement"
    primary_key = ("symbol", "fiscal_year")
    watermark_field = ""  # No date watermark — we just fill holes

    def fetch_incremental(self, symbol: str, since: date | None):
        """Fetch revenue/EPS from yfinance to backfill NULL rows in DB.

        Only returns rows if:
        1. Symbol has at least one annual_income_statement row with NULL revenue
        2. yfinance has data for that symbol
        3. Data matches fiscal_year already in DB (not adding new rows)

        Returns list of dicts with symbol, fiscal_year, revenue, earnings_per_share
        to be upserted into DB.
        """
        try:
            # Check if this symbol has any NULL revenue rows
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT fiscal_year FROM annual_income_statement WHERE symbol = %s AND revenue IS NULL ORDER BY fiscal_year DESC",
                    (symbol,),
                )
                null_years = {row[0] for row in cur.fetchall()}

            if not null_years:
                logger.debug(
                    f"{symbol}: No NULL revenue rows found. Skipping backfill."
                )
                return None

            logger.debug(
                f"{symbol}: Found {len(null_years)} fiscal year(s) with NULL revenue: {sorted(null_years)}"
            )

            # Fetch income statement from yfinance
            try:
                ticker = yfinance.Ticker(symbol)
                income_stmt = ticker.income_stmt

                if income_stmt is None or income_stmt.empty:
                    logger.debug(
                        f"{symbol}: yfinance has no income statement data. Cannot backfill."
                    )
                    return None
            except (ValueError, KeyError, AttributeError, TypeError, Exception) as e:
                logger.debug(
                    f"{symbol}: yfinance fetch failed: {e}. Skipping backfill."
                )
                return None

            # Extract Total Revenue and EPS columns
            revenue_row = (
                income_stmt.loc["Total Revenue"]
                if "Total Revenue" in income_stmt.index
                else None
            )
            eps_row = (
                income_stmt.loc["Diluted EPS"]
                if "Diluted EPS" in income_stmt.index
                else (
                    income_stmt.loc["Basic EPS"]
                    if "Basic EPS" in income_stmt.index
                    else None
                )
            )

            if revenue_row is None:
                logger.debug(
                    f"{symbol}: yfinance has no 'Total Revenue' field. Cannot backfill."
                )
                return None

            # Extract fiscal years from yfinance dates (YYYY-12-31)
            backfill_rows = []
            for idx, revenue_val in revenue_row.items():
                if revenue_val is None or (
                    hasattr(revenue_val, "isna") and revenue_val.isna()
                ):
                    continue

                fiscal_year = idx.year if hasattr(idx, "year") else int(str(idx)[:4])

                if fiscal_year not in null_years:
                    logger.debug(
                        f"{symbol}: FY {fiscal_year} in yfinance but not in DB NULL rows. Skipping."
                    )
                    continue

                # Extract EPS if available
                eps_val = None
                if eps_row is not None:
                    try:
                        eps_val = float(eps_row[idx]) if eps_row[idx] else None
                    except (KeyError, TypeError, ValueError) as e:
                        logger.debug(f"{symbol} FY {fiscal_year}: Failed to extract EPS: {e}")

                # Build backfill row
                backfill_rows.append(
                    {
                        "symbol": symbol,
                        "fiscal_year": fiscal_year,
                        "revenue": float(revenue_val),
                        "earnings_per_share": eps_val,
                    }
                )

            if backfill_rows:
                logger.info(
                    f"{symbol}: Backfilling {len(backfill_rows)} rows from yfinance"
                )
                return backfill_rows
            else:
                logger.debug(f"{symbol}: No matching yfinance data to backfill.")
                return None

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(
                f"{symbol}: Backfill check failed: {e}. Will skip this symbol."
            )
            return None

    def transform(self, rows):
        """No transformation needed — data already formatted."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate backfill row has required fields."""
        if not super()._validate_row(row):
            return False

        # Must have symbol, fiscal year, and at least one of revenue/eps
        if not row.get("symbol") or not row.get("fiscal_year"):
            return False
        if row.get("revenue") is None and row.get("earnings_per_share") is None:
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(IncomeStatementYFinanceBackfillLoader))
