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

# FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
# these 4 sec_fields are the only concepts that can each independently BE a filer's
# entire consolidated revenue (as opposed to a narrower ASC-606 fee line, REIT lease
# income, or bank-thrift interest-income concept, all of which have their own established
# SIC/fallback-only carve-outs elsewhere in this function and are deliberately NOT
# included here). For these 4 specifically, "first-populated wins" (the general rule
# everywhere else in this function) is provably wrong: live-confirmed via real SEC
# companyfacts JSON that BBVA (a bank with a minority insurance subsidiary) tags a real
# but small, sometimes NEGATIVE "insurance_revenue" fact (its segment's net result, not a
# revenue total) that shares the EXACT SAME filed date as its own real ~EUR26B total
# (tagged "interest_revenue_expense") - _aggregate_concepts's tiebreak in
# sec_statements.py keeps whichever fact was inserted first on an exact filed-date tie,
# so the file's own "last-listed wins" convention silently never fires for same-filing
# collisions like this one. HSBC independently confirmed the same bug in its less
# obviously-wrong positive form: its real ~$65-68B total ("revenues", sourced from
# RevenueAndOperatingIncome) lost to its own ~$2-3B insurance-segment figure the same
# way. Since which candidate is the TRUE total varies per filer (BBVA needs
# interest_revenue_expense, HSBC/UBS need revenues, AEG - a genuine insurer with no
# bank-interest concepts at all - needs insurance_revenue), no fixed concept-priority
# ordering works for all of them; magnitude does, because a real consolidated total can
# never be smaller than a genuine sub-line of itself, and is never negative when a
# positive alternative exists.
#
# WIDENED 2026-08-31 (goal session, real-money-readiness audit - recovered from a stranded
# unmerged worktree commit, d175737e3, found never reached main despite memory citing it as
# FIXED; live-reverified against current main before porting): added sales_revenue_net/
# sales_revenue_goods_net, previously fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS in
# load_financial_statements.py - that set's own comment documents why they were made
# fallback-only in the first place: KARO/AGCO-style filers where a much-larger real total
# already sits in "revenue" from a normal concept and these two must never clobber it).
# Fallback-only cuts only one way ("never overwrite an already-populated value") -
# live-confirmed that's wrong when the ALREADY-populated value is itself the broken one.
# ANDE (Andersons, SIC 5153): FY2013-2015 "Revenues" tags a small, wrong sub-line
# ($882K/$6.159M/$5.447M) while "SalesRevenueNet" correctly holds the real total
# ($5.605B/$4.540B/$4.198B, confirmed via real SEC companyconcept JSON) - "revenues" (a
# magnitude-candidate field, so it wins "revenue" first) permanently blocked
# sales_revenue_net's correct, much larger figure from ever being considered. PRGO
# (Perrigo, SIC 2834) independently confirmed the identical shape for FY2013: real
# "Revenues"=$800,000 vs real "SalesRevenueGoodsNet"/"SalesRevenueNet"=$3,539,800,000.
# TKR (Timken, SIC 3562) independently reconfirms it again FY2015: DB showed $20.6M vs real
# SalesRevenueGoodsNet=$2,872,300,000 (139x understated) - live-verified via SEC
# companyconcept JSON before this port. Moving both into this magnitude-resolved group
# fixes all three (whichever total-candidate concept has the LARGEST value now wins,
# regardless of processing order) while provably not regressing KARO/OLDCO
# (test_sec_sales_revenue_net_not_overwritten.py): the "revenue" seed-from-existing-row-
# value step below still protects a real, larger, already-written total from a smaller
# candidate exactly the same as it always has for the original 4 fields.
_REVENUE_TOTAL_CANDIDATE_FIELDS = frozenset(
    {
        "revenues",
        "insurance_revenue",
        "revenues_net_of_interest_expense",
        "interest_revenue_expense",
        "sales_revenue_net",
        "sales_revenue_goods_net",
    }
)


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

    # Column names are validated against a fixed literal set (not user/DB-supplied) before
    # ever reaching an f-string SQL fragment - see the retry-set query below.
    #
    # FIX 2026-08-29 (goal: "full data" audit continuation, oil & gas capex follow-up):
    # was a single field per statement type, so the 2026-08-18 AVAV retry-gap fix (see
    # fetch_incremental's comment below) only ever re-included a fiscal year whose ONE core
    # field was NULL - a gap in any OTHER mapped field (e.g. cashflow's `capex`) never
    # qualified, so a fiscal year already at data_unavailable=FALSE with a populated
    # operating_cash_flow but NULL capex could never be retried again, no matter how many
    # later concept-mapping fixes landed. Live-confirmed for the SIC-1311 E&P symbols
    # targeted by [[oil_gas_capex_xbrl_concepts_fixed_20260829]]: a scoped `--symbols`
    # backfill for APA/FANG/RRC/etc. logged a clean "Fetched 7 annual cashflow row(s)" and
    # a "PASS" completion, yet `annual_cash_flow.capex`/`updated_at` stayed untouched - the
    # new oil & gas concepts DID resolve a real, non-NULL FY2025 capex value on this run's
    # raw SEC fetch (confirmed via a direct `get_cash_flow()` call outside the loader), but
    # `fetch_incremental`'s watermark filter dropped FY2025 anyway because
    # `unavailable_years` only ever checked `operating_cash_flow IS NULL`, already false for
    # every affected symbol. `capex` added as a second retry-trigger field for cashflow - a
    # real, widely-scored value (feeds free_cash_flow/fcf_yield/intrinsic_value_per_share),
    # not cosmetic, so it deserves the same "keep retrying until a real value lands"
    # treatment as the statement's primary field. income/balance left as single-field
    # tuples (unchanged behavior) - no equivalent secondary-field gap found for them yet.
    _CORE_FIELD_BY_STATEMENT_TYPE: dict[str, tuple[str, ...]] = {
        "income": ("net_income",),
        "balance": ("stockholders_equity",),
        "cashflow": ("operating_cash_flow", "capex"),
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
        # See the transform() copy-loop comment on _reit_exclusive_fields: a stricter
        # category for concepts (e.g. operating_lease_lease_income) that must never write
        # their target db_field for a non-REIT symbol at all, unlike
        # _reit_only_fallback_fields above whose "unaffected for non-REIT" behavior is
        # correct for concepts that should also win normally via the general chain.
        self._reit_exclusive_fields: frozenset[str] = cast(
            frozenset[str], cfg.get("reit_exclusive_fields", frozenset())
        )
        self._reit_symbols: frozenset[str] | None = None
        self._depository_institution_symbols: frozenset[str] | None = None
        self._insurance_symbols: frozenset[str] | None = None

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

    def _get_insurance_symbols(self) -> frozenset[str]:
        """Bulk-fetch insurance-carrier symbols (SIC 6311/6321/6331/6351/6361/6399) once per
        loader run, not per-row.

        FIXED 2026-08-22 (goal session: "Implausible / rejected value" coverage audit):
        insurance contracts are explicitly out of ASC 606's scope (covered by ASC 944/IFRS 17
        instead), so an insurer's "RevenueFromContractWithCustomer*" tag - when present at
        all - is inherently a minor ancillary fee-revenue stream (policy administration fees
        etc.), never the real premium/investment-income-driven total. The general priority
        chain legitimately lets this concept supersede "Revenues" for ordinary post-2018
        filers (see test_sec_reit_lease_revenue_not_overwritten.py's AAPL case), which is
        exactly wrong here - same failure shape as the REIT case above, different industry.
        Live-confirmed via MCY (Mercury General, a P&C insurer, SIC 6331): real "Revenues"
        FY2025 = $5.99B (matches its known real revenue), but real
        RevenueFromContractWithCustomerIncludingAssessedTax FY2025 = $29.6M (a minor fee
        line) was clobbering it - stored "revenue" was $29.6M, a ~200x understatement that
        fed a nonsensical >1800% net_margin into the implausible_ratio guard (correctly
        rejecting the ratio, for the wrong underlying reason).
        """
        # getattr: see _get_depository_institution_symbols's identical comment - some
        # existing test fixtures construct this loader via __new__, bypassing __init__.
        cached: frozenset[str] | None = getattr(self, "_insurance_symbols", None)
        if cached is None:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol FROM company_info_sec WHERE sic_code IN (6311, 6321, 6331, 6351, 6361, 6399)"
                )
                cached = frozenset(row[0] for row in cur.fetchall())
            self._insurance_symbols = cached
        return cached

    # FIXED 2026-08-24 (goal: "Margin of Safety (DCF) / Cash flow data unavailable" audit):
    # a small, individually-verified allowlist of insurers confirmed to have ZERO capex-
    # related XBRL concept (PP&E family, REIT family, or the insurer investment-real-estate
    # concepts - see sec_statements.py's get_cash_flow() comment) across their entire
    # filing history. NOT SIC-based like DEPOSITORY_INSTITUTION_SIC_CODES below - insurance
    # SIC codes (6311/6321/6331/6351/6361/6399) are NOT uniformly capex-less the way
    # banking is: ALL (Allstate) and HIG (Hartford) both tag real, material
    # "PaymentsToAcquirePropertyPlantAndEquipment" ($267M/$215M FY2023). Source of truth
    # for the verification evidence: load_sec_valuations.py's
    # SecValuationsLoader.INSURANCE_CAPEX_EXEMPT_SYMBOLS (same list, kept in sync manually -
    # same duplication convention already used for DEPOSITORY_INSTITUTION_SIC_CODES's SIC
    # codes between this file and that one).
    _INSURANCE_CAPEX_EXEMPT_SYMBOLS = frozenset(
        {
            "CRBG",
            "FG",
            "GNW",
            "JXN",
            "LNC",
            "PRU",
            "AFL",
            "CNO",
            "AFG",
            "AXS",
            "CB",
            "EG",
            "GBLI",
            "HG",
            "HMN",
            "KG",
            "RNR",
            "SPNT",
            "AGO",
            "ORI",
            "OSG",
        }
    )

    def _get_depository_institution_symbols(self) -> frozenset[str]:
        """Bulk-fetch bank/depository-institution symbols once per loader run, not per-row.

        FIXED 2026-08-22 (goal session: "Missing SEC/XBRL data" coverage audit): banks never
        tag a "CapitalExpenditures" XBRL concept in any fiscal year - live-confirmed via JPM,
        BAC, MS, WFC, PNC's real companyfacts JSON (capex NULL across every year 2007-2026).
        Same SIC codes as load_sec_valuations.py's DEPOSITORY_INSTITUTION_SIC_CODES - see that
        class attribute's comment for the full rationale (a bank's capital allocation is
        fundamentally different from an industrial filer's, so treating its genuinely-absent
        capex as 0 for the free_cash_flow computation just below is the standard equity-
        research convention for this sector, not a guess).
        """
        # getattr (not a direct self._depository_institution_symbols read): mirrors the
        # _fallback_only_fields/_reit_only_fallback_fields defensive-getattr pattern used
        # elsewhere in this file - some existing test fixtures construct this loader via
        # __new__, bypassing __init__ entirely, so the attribute this method's own __init__
        # assignment sets may not exist yet.
        cached: frozenset[str] | None = getattr(self, "_depository_institution_symbols", None)
        if cached is None:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol FROM company_info_sec WHERE sic_code IN (6020, 6021, 6022, 6029, 6035, 6036, 6712)"
                )
                cached = frozenset(row[0] for row in cur.fetchall())
            self._depository_institution_symbols = cached
        return cached

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
                # NOTE 2026-08-29: _CORE_FIELD_BY_STATEMENT_TYPE holds a tuple of fields per
                # statement type (was a single field - see its own comment for why cashflow
                # now carries 2). Issue one retry-candidate query per field so a fiscal year
                # missing ANY of them (not just the first-listed one) gets retried.
                for core_field in self._CORE_FIELD_BY_STATEMENT_TYPE.get(self.statement_type, ()):
                    cur.execute(
                        f"SELECT fiscal_year FROM {self.table_name} "
                        f"WHERE symbol = %s AND data_unavailable = FALSE AND {core_field} IS NULL",
                        (symbol,),
                    )
                    unavailable_years |= {r[0] for r in cur.fetchall() if r[0] is not None}

            # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage
            # audit, CHTR live-confirmed): a fiscal year can be written as real
            # (data_unavailable=FALSE) from a partial-year/interim SEC fact that an
            # earlier version of this extraction pipeline mistakenly accepted as a
            # complete annual figure, then later have that acceptance bug fixed - but
            # nothing ever retracted the row THAT bug already wrote, since the normal
            # `fiscal_year > since_year` filter only ever ADDS newer years, never
            # removes a now-unconfirmed one. Live-confirmed via CHTR: annual_income_
            # statement.fiscal_year=2026 held a real-looking $27.123B "revenue" (written
            # 2026-08-01, before whatever later fix stopped this), but CHTR's fiscal
            # year runs calendar-year (ends December 31) so FY2026 cannot have a real
            # 10-K yet - and a fresh, full-history refetch (`rows` here, unfiltered by
            # `since`) genuinely returns no FY2026 entry at all today, confirming the
            # stored row is a stale orphan, not a legitimate gap. This silently poisoned
            # every downstream revenue-growth calculation that anchors on "the most
            # recent fiscal year" (CHTR's revenue_growth_1y computed a nonsensical
            # -50.48%, comparing the stub's implausibly low value against the real
            # FY2025 total). `rows` is always the symbol's FULL current-truth history
            # (see the comment on `unavailable_years` above) - if it doesn't reach as
            # far as a fiscal year the DB currently marks available, that year is no
            # longer backed by any data this extraction pipeline can produce and must be
            # retracted, the same "explicit, not silent" governance principle every
            # other data_unavailable marker in this codebase already follows. Bounded to
            # fiscal years the DB has but a full unfiltered refetch does NOT reproduce -
            # never touches a year genuinely absent from `rows` because SEC transiently
            # failed to answer for it this run (that year simply isn't compared against
            # at all, since the DB row for it - if any - is untouched by this max()
            # check unless it's the one exceeding the fresh maximum).
            fetched_fiscal_years = {r["fiscal_year"] for r in rows if r.get("fiscal_year") is not None}
            if fetched_fiscal_years:
                max_fetched_fiscal_year = max(fetched_fiscal_years)
                with DatabaseContext("write") as write_cur:
                    write_cur.execute(
                        f"UPDATE {self.table_name} SET data_unavailable = TRUE, "
                        f"reason = 'stale_fiscal_year_not_confirmed_by_full_sec_refetch', "
                        f"updated_at = NOW() "
                        f"WHERE symbol = %s AND data_unavailable = FALSE AND fiscal_year > %s",
                        (symbol, max_fetched_fiscal_year),
                    )
                    if write_cur.rowcount:
                        logger.warning(
                            f"[{self.table_name}] {symbol}: retracted {write_cur.rowcount} stale fiscal-year "
                            f"row(s) beyond the freshest full-history fiscal_year ({max_fetched_fiscal_year}) "
                            f"a complete refetch actually reproduces."
                        )

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
            # FIXED 2026-08-31 (goal session continued: ANDE live-confirmed same clobber
            # shape as CHTR/HTLD but via the EXCLUDING_assessed_tax sibling instead -
            # revenue_from_contract_with_customer_excluding_assessed_tax=$1.531B vs. real
            # "Revenues"=$11.009B, a ~7x understatement). Tracks which sec_field most
            # recently wrote "revenue" so the excluding_assessed_tax magnitude guard below
            # can tell "an earlier normal concept like revenues already holds the real
            # total" (must protect it) apart from "including_assessed_tax already wrote a
            # smaller value that excluding_assessed_tax is SUPPOSED to override regardless
            # of magnitude" (must NOT protect it - see that guard's own comment).
            _revenue_source_sec_field: str | None = None

            field_mapping = self._field_mapping
            # FIXED 2026-08-22 (goal session: "Implausible / rejected value" coverage audit):
            # REIT-only-fallback concepts (revenue_from_contract_with_customer_*, the minor
            # ASC-606 fee-income line - see test_sec_reit_lease_revenue_not_overwritten.py)
            # only skip when "revenue" is ALREADY populated - which depends entirely on
            # whichever concept happened to occupy an earlier position in `r`'s insertion
            # order (itself just _aggregate_concepts's own concepts-list iteration order in
            # sec_statements.py, an implementation detail, not a deliberate priority signal).
            # Live-confirmed via CPT (Camden Property Trust, a real REIT, SIC 6798): reports
            # NO "Revenues"/"SalesRevenueNet" at all, only a small real ASC-606 fee-income
            # figure ($12.967M) AND the correct, much larger real lease-revenue figure under
            # operating_lease_lease_income ($1.574B, live-confirmed via real companyfacts
            # JSON) - because the ASC-606 concept happens to sit earlier in the concepts
            # list (so gets inserted into `r` first), it won the "not yet populated" check
            # and permanently blocked the correct, REIT-exclusive figure from ever writing
            # (operating_lease_lease_income's OWN fallback-only-for-REIT check then saw
            # "revenue" already populated and skipped too) - a ~121x understatement with no
            # data_unavailable/reason flag anywhere, silently corrupting every downstream
            # margin/ratio computation (net_margin, roic_pct, etc. all showed nonsensical
            # thousands-of-percent values, correctly caught by the implausible_ratio guard,
            # but for the wrong underlying reason). Process `_reit_only_fallback_fields`
            # keys LAST (stable sort - relative order otherwise unchanged) so the real REIT
            # lease-revenue concept always gets first claim on "revenue" for confirmed REITs,
            # regardless of incidental dict-insertion order.
            _reit_only_fallback: frozenset[str] = getattr(self, "_reit_only_fallback_fields", frozenset())
            ordered_fields = sorted(r.items(), key=lambda kv: kv[0] in _reit_only_fallback)
            # See _REVENUE_TOTAL_CANDIDATE_FIELDS's module-level comment for why these 4
            # fields specifically need magnitude-based resolution instead of the general
            # first-populated-wins/fallback-only rule this loop uses everywhere else.
            revenue_total_best: dict[str, float] = {}
            for sec_field, value in ordered_fields:
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
                if sec_field in _REVENUE_TOTAL_CANDIDATE_FIELDS and db_field == "revenue":
                    # Seed from any value a non-magnitude field already wrote (e.g. a
                    # mortgage REIT's interest_income_operating), so this group only ever
                    # OVERWRITES with a larger positive candidate - never blind to what's
                    # already there, and never regresses an existing correct larger value.
                    if db_field not in revenue_total_best and db_field in row:
                        existing = row[db_field]
                        if isinstance(existing, (int, float, Decimal)):
                            revenue_total_best[db_field] = float(existing)
                    if isinstance(value, (int, float, Decimal)) and float(value) > 0:
                        fvalue = float(value)
                        current_best = revenue_total_best.get(db_field)
                        if current_best is None or fvalue > current_best:
                            revenue_total_best[db_field] = fvalue
                            row[db_field] = value
                            if db_field == "revenue":
                                _revenue_source_sec_field = sec_field
                    continue
                if sec_field in getattr(self, "_fallback_only_fields", frozenset()) and db_field in row:
                    continue  # A higher-priority concept already populated this field
                if (
                    sec_field in getattr(self, "_reit_only_fallback_fields", frozenset())
                    and db_field in row
                    and (
                        r.get("symbol") in self._get_reit_symbols()
                        or r.get("symbol") in self._get_insurance_symbols()
                        # FIXED 2026-08-22 (goal session: real-money-readiness audit,
                        # following the AROW/community-bank revenue-gap investigation):
                        # same failure shape as the REIT/insurance cases above, bank/thrift
                        # trigger this time. Depository institutions' real total revenue
                        # (net interest income + noninterest income) is out of ASC 606's
                        # scope, so their ASC-606 contract-revenue tag - when present at
                        # all - is a minor ancillary fee-income line (deposit/wealth-
                        # management fees), never the total. Live-confirmed via WAFDP
                        # (Washington Federal, SIC 6035): real interest_and_dividend_
                        # income_operating FY2018=$607.1M/FY2019=$671.5M (growing,
                        # consistent with real net_income) vs. revenue_from_contract_
                        # with_customer_excluding_assessed_tax FY2018=$25.9M/FY2019=
                        # $24.9M (a minor fee line) was clobbering it - stored "revenue"
                        # was the $25.9M figure, a ~23x understatement. A DB-wide scan
                        # (bank/thrift SIC codes, revenue < 80% of net_income) found 40
                        # more rows with the same signature (ALLY, AMTB, AUBN, and
                        # others).
                        or r.get("symbol") in self._get_depository_institution_symbols()
                    )
                ):
                    # REIT filer: real lease revenue already populated this field.
                    # Insurance filer (2026-08-22 fix): real "Revenues" (premiums + investment
                    # income) already populated this field - see _get_insurance_symbols's
                    # docstring for why ASC 606's contract-revenue concept must not supersede
                    # it, same reasoning as the REIT case, different XBRL concept trigger.
                    # Depository institution (2026-08-22 fix): real interest-income-derived
                    # revenue already populated this field - see this branch's own comment
                    # above for the live-verified WAFDP case.
                    continue
                # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage
                # audit): the REIT/insurance/depository gate above assumes "IncludingAssessedTax
                # as a narrow sub-line, not the real total" is an industry-specific (SIC-coded)
                # failure mode - false. Live-confirmed via three ordinary, non-REIT/insurance/
                # bank filers: CHTR (Charter Communications, SIC 4841 cable) tags a real,
                # current, correct "Revenues" every year through FY2025 ($54.607B/$55.085B/
                # $54.774B for FY2023-2025) while ALSO tagging
                # RevenueFromContractWithCustomerIncludingAssessedTax with a much narrower
                # same-year figure ($993M/$941M/$889M); HTLD (Heartland Express, SIC 4213
                # trucking) shows the identical shape via the same concept ($58.1M FY2025 vs. a
                # real ~$863M total); ANDE (Andersons, SIC 5153 grain/agribusiness) shows the
                # SAME shape via the sibling ExcludingAssessedTax concept instead ($1.531B
                # FY2025 vs. real "Revenues"=$11.009B, a ~7x understatement). None of these
                # filers are REIT/insurer/depository, so the SIC-gated branch above never fires,
                # and the general "last-listed-wins" priority let the narrow figure silently
                # clobber the correct total - up to a ~61x understatement with no
                # data_unavailable/reason flag anywhere, corrupting every downstream revenue-
                # based metric (P/S, revenue growth, all margin ratios) for these and up to 63
                # other real symbols sharing this fingerprint (see the DB-wide "latest fiscal
                # year revenue present but cost_of_revenue/gross_profit both NULL" scan this
                # goal session ran). A real consolidated revenue total can never be smaller than
                # a genuine sub-line of itself, so if a field a normal-priority concept already
                # wrote to "revenue" is LARGER than either ASC-606 concept's incoming value, the
                # incoming value is never allowed to shrink it, regardless of SIC code. This does
                # NOT weaken the AAPL case (test_sec_reit_lease_revenue_not_overwritten.py's
                # test_non_insurer_still_uses_normal_priority_asc606_wins): there the ASC-606
                # figure is LARGER than the legacy "Revenues" figure (391B > 300B), so neither
                # guard below fires and normal overwrite still applies.
                #
                # The excluding_assessed_tax guard (added same pass, ANDE fix) additionally
                # checks `_revenue_source_sec_field` (tracked at every "revenue" write site
                # above) is NOT the including_assessed_tax concept: excluding_assessed_tax is
                # always processed strictly AFTER including_assessed_tax (concept-list order in
                # sec_statements.py), so it may see "revenue" already holding including_assessed_
                # tax's own (smaller, by definition) value -
                # test_load_financial_statements_revenue_precedence.py's
                # test_tax_exclusive_revenue_wins_when_both_concepts_reported requires
                # excluding_assessed_tax to keep unconditionally overwriting THAT specific value
                # even though it's smaller (excluding tax is deliberately preferred as "the
                # standard net-revenue measure most filers use" - a precedence rule, not a
                # magnitude one). The source check lets that precedence stand while still
                # protecting a genuinely different, larger, earlier-written total like ANDE's
                # "Revenues".
                if (
                    db_field in row
                    and isinstance(row[db_field], (int, float, Decimal))
                    and isinstance(value, (int, float, Decimal))
                    and float(row[db_field]) > float(value)
                    and (
                        sec_field == "revenue_from_contract_with_customer_including_assessed_tax"
                        or (
                            sec_field == "revenue_from_contract_with_customer_excluding_assessed_tax"
                            and _revenue_source_sec_field
                            != "revenue_from_contract_with_customer_including_assessed_tax"
                        )
                    )
                ):
                    continue
                # BUG FOUND 2026-08-19 (goal: "no SEC data"/loader audit): a separate,
                # stricter category from _reit_only_fallback_fields above. That set's
                # "skip only when (already populated AND symbol is a REIT)" semantics is
                # correct for concepts that should ALSO win normally for non-REIT filers
                # via the general priority chain (e.g. the ASC-606 contract-revenue
                # concepts - see test_sec_reit_lease_revenue_not_overwritten.py's AAPL
                # case, where that concept legitimately supersedes "revenues" for ordinary
                # filers too). It is NOT correct for a concept like
                # operating_lease_lease_income, whose real-world meaning for a non-REIT
                # filer is a completely unrelated, minor line item (real-estate sublease
                # income) that must never touch "revenue" at all, REIT-populated-check
                # or not. Live-confirmed via IHRT (iHeartMedia, SIC 7812, not a REIT): its
                # real annual "Revenues" ($3.75B/$3.85B/$3.86B for FY2023-2025) was
                # silently clobbered by its tiny sublease income under
                # OperatingLeaseLeaseIncome ($2.01M/$787K/$562K - exact match to the
                # corrupted DB values), a ~1000x understatement with no
                # data_unavailable/reason flag anywhere - because that concept was lumped
                # into the same reit_only_fallback_fields set as the ASC-606 concepts,
                # whose "unaffected for non-REIT" behavior is correct for THEM but wrong
                # for this one. This new set unconditionally skips (never writes) for any
                # symbol that isn't a confirmed REIT, and behaves as fallback-only
                # (skip if already populated) for symbols that are.
                if sec_field in getattr(self, "_reit_exclusive_fields", frozenset()):
                    if r.get("symbol") not in self._get_reit_symbols() or db_field in row:
                        continue
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
                        if db_field == "revenue":
                            _revenue_source_sec_field = sec_field

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
                # FIXED 2026-08-22 (goal session: "Missing SEC/XBRL data" coverage audit):
                # depository institutions (banks) never tag a "CapitalExpenditures" concept
                # at all - see _get_depository_institution_symbols's docstring for the full
                # rationale. Without this, free_cash_flow (and everything derived from it:
                # fcf_yield, margin_of_safety, intrinsic_value_per_share) was structurally
                # uncomputable forever for the entire banking sector, not a transient
                # extraction gap a future fetch could fix.
                # FIXED 2026-08-24 (same audit, insurance-sector continuation): see
                # _INSURANCE_CAPEX_EXEMPT_SYMBOLS's docstring above for why this is a
                # verified symbol allowlist, not a SIC-code check like the bank case.
                if capex is None and (
                    r.get("symbol") in self._get_depository_institution_symbols()
                    or r.get("symbol") in self._INSURANCE_CAPEX_EXEMPT_SYMBOLS
                ):
                    capex = 0
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

            # DEFENSIVE BACKFILL (2026-08-24, real-money-readiness audit): fetch_incremental()
            # sets r.setdefault("data_source", "sec_audited")/_try_yfinance_fallback() sets
            # r["data_source"]="yfinance" on the RAW rows before transform() runs, and the
            # per-field loop above copies it through via the identity field_mapping entry
            # ("data_source" -> "data_source", see _MARKER_FIELDS in load_financial_statements.py) -
            # but that copy only happens if "data_source" survives as a literal key on this
            # specific `r`/`row` pair through every skip/continue branch above. Live-confirmed
            # via DB audit: real-data annual_balance_sheet/quarterly_balance_sheet rows
            # (SLN, UCB, SKT, XPL, and others - genuine SEC-EDGAR filers) were written with
            # data_source=NULL as recently as 2026-08-22, well after migration 1202's tagging
            # fix was believed to have closed this gap - bulk_insert_manager.py's CSV writer
            # (csv.DictWriter, default restval='') turns any row dict missing this key into an
            # empty string, and COPY's FORCE_NULL then turns that into a real DB NULL,
            # indistinguishable from "we don't know the source" for governance purposes. Rather
            # than fully re-derive which specific skip branch above drops the key for which
            # symbols, close the gap unconditionally here: every non-marker row leaving
            # transform() gets a source tag, exactly mirroring the raw-row guarantee this class
            # already makes upstream. Marker rows (data_unavailable=True) are untouched -
            # they correctly carry no data_source since there is no data to source-tag.
            if not row.get("data_unavailable"):
                row.setdefault("data_source", "sec_audited")

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
