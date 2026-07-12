#!/usr/bin/env python3
"""Consolidated SEC EDGAR Financial Statement Loader."""

import logging
import os
import socket
from datetime import date
from typing import Any, cast

from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class SecEdgarStatementLoader(OptimalLoader):
    """Base loader for SEC EDGAR financial statements (balance sheet, income, cash flow)."""

    watermark_field = "fiscal_year"
    exclude_etfs_from_symbols = True

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
        """Fetch financial data for a symbol, filtering by watermark (fiscal_year)."""
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError as e:
            raise RuntimeError(f"[{self.statement_type.upper()}] {symbol}: CIK not found in SEC ticker cache.") from e

        if not cik:
            raise RuntimeError(f"[{self.statement_type.upper()}] CIK resolution failed for {symbol}.")

        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

        try:
            getter_method = getattr(self._sec_client, f"get_{self.statement_type}")
            rows = getter_method(symbol, period=self.period)

            # CRITICAL FIX: Handle stocks with no SEC financial data gracefully.
            # REITs, investment trusts, and other special entities often have no
            # traditional income statement data in SEC EDGAR. Return explicit data_unavailable marker
            # instead of empty list (which gets silently skipped by OptimalLoader).
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
            # CRITICAL: Ensure symbol and fiscal_year are always preserved
            if "symbol" in r:
                row["symbol"] = r["symbol"]
            if "fiscal_year" in r:
                row["fiscal_year"] = r["fiscal_year"]

            field_mapping = self._field_mapping
            for sec_field, value in r.items():
                # Skip fields we already handled above
                if sec_field in ("symbol", "fiscal_year"):
                    continue

                # FAIL-FAST: Validate all mapped fields exist in schema (configuration error if not)
                if sec_field not in field_mapping:
                    # Unmapped field — log and skip (don't silently discard without visibility)
                    logger.debug(
                        f"[{self.table_name}] {r.get('symbol')}: Unmapped SEC field '{sec_field}' "
                        f"— may indicate schema change or optional field. Skipping."
                    )
                    continue

                db_field = field_mapping[sec_field]  # Field is guaranteed to exist
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
