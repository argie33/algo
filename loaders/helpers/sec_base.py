#!/usr/bin/env python3
"""Unified SEC Data Loader Base Class - Shared utilities for SEC EDGAR patterns.

Two complementary SEC data patterns:

1. PATTERN A: Fetch directly from SEC EDGAR API (raw data ingestion)
   - Used by: load_financial_statements.py
   - Flow: SEC EDGAR API → DB (annual/quarterly income, balance, cash flow)
   - Base class: SecEdgarStatementLoader

2. PATTERN B: Read from already-loaded SEC tables (metrics computation)
   - Used by: load_quality_growth_metrics.py
   - Flow: DB tables → Compute metrics (ROE, growth) → Output tables
   - Base class: SecFinancialsLoader

Both patterns share:
- NaN Decimal handling (SEC XBRL data quality issue)
- Schema healing (auto-create missing columns)
- Data unavailability markers (explicit, not silent)
- ETF exclusion (SEC data only for companies)
"""

import logging
import os
from abc import abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, cast

from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class SecLoaderBase(OptimalLoader):
    """Unified base class for all SEC data loaders.

    Provides shared utilities:
    - Decimal NaN cleaning (SEC XBRL quirk)
    - Schema healing (auto-create missing columns)
    - Data unavailability handling (explicit markers)
    - ETF exclusion (companies only)

    Subclasses implement one of two patterns:
    1. API fetchers (SecEdgarStatementLoader) - fetch from SEC EDGAR API
    2. DB readers (SecFinancialsLoader) - read from already-loaded tables
    """

    # All SEC loaders must exclude ETFs/bonds (no SEC filings)
    exclude_etfs_from_symbols = True

    # Subclasses may define REQUIRED_COLUMNS for schema healing
    REQUIRED_COLUMNS: dict[str, str] = {}

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        if self.REQUIRED_COLUMNS:
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
        return tuple(SecLoaderBase._clean_decimal(v) for v in row)

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
        """Subclasses must implement fetch_incremental."""
        raise NotImplementedError("Subclass must implement fetch_incremental")

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Default transform: no transformation needed. Subclasses may override."""
        return rows


class SecEdgarStatementLoader(SecLoaderBase):
    """Pattern A: Fetch SEC EDGAR financial statements (raw data ingestion).

    Used by: load_financial_statements.py
    Fetches income statements, balance sheets, cash flows across periods.
    """

    watermark_field = "fiscal_year"

    # statement_type ("income"/"balance"/"cashflow", used for table/config naming
    # throughout load_financial_statements.py) does not match SecEdgarClient's actual
    # method names (get_income_statement/get_balance_sheet/get_cash_flow) closely enough
    # for f"get_{statement_type}" to resolve correctly. Confirmed live 2026-07-13, the
    # first time the consolidated financials_all loader ever ran (previously blocked for
    # its entire existence by an unrelated pipeline hang): every single symbol failed with
    # AttributeError: 'SecEdgarClient' object has no attribute 'get_balance' -- and would
    # have failed identically for "income" ("get_income" vs get_income_statement) and
    # "cashflow" ("get_cashflow" vs get_cash_flow, missing the underscore) had the run
    # gotten that far.
    _STATEMENT_TYPE_TO_METHOD = {
        "income": "get_income_statement",
        "balance": "get_balance_sheet",
        "cashflow": "get_cash_flow",
    }

    def __init__(
        self,
        statement_type: str,
        period_config: dict[str, dict[str, Any]],
        period: str | None = None,
    ):
        """Initialize loader with statement type and period config."""
        period = self._resolve_period(period)
        if period not in ("annual", "quarterly"):
            raise ValueError(f"Invalid period: {period!r}; must be 'annual' or 'quarterly'")
        if period not in period_config:
            raise ValueError(f"Period {period!r} not in config for {statement_type}")

        cfg = period_config[period]
        self.statement_type = statement_type
        self.period = period
        self.table_name: str = cast(str, cfg["table_name"])
        self.primary_key: tuple[str, ...] = cast(tuple[str, ...], cfg["primary_key"])
        self._schema_cols: frozenset[str] = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping: dict[str, str] | None = cast(dict[str, str] | None, cfg.get("field_mapping"))

        super().__init__()
        self._sec_client = SecEdgarClient()

    @staticmethod
    def _resolve_period(cli_arg: str | None) -> str:
        """Resolve period from CLI arg or LOADER_PERIOD env var."""
        if cli_arg:
            return cli_arg
        return os.getenv("LOADER_PERIOD", "annual")

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError as e:
            raise RuntimeError(f"[{self.statement_type.upper()}] {symbol}: CIK not found in SEC ticker cache.") from e

        if not cik:
            raise RuntimeError(f"[{self.statement_type.upper()}] CIK resolution failed for {symbol}.")

        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

        try:
            method_name = self._STATEMENT_TYPE_TO_METHOD.get(self.statement_type)
            if method_name is None:
                raise RuntimeError(
                    f"[{self.statement_type.upper()}] Unknown statement_type {self.statement_type!r}. "
                    f"Must be one of {sorted(self._STATEMENT_TYPE_TO_METHOD)}."
                )
            getter_method = getattr(self._sec_client, method_name)
            rows = getter_method(symbol, period=self.period)

            if not rows:
                logger.debug(
                    f"[{self.statement_type.upper()}] {symbol}: No {self.period} data in SEC EDGAR. "
                    f"Stock may be REIT, investment trust, or lack SEC filings."
                )
                return [
                    {
                        "symbol": symbol,
                        "fiscal_year": 0,
                        "data_unavailable": True,
                        "reason": f"no_{self.period}_{self.statement_type}_data_in_sec_edgar_reit_or_special_entity",
                    }
                ]

            logger.info(
                "%s: Fetched %d %s %s row(s)",
                symbol,
                len(rows),
                self.period,
                self.statement_type,
            )

            since_year = int(since.year) if since else 2000
            filtered = []
            for r in rows:
                if "fiscal_year" not in r or r["fiscal_year"] is None:
                    raise ValueError(f"Row missing required 'fiscal_year' field: {r}.")
                if r["fiscal_year"] > since_year:
                    filtered.append(r)

            if len(filtered) < len(rows):
                logger.debug(f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year}")

            return filtered

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"[{self.statement_type.upper()}] Failed to fetch data for {symbol}: {e}.") from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform SEC EDGAR data to schema format."""
        if self._field_mapping is None:
            raise RuntimeError(f"[{self.table_name}] Field mapping not initialized.")

        transformed = []
        skipped_invalid_fields = 0

        for r in rows:
            row: dict[str, Any] = {}
            if "symbol" in r:
                row["symbol"] = r["symbol"]
            if "fiscal_year" in r:
                row["fiscal_year"] = r["fiscal_year"]

            field_mapping = self._field_mapping
            for sec_field, value in r.items():
                if sec_field in ("symbol", "fiscal_year"):
                    continue

                if sec_field not in field_mapping:
                    logger.debug(
                        f"[{self.table_name}] {r.get('symbol')}: Unmapped SEC field '{sec_field}' "
                        f"— may indicate schema change or optional field. Skipping."
                    )
                    continue

                db_field = field_mapping[sec_field]
                if db_field not in self._schema_cols:
                    raise RuntimeError(
                        f"[{self.table_name}] Field mapping configuration error: SEC field '{sec_field}' "
                        f"maps to '{db_field}' but '{db_field}' not in target schema. "
                        f"Check field_mapping and schema definitions."
                    )
                row[db_field] = value

            if "fiscal_quarter" in row and isinstance(row["fiscal_quarter"], str):
                quarter_str = row["fiscal_quarter"]
                quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
                quarter_num = quarter_map.get(quarter_str)
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

        return list(seen.values())


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
                WHERE symbol = %s
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
                WHERE symbol = %s
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

    def _fetch_annual_income_statement_history(self, symbol: str, years: int = 10) -> list[tuple[Any, Any, Any]] | None:
        """Fetch historical annual income statements for multi-year analysis.

        Args:
            symbol: Stock symbol
            years: Number of years to fetch (default 10 for 1Y/3Y/5Y lookback)

        Returns:
            List of tuples (fiscal_year, revenue, earnings_per_share) ordered by fiscal_year DESC.
            All NaN Decimal values are cleaned to None.
            Returns None if no data found.
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
            logger.debug(
                f"[{self.table_name}] No income statement history for {symbol}: "
                "SEC filing data not available or insufficient history (young company, new IPO, or lack of coverage)"
            )
            return None
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to fetch income statement history for {symbol}: {e}")
            raise RuntimeError(f"Cannot fetch income statement history for {symbol}: {e}") from e
