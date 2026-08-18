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

    @staticmethod
    def _validate_numeric_precision(value: Any, precision: int, scale: int) -> bool:
        """Check if a numeric value fits within NUMERIC(precision, scale) constraints.

        Args:
            value: Value to validate (None is always valid)
            precision: Total digits
            scale: Decimal places

        Returns:
            True if value fits, False if it would overflow
        """
        if value is None:
            return True
        try:
            if isinstance(value, str):
                value = float(value)
            elif isinstance(value, Decimal):
                if value.is_nan() or value.is_infinite():
                    return True
                value = float(value)
            elif not isinstance(value, (int, float)):
                return True
            max_integer_digits = precision - scale
            max_value: float = float(10**max_integer_digits - 10 ** (-scale))
            return abs(float(value)) <= max_value
        except (ValueError, TypeError, OverflowError):
            return True

    _precision_cache: dict[str, dict[str, tuple[int, int] | None]] = {}

    def _get_field_precision_scale(self, db_field: str) -> tuple[int, int] | None:
        """Look up the real NUMERIC(precision, scale) for a column from the live DB schema.

        BUGFIX 2026-08-16: _validate_numeric_precision was always called with its
        hardcoded default of NUMERIC(12,4) (~$100M cap), regardless of what the column
        actually allows. Confirmed live: revenue/net_income/total_assets etc. are
        NUMERIC(20,2) or unbounded `numeric` in the DB, but the (12,4) default rejected
        any real company's figures above ~$100M as "overflow" and marked the row
        data_unavailable - flagging 67-80% of annual/quarterly statement rows as
        unavailable when the data was actually fine. Looking up the true column
        precision (cached per table) makes the check match what the DB will actually
        accept. Returns None for unbounded `numeric` columns (no overflow is possible).
        """
        table_cache = SecLoaderBase._precision_cache.get(self.table_name)
        if table_cache is None:
            table_cache = {}
            try:
                from utils.db.context import DatabaseContext

                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT column_name, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_name = %s AND data_type = 'numeric'
                        """,
                        (self.table_name,),
                    )
                    for col, col_precision, col_scale in cur.fetchall():
                        table_cache[col] = (col_precision, col_scale) if col_precision is not None else None
            except Exception as e:
                logger.error(f"[{self.table_name}] Failed to load numeric column precision from schema: {e}")
            SecLoaderBase._precision_cache[self.table_name] = table_cache
        return table_cache.get(db_field)

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

    def _wrap_exception_handler(self, symbol: str, exc: Exception, context: str) -> list[dict[str, Any]]:
        """Unified exception handler for SEC data fetching failures.

        When handle_exception() itself fails (programming error), wraps it safely
        rather than letting the error propagate uncaught. This prevents loader
        crashes when the exception handler has a bug (e.g., unexpected exception type).

        Args:
            symbol: Stock symbol being processed
            exc: The original exception from fetch attempt
            context: Description of what was being attempted (e.g., "fetching company info")

        Returns:
            List with data_unavailable marker on handler success, or raises RuntimeError if handler itself fails

        Raises:
            RuntimeError: If exception handler fails (catches ValueError, KeyError, AttributeError from handler)
        """
        from utils.loaders.exception_handler import handle_exception

        try:
            marker = handle_exception(symbol, exc, context)
            return [marker]
        except (ValueError, KeyError, AttributeError) as handler_err:
            logger.critical(
                f"[{symbol}] Exception handler failed while processing {type(exc).__name__}: {exc}. "
                f"Handler error: {type(handler_err).__name__}: {handler_err}",
                exc_info=True,
            )
            raise RuntimeError(f"Failed to handle SEC fetch error for {symbol}: {handler_err}") from exc

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

    def watermark_from_rows(self, rows: list[dict[str, Any]]) -> date:
        """Map the integer fiscal_year watermark onto a date (Dec 31 of the max year).

        BUGFIX 2026-07-14 (found live): watermark_field here is fiscal_year - an int -
        and the base implementation returned that int, so WatermarkManager crashed on
        .isoformat() ('int' object has no attribute 'isoformat') AFTER rows were
        inserted, marking every symbol failed. This was masked for the loader's entire
        life by the missing-field_mapping transform crash that preceded it.

        Dec 31 of the max loaded fiscal year round-trips correctly: fetch_incremental
        derives its incremental cutoff as since.year. Marker-only batches (fiscal_year
        0) map to Dec 31 2000 - identical to the no-watermark default (since_year
        2000), so unavailable symbols keep refetching their full window.

        FIXED 2026-08-10: a real fiscal_year row that transform() marked
        data_unavailable=True (e.g. 'incomplete_sec_filing_income' for a recent
        spinoff still mid-filing) was still advancing the watermark to that year,
        because this function only ever looked at fiscal_year, never at
        data_unavailable. fetch_incremental's `fiscal_year > since_year` filter
        (below) then permanently excluded that year from every future incremental
        fetch - even after the company finished filing and SEC EDGAR had real
        revenue/net_income for it - since only strictly-newer fiscal years would
        ever be re-requested. Live-confirmed on HONA: the exact spinoff this
        marker logic was built for (see class docstring) later filed real
        FY2026 financials (revenue=$8.87B, net_income=$880M), but the stale
        watermark meant fetch_incremental never asked SEC EDGAR for FY2026 again,
        so the DB row stayed marked unavailable indefinitely. 112 rows (101
        income, 11 cashflow) found stuck this way system-wide and corrected by a
        one-time backfill; excluding unavailable rows from the watermark
        calculation stops the backlog from re-accumulating.
        """
        max_year = 0
        for r in rows:
            if r.get("data_unavailable"):
                continue
            fiscal_year = r.get("fiscal_year")
            if isinstance(fiscal_year, int) and fiscal_year > max_year:
                max_year = fiscal_year
        if max_year <= 0:
            return date(2000, 12, 31)
        return date(max_year, 12, 31)

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

    # Column name is validated against a fixed literal set (not user/DB-supplied) before
    # ever reaching an f-string SQL fragment - see the retry-set query above.
    _CORE_FIELD_BY_STATEMENT_TYPE = {
        "income": "net_income",
        "balance": "stockholders_equity",
        "cashflow": "operating_cash_flow",
    }

    def __init__(
        self,
        statement_type: str,
        period_config: dict[str, dict[str, Any]],
        period: str | None = None,
        sec_client: SecEdgarClient | None = None,
    ):
        """Initialize loader with statement type and period config.

        Args:
            statement_type: 'income', 'balance', or 'cashflow'.
            period_config: Per-period table/schema configuration.
            period: 'annual' or 'quarterly' (falls back to LOADER_PERIOD env var).
            sec_client: Optional shared SecEdgarClient. Passing one client to
                several statement/period loaders lets them share its per-CIK
                companyfacts LRU cache (and rate limiter), so all statements
                for a symbol are derived from a single HTTP fetch.
        """
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
        # FIXED 2026-08-09: sec_fields listed here only ever WRITE their target db_field
        # when nothing else has already populated it. Needed for the revenue fallback
        # chain (interest_income_operating/interest_and_dividend_income_operating) -
        # those concepts are meant as a last resort for banks/REITs with no standard
        # revenue tag, but transform()'s normal "last one iterated wins" merge let them
        # silently clobber a real revenue figure for any company that happens to ALSO
        # report a genuine interest/dividend income line item (ORLY live-confirmed: real
        # ~$4B/quarter retail revenue overwritten by a $1.75M interest-income fact).
        self._fallback_only_fields: frozenset[str] = cast(frozenset[str], cfg.get("fallback_only_fields", frozenset()))
        # FIXED 2026-08-09: REIT-specific fallback fields - same "don't overwrite
        # something already found" mechanism as _fallback_only_fields above, but
        # scoped to REIT filers only (SIC 6798). Most post-2018 filers legitimately
        # have their ASC-606 contract-revenue tag supersede the legacy "Revenues" tag
        # (fuller, more current figure) - true for the general priority chain above.
        # False for equity REITs specifically: their real revenue ("Revenues", mostly
        # lease income) is explicitly OUT of ASC 606's scope, so their ASC-606 tag only
        # ever captures a much smaller non-lease fee-income line. Live-confirmed UDR:
        # revenues=$1.67B (real) vs revenue_from_contract_with_customer_excluding_
        # assessed_tax=$8.3M (real but minor fee income) - the general chain let the
        # $8.3M win.
        self._reit_only_fallback_fields: frozenset[str] = cast(
            frozenset[str], cfg.get("reit_only_fallback_fields", frozenset())
        )
        self._reit_symbols: frozenset[str] | None = None

        super().__init__()
        self._sec_client = sec_client if sec_client is not None else SecEdgarClient()

    @staticmethod
    def _resolve_period(cli_arg: str | None) -> str:
        """Resolve period from CLI arg or LOADER_PERIOD env var."""
        if cli_arg:
            return cli_arg
        return os.getenv("LOADER_PERIOD", "annual")

    def _get_reit_symbols(self) -> frozenset[str]:
        """Bulk-fetch REIT symbols (SIC 6798) once per loader run, not per-row.

        Same SIC code scores.py already uses for CEF/trust filtering (see
        lambda/api/routes/scores.py's sic_code exclusion comment).
        """
        if self._reit_symbols is None:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute("SELECT symbol FROM company_info_sec WHERE sic_code = 6798")
                self._reit_symbols = frozenset(row[0] for row in cur.fetchall())
        return self._reit_symbols

    def _unavailable_marker(self, symbol: str, reason: str) -> dict[str, Any]:
        """Build an explicit data_unavailable marker row for this loader's period.

        FIXED 2026-07-28: every call site here used to hand-build this dict with only
        `fiscal_year: 0` as its sentinel key. That's a complete key for ANNUAL loaders
        (transform()'s dedup only requires symbol+fiscal_year there), but for QUARTERLY
        loaders transform() also requires a non-None `fiscal_quarter` to build its dedup
        key - a marker missing that key silently fails the `if fiscal_quarter is None:
        skip` check, so the ENTIRE marker row vanishes before it can be written. If a
        symbol's only row this run is one of these markers (true for any foreign private
        issuer that files 20-F/6-K instead of 10-Q, e.g. ZIM, ZTO, ZH, ZKH), that leaves
        transform() with zero surviving rows, which raises "CRITICAL: No valid rows
        after transformation" - a hard failure - instead of writing the clean marker this
        method already exists to produce. Adding a `fiscal_quarter: 0` sentinel (parallel
        to the existing `fiscal_year: 0` one, and equally distinct from real Q1-4 values)
        lets quarterly markers survive the same dedup path annual ones already do.
        """
        marker: dict[str, Any] = {
            "symbol": symbol,
            "fiscal_year": 0,
            "data_unavailable": True,
            "reason": reason,
        }
        if self.period != "annual":
            # NOT "fiscal_quarter" - field_mapping's source-side key for this is
            # "fiscal_period" (see _QUARTERLY_EXTRA in load_financial_statements.py),
            # which the generic per-field copy loop below maps to the "fiscal_quarter"
            # DB column. Setting "fiscal_quarter" directly here would itself hit the
            # "sec_field not in field_mapping" skip and vanish exactly like the bug
            # this method exists to fix.
            marker["fiscal_period"] = 0
        return marker

    def _try_yfinance_fallback(self, symbol: str, since: date | None, sec_reason: str) -> list[dict[str, Any]]:
        """Attempt a yfinance fallback fetch when SEC EDGAR has nothing for this symbol.

        Called only from the paths where SEC genuinely returned no usable data (CIK not
        found, 404/empty facts under any taxonomy) - see utils/external/yfinance_financials.py's
        docstring for why this is a fallback, not a competing source, and why every row it
        returns is tagged data_source='yfinance' rather than silently blended with SEC data.

        Returns the standard SEC-unavailable marker (same as the caller would have returned
        without this fallback) if yfinance also has nothing, or errors - a fallback failing
        is not itself a loader failure, the symbol just stays genuinely unavailable.
        """
        try:
            from utils.external.yfinance_financials import fetch_financial_statement

            yf_rows = fetch_financial_statement(symbol, self.statement_type, self.period)
        except Exception as e:
            logger.debug(f"[{self.table_name}] {symbol}: yfinance fallback also failed: {e}")
            yf_rows = None

        if not yf_rows:
            return [self._unavailable_marker(symbol, sec_reason)]

        since_year = int(since.year) if since else 2000
        filtered = [r for r in yf_rows if isinstance(r.get("fiscal_year"), int) and r["fiscal_year"] > since_year]
        if not filtered:
            return [self._unavailable_marker(symbol, sec_reason)]

        for r in filtered:
            r["data_source"] = "yfinance"
        logger.info(
            f"[{self.table_name}] {symbol}: SEC EDGAR unavailable ({sec_reason}), "
            f"recovered {len(filtered)} row(s) from yfinance fallback"
        )
        return filtered

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        # FIX 2026-08-10: watermark/table desync self-heal. loader_watermarks can advance
        # for a symbol (via bulk_insert_manager's advance_watermark, called with
        # in_transaction=False - a separate write from the actual row INSERT) while the
        # real rows for that symbol are later deleted/never persisted (table
        # truncation/reset, a rolled-back shared "ALL MODE" transaction, etc.) - live-
        # reproduced 2026-08-10 for BFS/UDR: watermark claimed fiscal_year data through
        # 2026-12-31 with rows_loaded=112/114, but annual_income_statement had ZERO real
        # rows for either symbol. Since `since` only ever narrows what gets fetched
        # (fetch_incremental filters to fiscal_year > since.year below), a stale
        # "already loaded" watermark permanently starves that symbol of ever being
        # re-fetched via the normal incremental path - it looks like "no new data" forever.
        # Guard: if the watermark claims data exists but this symbol genuinely has zero
        # rows in the target table, the watermark is provably wrong - ignore it and fetch
        # the full history instead of trusting a claim the table itself contradicts.
        if since is not None and self.is_symbol_based:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(f"SELECT 1 FROM {self.table_name} WHERE symbol = %s LIMIT 1", (symbol,))
                if cur.fetchone() is None:
                    logger.warning(
                        f"[{self.table_name}] {symbol}: watermark={since} claims data already loaded, "
                        f"but table has zero rows for this symbol - watermark/table desync, "
                        f"ignoring watermark and fetching full history."
                    )
                    since = None
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
        except ValueError:
            # Legitimate, permanent condition (e.g. preferred-share tickers like WRB$E
            # trade under the same CIK as their common stock but aren't separately
            # listed in SEC's company_tickers.json) - not a fetch bug. Previously raised
            # as a hard failure here, which at scale (dozens of preferred-share symbols
            # in one run) pushed the loader's failure rate past its 15% abort threshold.
            logger.debug(f"[{self.statement_type.upper()}] {symbol}: CIK not found in SEC ticker cache.")
            return self._try_yfinance_fallback(symbol, since, "cik_not_found")

        if not cik:
            return self._try_yfinance_fallback(symbol, since, "cik_not_found")

        logger.debug("Symbol %s resolved to CIK %s", symbol, cik)

        method_name = self._STATEMENT_TYPE_TO_METHOD.get(self.statement_type)
        if method_name is None:
            raise RuntimeError(
                f"[{self.statement_type.upper()}] Unknown statement_type {self.statement_type!r}. "
                f"Must be one of {sorted(self._STATEMENT_TYPE_TO_METHOD)}."
            )
        getter_method = getattr(self._sec_client, method_name)

        try:
            rows = getter_method(symbol, period=self.period)
        except ValueError as e:
            # utils/external/sec_statements.py raises ValueError (prefixed "[SEC_EDGAR]")
            # for the legitimate "no facts under any taxonomy" case, with an explicit
            # contract in its own comments that "downstream loaders must mark
            # data_unavailable with this reason". That contract was never actually
            # honored here - this except previously fell through to the blanket
            # (ValueError, ZeroDivisionError, TypeError) handler below, which just
            # re-raised as RuntimeError, counting a genuinely-no-data REIT/shell/
            # special-entity symbol as a hard FAILURE. At scale (526 never-processed
            # symbols, mostly newly added NYSE preferred-share/SPAC/REIT tickers) that
            # inflated the failure rate past the loader's 15% abort threshold and killed
            # the entire run. Convert to the same clean marker the `not rows` branch
            # below already produces for the equivalent case.
            logger.debug(f"[{self.statement_type.upper()}] {symbol}: No SEC facts available: {e}")
            return self._try_yfinance_fallback(
                symbol, since, f"no_{self.period}_{self.statement_type}_data_in_sec_edgar_reit_or_special_entity"
            )

        if not rows:
            logger.debug(
                f"[{self.statement_type.upper()}] {symbol}: No {self.period} data in SEC EDGAR. "
                f"Stock may be REIT, investment trust, or lack SEC filings."
            )
            return self._try_yfinance_fallback(
                symbol, since, f"no_{self.period}_{self.statement_type}_data_in_sec_edgar_reit_or_special_entity"
            )

        for r in rows:
            r.setdefault("data_source", "sec_audited")

        logger.info(
            "%s: Fetched %d %s %s row(s)",
            symbol,
            len(rows),
            self.period,
            self.statement_type,
        )

        # FIX 2026-08-18 (goal: "no SEC data"/loader audit, NVO live-confirmed): the
        # watermark-exclusion fix (2026-08-10, see watermark_from_rows() above) stops the
        # watermark from advancing TO a still-unavailable fiscal year, but does nothing
        # once a LATER year succeeds and advances the watermark past it - this filter's
        # blunt "fiscal_year > since_year" then permanently excludes every older fiscal
        # year from ever being reprocessed again, including ones still marked
        # data_unavailable that a later concept-list fix (IFRS alias, fallback concept,
        # etc.) might now be able to fill. `rows` here is always the symbol's FULL
        # refetched history (get_income_statement/get_balance_sheet/get_cash_flow don't
        # accept a date cutoff), so the real data to retry is already present in-memory -
        # it was just being thrown away. Live-confirmed: NVO's 2015-2021 annual_income_
        # statement rows had real, correct revenue/net_income values already stored
        # (from some earlier successful fetch) yet stayed data_unavailable=TRUE forever
        # once 2022+ advanced the watermark past them - 486 rows across all 6 statement
        # tables found in this same contradictory state (repaired directly, this fix
        # stops the backlog from re-accumulating). Retry any fiscal year still marked
        # unavailable in the DB regardless of the watermark cutoff, same as a fiscal year
        # newer than the watermark.
        unavailable_years: set[int] = set()
        if since is not None and self.is_symbol_based:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SELECT fiscal_year FROM {self.table_name} WHERE symbol = %s AND data_unavailable = TRUE",
                    (symbol,),
                )
                unavailable_years = {r[0] for r in cur.fetchall() if r[0] is not None}

                # FIX 2026-08-18 (goal: "no SEC data"/loader audit, AVAV live-confirmed):
                # the data_unavailable=TRUE retry above only covers fiscal years marked a
                # total failure - it does nothing for a DIFFERENT, more common shape of
                # the same bug: a row that WAS written successfully (data_unavailable=
                # FALSE) but is missing this statement's one load-bearing field because
                # of an extraction gap (missing concept fallback, mid-year 10-Q instant
                # stub, etc.) that a later fix might now close. AVAV's annual_balance_
                # sheet FY2024-2026 rows are exactly this: real total_assets on file,
                # data_unavailable=FALSE, yet stockholders_equity NULL every year - the
                # 2026-08-18 d36598a2d mid-year-stub fix landed and a fresh full pipeline
                # pass ran afterward, but AVAV's watermark had already advanced past
                # FY2026 from an earlier run, so `fiscal_year > since_year` silently
                # discarded these rows before the fix could ever be applied to them -
                # same root mechanism as the data_unavailable=TRUE case above, just never
                # marked TRUE in the first place because SOME fields did extract fine.
                # `rows` here is always the symbol's FULL refetched history already
                # sitting in memory (see comment above) - retrying costs zero extra SEC
                # API calls, only an extra DB write for symbols that actually qualify.
                core_field = self._CORE_FIELD_BY_STATEMENT_TYPE.get(self.statement_type)
                if core_field:
                    cur.execute(
                        f"SELECT fiscal_year FROM {self.table_name} "
                        f"WHERE symbol = %s AND data_unavailable = FALSE AND {core_field} IS NULL",
                        (symbol,),
                    )
                    unavailable_years |= {r[0] for r in cur.fetchall() if r[0] is not None}

        try:
            since_year = int(since.year) if since else 2000
            filtered = []
            for r in rows:
                if "fiscal_year" not in r or r["fiscal_year"] is None:
                    raise ValueError(f"Row missing required 'fiscal_year' field: {r}.")
                if r["fiscal_year"] > since_year or r["fiscal_year"] in unavailable_years:
                    filtered.append(r)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            # Genuine data-integrity problem (e.g. malformed row), not the "no facts
            # at all" case handled above - keep failing loudly on this one.
            raise RuntimeError(f"[{self.statement_type.upper()}] Failed to fetch data for {symbol}: {e}.") from e

        if len(filtered) < len(rows):
            logger.debug(f"{symbol}: Filtered {len(rows) - len(filtered)} row(s) with fiscal_year <= {since_year}")

        return filtered

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Transform SEC EDGAR data to schema format."""
        if self._field_mapping is None:
            raise RuntimeError(f"[{self.table_name}] Field mapping not initialized.")

        transformed = []
        skipped_invalid_fields = 0
        unmapped_fields_per_symbol: dict[str, set[str]] = {}

        for r in rows:
            row: dict[str, Any] = {}
            if "symbol" in r:
                row["symbol"] = r["symbol"]
            if "fiscal_year" in r:
                row["fiscal_year"] = r["fiscal_year"]
            row["data_unavailable"] = False

            field_mapping = self._field_mapping
            for sec_field, value in r.items():
                if sec_field in ("symbol", "fiscal_year"):
                    continue

                if sec_field not in field_mapping:
                    # FIXED 2026-08-17: "fiscal_period" is present on every annual row (SEC
                    # tags it "FY") but intentionally has no mapping for annual statements -
                    # see _QUARTERLY_EXTRA's comment in load_financial_statements.py; annual
                    # tables have no fiscal_quarter column to map it to. Before this fix, that
                    # expected, harmless omission logged a per-occurrence WARNING for every
                    # single annual row of every symbol - live-confirmed 40,050 warnings (plus
                    # 3,248 per-symbol summary warnings) from one load_financial_statements
                    # run, 100% of them this one field. That volume of pure noise drowns out
                    # genuinely actionable unmapped-field warnings for other statement types.
                    if sec_field == "fiscal_period" and self.period == "annual":
                        continue
                    symbol = r.get("symbol", "?")
                    if symbol not in unmapped_fields_per_symbol:
                        unmapped_fields_per_symbol[symbol] = set()
                    unmapped_fields_per_symbol[symbol].add(sec_field)
                    logger.warning(
                        f"[{self.table_name}] {symbol}: Unmapped SEC field '{sec_field}'. "
                        f"This field is present in SEC XBRL data but has no database column mapping. "
                        f"Check if field_mapping in load_financial_statements.py needs updating."
                    )
                    continue

                db_field = field_mapping[sec_field]
                if sec_field in getattr(self, "_fallback_only_fields", frozenset()) and db_field in row:
                    continue  # A higher-priority concept already populated this field
                if (
                    sec_field in getattr(self, "_reit_only_fallback_fields", frozenset())
                    and db_field in row
                    and r.get("symbol") in self._get_reit_symbols()
                ):
                    continue  # REIT filer: real lease revenue already populated this field
                if db_field not in self._schema_cols:
                    raise RuntimeError(
                        f"[{self.table_name}] Field mapping configuration error: SEC field '{sec_field}' "
                        f"maps to '{db_field}' but '{db_field}' not in target schema. "
                        f"Check field_mapping and schema definitions."
                    )
                if db_field == "data_unavailable":
                    row["data_unavailable"] = value
                elif db_field == "reason":
                    row["reason"] = value
                else:
                    precision_scale = self._get_field_precision_scale(db_field)
                    if precision_scale is not None and not self._validate_numeric_precision(
                        value, precision=precision_scale[0], scale=precision_scale[1]
                    ):
                        symbol = r.get("symbol", "?")
                        logger.error(
                            f"[{self.table_name}] {symbol}: Numeric overflow in field '{db_field}' "
                            f"(value={value}). Field is NUMERIC{precision_scale}. Marking data_unavailable."
                        )
                        row["data_unavailable"] = True
                        row["reason"] = f"Numeric overflow in {db_field}"
                    else:
                        row[db_field] = value

            # free_cash_flow has no direct XBRL concept (FCF is a non-GAAP measure SEC
            # filers don't tag) - derive it from operating_cash_flow - capex, the standard
            # formula, whenever both real inputs are present. Confirmed live 2026-08-03:
            # annual_cash_flow.free_cash_flow was NULL for every row in the table (0/206)
            # despite operating_cash_flow and capex both being populated - nothing ever
            # computed it, cascading into fcf_yield/fcf_to_net_income/fcf_growth_yoy being
            # NULL universe-wide downstream in load_value_quality_growth_metrics.py.
            if self.statement_type == "cashflow":
                ocf = row.get("operating_cash_flow")
                capex = row.get("capex")
                if ocf is not None and capex is not None:
                    row["free_cash_flow"] = ocf - capex

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

        # Report unmapped fields summary (Issue #4 fix: Surface data mapping gaps)
        if unmapped_fields_per_symbol:
            for symbol in sorted(unmapped_fields_per_symbol.keys()):
                unmapped_set = unmapped_fields_per_symbol[symbol]
                logger.warning(
                    f"[{self.table_name}] {symbol}: Found {len(unmapped_set)} unmapped SEC XBRL concepts: "
                    f"{sorted(unmapped_set)}. These fields are being discarded. "
                    f"If any are important metrics, add mappings to field_mapping dict."
                )

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
