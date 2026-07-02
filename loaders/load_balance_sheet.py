#!/usr/bin/env python3

"""
Balance Sheet Loader — annual and quarterly from SEC EDGAR (single authoritative source).

Period determined by LOADER_PERIOD env var or --period CLI flag for manual runs.
"""

import logging
import os
import sys
from datetime import date, datetime
from typing import Any, cast

from loaders.runner import run_loader
from utils.external import SecEdgarClient, sec_statements
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

_PERIOD_CONFIG = {
    "annual": {
        "table_name": "annual_balance_sheet",
        "primary_key": ("symbol", "fiscal_year"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "total_assets",
                "current_assets",
                "total_liabilities",
                "current_liabilities",
                "stockholders_equity",
                "inventory",
                "cash_and_equivalents",
                "accounts_receivable",
                "ppe_net",
                "goodwill",
                "long_term_debt",
            }
        ),
        "field_mapping": {
            # SEC EDGAR client converts concept names to snake_case before returning
            "assets": "total_assets",
            "assets_current": "current_assets",
            "cash_and_cash_equivalents_at_carrying_value": "cash_and_equivalents",
            "accounts_receivable_net_current": "accounts_receivable",
            "inventory_net": "inventory",
            "property_plant_and_equipment_net": "ppe_net",
            "goodwill": "goodwill",
            "liabilities": "total_liabilities",
            "liabilities_current": "current_liabilities",
            "stockholders_equity": "stockholders_equity",
            "long_term_debt": "long_term_debt",
        },
    },
    "quarterly": {
        "table_name": "quarterly_balance_sheet",
        "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
        "schema_cols": frozenset(
            {
                "symbol",
                "fiscal_year",
                "fiscal_quarter",
                "total_assets",
                "current_assets",
                "total_liabilities",
                "stockholders_equity",
            }
        ),
        "field_mapping": {
            "fiscal_period": "fiscal_quarter",
            "assets": "total_assets",
            "assets_current": "current_assets",
            "liabilities": "total_liabilities",
            "stockholders_equity": "stockholders_equity",
        },
    },
}


def _resolve_period(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "annual")


class BalanceSheetLoader(OptimalLoader):
    """Balance sheet loader from SEC EDGAR (official, authoritative source only)."""

    watermark_field = "fiscal_year"
    exclude_etfs_from_symbols = True

    def __init__(self, period: str | None = None):
        period = _resolve_period(period)
        if period not in ("annual", "quarterly"):
            raise ValueError(f"Invalid period: {period!r}; must be 'annual' or 'quarterly'")
        cfg = _PERIOD_CONFIG[period]
        self.period = period
        self.table_name: str = cast(str, cfg["table_name"])
        self.primary_key: tuple[str, ...] = cast(tuple[str, ...], cfg["primary_key"])
        self._schema_cols: frozenset[str] = cast(frozenset[str], cfg["schema_cols"])
        self._field_mapping: dict[str, str] | None = cast(dict[str, str] | None, cfg.get("field_mapping"))
        super().__init__()
        self._sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        try:
            rows = sec_statements.get_balance_sheet(self._sec_client, symbol, period=self.period)

            if not rows:
                logger.warning(
                    f"[BALANCE_SHEET] {symbol}: No {self.period} balance sheet data in SEC EDGAR. "
                    f"Stock may lack SEC filings."
                )
                return self._unavailable_record(symbol, "No balance sheet data in SEC EDGAR")

            logger.info("%s: Fetched %d %s balance sheet row(s)", symbol, len(rows), self.period)

            since_year = int(since.year) if since else 2000
            filtered = []
            for r in rows:
                if isinstance(r, dict):
                    if "fiscal_year" not in r or r["fiscal_year"] is None:
                        logger.warning(f"[BALANCE_SHEET] {symbol}: Row missing required 'fiscal_year' field. Skipping.")
                        continue
                    if r["fiscal_year"] > since_year:
                        filtered.append(r)

            if len(filtered) < len(rows) and len(rows) > 0:
                logger.debug(f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year}")
            return self.transform(filtered)
        except Exception as e:
            logger.error(f"[BALANCE_SHEET] Failed to fetch balance sheet for {symbol}: {type(e).__name__}: {e}")
            raise RuntimeError(f"[BALANCE_SHEET] Failed to fetch balance sheet for {symbol}: {e}") from e

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

        seen = {}
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
        # Fail-fast: symbol is required (primary key). No fallback to placeholder.
        if "symbol" not in row or not row["symbol"]:
            logger.warning(
                f"[{self.table_name}] Row missing required 'symbol' (primary key): {row}. Rejecting."
            )
            return False

        symbol = row["symbol"]

        if not super()._validate_row(row):
            logger.warning(
                f"[{self.table_name}] Row failed parent validation (missing primary key fields) for symbol '{symbol}'. "
                f"Row: {row}."
            )
            return False
        fy = row.get("fiscal_year")
        if not (fy and 1990 < fy < 2100):
            logger.warning(
                f"[{self.table_name}] Row has invalid or missing fiscal_year for symbol '{symbol}'. "
                f"Expected 4-digit year between 1990 and 2100, got: {fy}."
            )
            return False
        if self.period == "quarterly" and row.get("fiscal_quarter") is None:
            logger.warning(
                f"[{self.table_name}] Quarterly balance sheet row missing required 'fiscal_quarter' "
                f"for symbol '{symbol}' fiscal_year {fy}."
            )
            return False

        # Reject rows where all key balance sheet fields are NULL
        # (indicates API failure or incomplete data from SEC EDGAR)
        balance_fields = ["total_assets", "current_assets", "total_liabilities"]
        if all(row.get(field) is None for field in balance_fields):
            logger.error(
                f"[{self.table_name}] Row has all critical balance sheet fields NULL for symbol '{symbol}' "
                f"fiscal_year {fy}. This indicates incomplete data from SEC EDGAR. "
                f"Row: {row}. Rejecting row — cannot trust incomplete financial data."
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(BalanceSheetLoader))
