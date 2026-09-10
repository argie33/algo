#!/usr/bin/env python3
"""Consolidated Financial Statements Loader - SEC EDGAR filing data.

Loads financial statements (income, balance sheet, cash flow) across periods
(annual, quarterly) from SEC EDGAR using consolidated statements.

This consolidated loader replaces 8 separate loaders:
  - load_income_statement.py (annual/quarterly/ttm)
  - load_balance_sheet.py (annual/quarterly/ttm)
  - load_cash_flow.py (annual/quarterly/ttm)

NOTE: 'ttm' remains in the single-combo config tables for backward
compatibility, but the fetch path has never supported it (loader init rejects
period='ttm'); the 'all' mode no longer attempts it.

The statement type and period are determined by environment variables set by terraform:
  LOADER_STATEMENT_TYPE: income, balance, or cashflow
  LOADER_PERIOD: annual, quarterly, or ttm

Run:
    python3 load_financial_statements.py
    (with LOADER_STATEMENT_TYPE and LOADER_PERIOD env vars set by terraform)

Or directly:
    LOADER_STATEMENT_TYPE=income LOADER_PERIOD=annual python3 load_financial_statements.py
"""

import os
import sys
import time

from loaders.loader_helper import setup_imports
from loaders.timeout_config import configure_socket_timeout

setup_imports()

import logging  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

from loaders.helpers.financial_statements_custom_extension_fallbacks import (  # noqa: E402
    apply_custom_cashflow_extensions,
    apply_custom_debt_extensions,
    apply_custom_income_extensions,
)
from loaders.helpers.financial_statements_prefetch import start_companyfacts_prefetch  # noqa: E402
from loaders.helpers.financial_statements_q4_sweeps import Q4DerivationSweepMixin  # noqa: E402
from loaders.helpers.financial_statements_share_count_validation import (  # noqa: E402
    FinancialStatementsShareCountValidationMixin,
)
from loaders.helpers.financial_statements_value_validation import (  # noqa: E402
    FinancialStatementsValueValidationMixin,
)
from loaders.helpers.sec_base import SecEdgarStatementLoader  # noqa: E402
from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.sec_edgar import SecEdgarClient  # noqa: E402
from utils.external.sec_statements_shared import has_unsupported_currency_only_fact  # noqa: E402
from utils.loaders.enum_validator import validate_period, validate_statement_type  # noqa: E402

# Explicit re-export: loaders/financial_statements/{sweeps,runner}.py import
# DatabaseContext/run_loader from this module at call time (to avoid a circular
# import with ConsolidatedFinancialStatementsLoader, defined further down in this
# file) rather than from their own source modules directly - mypy's
# --no-implicit-reexport requires this to be listed explicitly.
__all__ = [
    "DatabaseContext",
    "run_loader",
]

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)

# FIXED 2026-09-03 (goal session: "implausible values" audit, following up
# [[etn_etf_trust_shared_cik_implausible_financials_found_not_fixed_20260903]]): every
# `etf_symbols` ticker below shares its resolved SEC CIK with at least one OTHER
# `etf_symbols` ticker - an ETN issued under its issuing bank's own CIK (AMJB/VYLD ->
# JPMorgan, CIK 19617), or a series within a multi-fund umbrella-trust CIK (ProShares
# Trust II, Teucrium Commodity Trust, US Commodity Funds Trust, etc). A shared CIK means
# every companyfacts fetch under it returns the SAME JSON for every ticker mapped to it -
# there is no way to attribute that data to one specific fund/note series, so treating it
# as this symbol's own financials is a real, live-confirmed data-quality bug, not a
# hypothetical.
#
# Live-verified 2026-09-03 via a full `etf_symbols` x SEC `company_tickers.json`
# cross-reference (11 shared-CIK groups found among ~700 ETF tickers, this list = every
# member of every group) AND a direct DB check: every group with any overlapping-
# fiscal-year `annual_balance_sheet` data on file shows FULLY IDENTICAL total_assets/
# total_liabilities/stockholders_equity across every ticker in the group for every shared
# year, zero genuine divergence found anywhere - including CPER/USCI, which the memory
# file above had earlier (and wrongly) spot-checked as "distinct, plausible figures";
# a fuller live query here shows they share CIK 0001479247 and are byte-identical every
# fiscal year 2016-2019. The other 5 groups below (GBUG/TAPR, YSAG/YSAU, the 28-symbol
# Direxion leveraged-ETF-family CIK, BDCX/CEFD/HDLB/IFED/MLPR/MVRL) currently have zero
# overlapping fiscal-year data fetched at all (nothing wrong stored yet), but are the
# same structural shape and included pre-emptively so a future fetch can't silently
# reproduce this bug for them.
#
# Restricting the signal to "shares a CIK with ANOTHER member of etf_symbols" (never
# "shares a CIK with any ticker at all") is what keeps this list safe against the
# dual-class-share false-positive risk the memory file above originally flagged:
# legitimate one-company-two-tickers cases (GOOG/GOOGL, BRK.A/BRK.B) are never
# `etf_symbols` members, and this same cross-reference confirmed every genuinely-scored
# physical-commodity ETF this repo relies on (GLD/SLV/IAU/GLDM/AAAU/SGOL/PPLT/PALL/SIVR/
# GLTR/BNO/OUNZ/FGDL/IAUM) resolves to its own exclusive CIK - none of them appear here.
#
# A static, manually-verified registry (same convention as CUSTOM_DEBT_CONCEPTS/
# CUSTOM_CAPEX_CONCEPTS below) rather than a live per-run DB+SEC-API computation: this
# loader's fetch_incremental() runs for every symbol in the universe, and several existing
# unit tests construct it via __new__ (bypassing __init__) - a mandatory extra DB query in
# the hot path would both add real per-run cost across the whole universe for a check that
# only ever matters for ~70 known symbols, and break every test's fixed DatabaseContext
# mock sequence. Re-verify against a fresh company_tickers.json + DB cross-reference
# before adding new entries, same "verify before fix" discipline as the rest of this file.
SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS: frozenset[str] = frozenset(
    {
        # CIK 0000019617 (JPMorgan Chase & Co) - ETNs issued under the issuing bank's own CIK
        "AMJB",
        "VYLD",
        # CIK 0001415311 (ProShares Trust II) - 16 separate leveraged/inverse fund series
        "AGQ",
        "BOIL",
        "EUO",
        "GLL",
        "KOLD",
        "SCO",
        "SVXY",
        "UCO",
        "UGL",
        "ULE",
        "UVXY",
        "VIXM",
        "VIXY",
        "YCL",
        "YCS",
        "ZSL",
        # CIK 0001053092 (UBS ETRACS covered-call notes umbrella)
        "GLDI",
        "SLVO",
        "USOI",
        # CIK 0001610940 (Volatility Shares / futures umbrella)
        "BDRY",
        "BWET",
        # CIK 0001471824 (Teucrium Commodity Trust) - single-commodity fund series
        "BTCK",
        "CANE",
        "CORN",
        "SOYB",
        "TAGS",
        "WEAT",
        # CIK 0001479247 (US Commodity Funds Trust)
        "CPER",
        "USCI",
        # CIK 0001793497 (volatility-linked notes umbrella)
        "SVIX",
        "UVIX",
        # CIK 0000312070
        "GBUG",
        "TAPR",
        # CIK 0002087989
        "YSAG",
        "YSAU",
        # CIK 0001114446
        "BDCX",
        "CEFD",
        "HDLB",
        "IFED",
        "MLPR",
        "MVRL",
        # CIK 0000927971 (Direxion leveraged/inverse single-stock ETF family)
        "AIQD",
        "AIQU",
        "BERZ",
        "BNKD",
        "BNKU",
        "BULZ",
        "CARD",
        "CARU",
        "DULL",
        "FLYD",
        "FLYU",
        "FNGS",
        "FNGU",
        "GDXD",
        "GDXU",
        "HYGD",
        "HYGU",
        "JETD",
        "JETU",
        "LQDD",
        "LQDU",
        "NRGD",
        "NRGU",
        "OILD",
        "OILU",
        "SHNY",
        "SMHU",
        "WTID",
        "WTIU",
    }
)


def get_all_statement_configs() -> list[tuple[str, str]]:
    """Enumerate all statement/period combinations for 'all' mode.

    NOTE: the ("income", "ttm") and ("balance", "ttm") combos were removed
    2026-07-13. They never worked: SecEdgarStatementLoader.__init__ only
    accepts period 'annual'/'quarterly' and rejected period='ttm' at init on
    every run, so both combos crashed immediately and were merely logged as
    failed. Reinstating TTM requires actual TTM aggregation support in the
    SEC client/loader, not just a config entry here.

    Returns:
        List of (statement_type, period) tuples in execution order
    """
    return [
        ("income", "annual"),
        ("income", "quarterly"),
        ("balance", "annual"),
        ("balance", "quarterly"),
        ("cashflow", "annual"),
        ("cashflow", "quarterly"),
    ]


# SEC snake_cased concept -> DB column mappings (BUGFIX 2026-07-14: no config ever
# defined field_mapping, so SecEdgarStatementLoader.transform() raised "Field mapping
# not initialized" for EVERY symbol that returned rows - this loader had never
# persisted a real row since consolidation. Keys are _to_snake()'d XBRL concept names
# from utils/external/sec_statements.py; unmapped keys are skipped by transform().
# Multiple revenue concepts intentionally map to "revenue": transform iterates in row
# insertion order (= concepts-list order in sec_statements.get_income_statement()), so
# the last-listed concept present wins on overwrite - legacy Revenues < SalesRevenueNet
# < tax-inclusive ASC-606 tag < tax-exclusive ASC-606 tag (the standard net-revenue
# measure). See sec_statements.py's concept-list ordering comment for why the
# tax-inclusive concept must be mapped too, not just the exclusive one.
# REQUIRED metric fields per statement type - a row with all of these NULL has no usable
# data regardless of what optional fields it carries. Shared between transform() (governs
# freshly-fetched rows) and post_run()'s force-null flag sync (governs rows whose values
# were wiped by _reject_stale_fpi_currency_data/_reject_implausible_* without going back
# through transform() - see post_run() for why that sync is necessary).
_REQUIRED_STATEMENT_FIELDS = {
    "income": {"revenue", "net_income"},
    "balance": {"total_assets", "stockholders_equity"},
    "cashflow": {"operating_cash_flow"},
}

# ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): the (us-gaap concepts,
# ifrs-full concepts) checked by has_unsupported_currency_only_fact() when a required field
# above comes back NULL for a foreign private issuer - see that function's own docstring
# (sec_statements_shared.py) for the GGAL/BBAR/BSAC/... root cause this distinguishes from a
# genuine filing gap. Deliberately a minimal, high-confidence concept list per statement type
# (a false negative here just keeps the existing generic label - safe; a false positive would
# mislabel a genuinely-broken filing as "Legitimate / not applicable" - not safe), not the
# full alias lists sec_balance_sheet.py/sec_income_statement.py/sec_cash_flow.py use for
# actual value extraction.
_UNSUPPORTED_CURRENCY_CHECK_CONCEPTS: dict[str, tuple[list[str], list[str]]] = {
    "income": (["Revenues", "NetIncomeLoss"], ["Revenue", "ProfitLoss"]),
    "balance": (["Assets", "StockholdersEquity"], ["Assets", "Equity"]),
    "cashflow": (
        ["NetCashProvidedByUsedInOperatingActivities"],
        ["CashFlowsFromUsedInOperatingActivities"],
    ),
}

# SEC snake_cased concept -> DB column field mappings and per-statement/period config
# builders extracted to loaders/helpers/financial_statements_{income,balance,cashflow}_config.py
# (2026-09-07, file-size ratchet; split three ways rather than one combined module because a
# single combined module came in at 1394 lines - over the ratchet's 800-line cap for new files)
# - re-imported here so `from loaders.load_financial_statements import X` keeps working for
# every existing caller/test (see financial_statements_income_config.py's docstring for the
# full extraction rationale).
from loaders.helpers.financial_statements_balance_config import (  # noqa: E402
    _ANNUAL_BALANCE_EXTRA,  # noqa: F401
    _BALANCE_FIELD_MAPPING,  # noqa: F401
    _DEBT_FALLBACK_ONLY_FIELDS,  # noqa: F401
    _QUARTERLY_BALANCE_EXTRA,  # noqa: F401
    get_balance_sheet_config,
)
from loaders.helpers.financial_statements_cashflow_config import (  # noqa: E402
    _CASHFLOW_FIELD_MAPPING,  # noqa: F401
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,  # noqa: F401
    get_cash_flow_config,
)
from loaders.helpers.financial_statements_config_shared import (  # noqa: E402
    _MARKER_FIELDS,  # noqa: F401
    _QUARTERLY_EXTRA,  # noqa: F401
)
from loaders.helpers.financial_statements_income_config import (  # noqa: E402
    _INCOME_FIELD_MAPPING,  # noqa: F401
    _QUARTERLY_INCOME_EXTRA,  # noqa: F401
    _REIT_EXCLUSIVE_FIELDS,  # noqa: F401
    _REIT_REVENUE_FALLBACK_ONLY_FIELDS,  # noqa: F401
    _REVENUE_FALLBACK_ONLY_FIELDS,  # noqa: F401
    get_income_statement_config,
)


def get_statement_config(statement_type: str, period: str) -> dict[str, Any]:
    """Return configuration for a specific statement type and period.

    Args:
        statement_type: 'income', 'balance', 'cashflow', or 'all' (loads all combos)
        period: 'annual', 'quarterly', 'ttm', or ignored if statement_type='all'

    Returns:
        Dict with table_name, primary_key, schema_cols, field_mapping
    """
    # ISSUE #12 FIX: Enum validation
    if statement_type != "all":
        validate_statement_type(statement_type, context="get_statement_config")
        validate_period(period, context="get_statement_config")

    if statement_type == "income":
        return get_income_statement_config(period)
    elif statement_type == "balance":
        return get_balance_sheet_config(period)
    elif statement_type == "cashflow":
        return get_cash_flow_config(period)
    elif statement_type == "all":
        raise ValueError("Use load_all_statements() for statement_type='all', not get_statement_config()")
    else:
        raise ValueError(f"Unknown statement type: {statement_type}")


def load_all_statements() -> int:
    """Load all statement/period combinations in a single symbol-major pass.

    PERFORMANCE FIX 2026-07-13: the previous implementation was combo-major -
    it invoked run_loader() once per statement/period combo, and each of those
    runs iterated ALL ~5,300 symbols. Every combo is derived from the SAME SEC
    companyfacts JSON, so each symbol's multi-MB payload was re-downloaded once
    per combo: ~32,000 HTTP requests per run at the client's 2 req/s rate limit
    (hours of wasted wall time).

    Now a single pass iterates symbols in the outer loop and the six combos in
    the inner loop, sharing one SecEdgarClient whose small per-CIK LRU cache
    serves combos 2-6 from memory: one companyfacts GET per symbol per run
    (~5,300 requests, a ~6x reduction).

    Per-combo contracts preserved from the old run_loader/OptimalLoader.run path:
    - per-table run locks (a held lock skips just that combo, as before)
    - per-table data_loader_status RUNNING row + heartbeat + final status
    - per-table loader_execution_history rows and CloudWatch loader metrics
    - per-combo failure isolation and watermark-based incremental filtering
    - SEC client retry/backoff, rate limiting, and 404 semantics (unchanged)
    - exit code: 1 only when ALL combos failed (same aggregation as before)

    Returns:
        0 on success (statements loaded, marked unavailable, or combos skipped
        by a held lock), 1 on fatal error or when every combo failed
    """
    import argparse

    # CRITICAL FIX (Session 96): Use centralized timeout config at function start
    # so it's available for lock_ttl calculation below, not just in _load_all_statements helper
    from loaders.loader_timeout_config import get_loader_timeout

    sla_timeout_seconds = get_loader_timeout("financial_statements")

    from utils.db.local_file_lock import get_lock_manager
    from utils.db.pooled_connection_manager import PooledConnectionManager
    from utils.db.pooled_context_var import set_pooled_connection
    from utils.loaders.helpers import get_active_symbols

    # Mirror run_loader's CLI surface (the ECS task normally passes no args).
    parser = argparse.ArgumentParser(description="all financial statements loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all active symbols.")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="Ignored in all-mode: the shared 2 req/s SEC rate limit is the bottleneck; symbols run serially.",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="Refetch last N days instead of using watermark (BACKFILL_DAYS env var also honored).",
    )
    args = parser.parse_args()
    if args.parallelism != 1:
        logger.info("[FINANCIAL_STATEMENTS ALL MODE] --parallelism ignored (serial symbol-major pass)")

    combos = get_all_statement_configs()
    logger.info(
        f"[FINANCIAL_STATEMENTS ALL MODE] Loading {len(combos)} statement/period combinations (symbol-major pass)"
    )

    try:
        # One shared client = one companyfacts LRU cache, one SEC rate limiter,
        # and one ticker->CIK cache across all six combos.
        shared_client = SecEdgarClient()
        loaders = [
            ConsolidatedFinancialStatementsLoader(statement_type=st, period=p, sec_client=shared_client)
            for st, p in combos
        ]
        if args.backfill_days:
            for loader in loaders:
                loader._backfill_days = args.backfill_days
    except Exception as e:
        logger.error(
            f"[FINANCIAL_STATEMENTS ALL MODE] Loader construction failed: {type(e).__name__}: {str(e)[:500]}",
            exc_info=True,
        )
        return 1

    # Per-table run locks: same lock keys and skip semantics as OptimalLoader.run.
    from utils.db.dynamo_lock import DynamoDBLockManager
    from utils.db.local_file_lock import FileLockManager
    from utils.db.rds_lock import RDSLockManager

    # get_lock_manager() returns FileLockManager when LOCAL_MODE=true (all local dev runs
    # take this path - see utils/db/local_file_lock.py), else DynamoDBLockManager with
    # RDSLockManager fallback. All three duck-type the same acquire/release/
    # lock_duration_seconds interface used below. The RuntimeError handler further down
    # only fires when BOTH DynamoDB and RDS are unavailable in non-LOCAL_MODE (production)
    # runs - it does not apply to FileLockManager, which was already fixed for its former
    # Windows race condition (Session 281: atomic O_CREAT|O_EXCL file creation).
    lock_manager: FileLockManager | DynamoDBLockManager | RDSLockManager | None = None
    active: list[ConsolidatedFinancialStatementsLoader] = []
    try:
        lock_table = os.getenv(
            "LOADER_LOCKS_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
        )
        # TTL tied to the loader SLA (matches OptimalLoader.run): this all-mode pass
        # legitimately runs 45+ min, so a 1800s TTL would expire mid-run and allow a
        # concurrent instance to double-write. Locks are still released in finally.
        # Use centralized timeout config (now set at module top via get_loader_timeout)
        # instead of hardcoded fallback
        lock_ttl = sla_timeout_seconds
        try:
            lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
        except RuntimeError as ddb_err:
            # CRITICAL (Session 282): DynamoDB unavailable in a non-LOCAL_MODE (production)
            # run, and RDS fallback also failed - fail fast rather than proceed unlocked.
            # (LOCAL_MODE=true never reaches this branch: get_lock_manager() returns
            # FileLockManager directly without raising.)
            logger.critical(
                f"[FINANCIAL_STATEMENTS ALL MODE] DynamoDB lock unavailable: {ddb_err}. "
                f"Cannot proceed without distributed locking. Fix DynamoDB access or AWS credentials."
            )
            from algo.exceptions import LockAcquisitionError

            raise LockAcquisitionError(
                lock_key="financial_statements_all_mode",
                reason=f"DynamoDB lock manager unavailable: {ddb_err}",
                context={"loader": "financial_statements"},
            ) from ddb_err

        # get_lock_manager() either returns a real lock manager or raises RuntimeError
        # above (caught and re-raised as LockAcquisitionError) - it never returns None.
        # Narrows the type for mypy without weakening lock_manager's declared type, which
        # must stay Optional for _release_combo_locks()'s cleanup in the except block below.
        assert lock_manager is not None

        # SESSION 98 FIX: Lock TTL must match configured loader timeout.
        # financial_statements is configured for 360 minutes (21600s) in loader_timeout_config.py.
        # Lock TTL = loader_timeout * 1.1 (10% safety margin for cleanup grace period).
        lock_ttl_seconds = sla_timeout_seconds
        if lock_manager.lock_duration_seconds != lock_ttl_seconds:
            lock_manager.lock_duration_seconds = lock_ttl_seconds

        for loader in loaders:
            if lock_manager.acquire(lock_key=loader.table_name, timeout_seconds=5):
                active.append(loader)
            else:
                logger.warning(f"[{loader.table_name}] Skipping: another instance already running")
    except Exception as lock_err:
        logger.critical(f"[FINANCIAL_STATEMENTS ALL MODE] Lock initialization failed: {lock_err}")
        _release_combo_locks(lock_manager, active)
        return 1

    if not active:
        logger.warning("[FINANCIAL_STATEMENTS ALL MODE] All combos locked by other instances; nothing to do")
        return 0

    conn_manager = None
    started: list[ConsolidatedFinancialStatementsLoader] = []
    try:
        conn_manager = PooledConnectionManager("financial_statements_all_mode")
        set_pooled_connection(conn_manager.acquire())

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
        else:
            symbols = get_active_symbols(timeout_secs=60, exclude_etfs=True)

        start = time.time()
        for loader in active:
            _start_combo(loader, start, len(symbols))
            started.append(loader)

        # signal.signal() is last-registration-wins: of the per-loader
        # LoaderInfrastructure SIGTERM handlers, only the most recently
        # constructed loader's shutdown flag is actually set on SIGTERM.
        shutdown_watcher = loaders[-1]._infrastructure

        logger.info(f"[FINANCIAL_STATEMENTS ALL MODE] Starting load: {len(symbols)} symbols x {len(active)} combos")
        _run_symbol_pass(active, symbols, shutdown_watcher, start)

        duration = round(time.time() - start, 2)
        return _finalize_all(active, len(combos), len(symbols), duration, symbols)
    except Exception as e:
        logger.error(f"[FINANCIAL_STATEMENTS ALL MODE] Fatal: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        for loader in started:
            try:
                loader._log_execution_history("failed", str(e)[:500])
            except Exception as log_err:
                logger.warning(f"[{loader.table_name}] Failed to log execution history: {log_err}")
        return 1
    finally:
        for loader in started:
            loader._infrastructure.stop_heartbeat()
        try:
            set_pooled_connection(None)
            if conn_manager is not None:
                conn_manager.release()
        except Exception as cleanup_err:
            logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] Failed to clean up connection: {cleanup_err}")
        _release_combo_locks(lock_manager, active)
        for loader in loaders:
            loader.close()


def _start_combo(loader: "ConsolidatedFinancialStatementsLoader", start: float, symbols_total: int) -> None:
    """Per-combo run setup mirroring OptimalLoader.run (RUNNING status + heartbeat)."""
    loader._execution_start_time = start
    loader._stats["symbols_total"] = symbols_total
    loader._prepare_batch_context()
    loader._status_manager.mark_running()
    loader._infrastructure.start_heartbeat()


def _run_symbol_pass(
    active: list["ConsolidatedFinancialStatementsLoader"],
    symbols: list[str],
    shutdown_watcher: Any,
    start: float,
) -> None:
    """Symbol-major pass: for each symbol, run every statement/period combo.

    Combo failures are isolated per symbol and per combo (mirroring the old
    independent per-combo runs: one combo failing a symbol never blocks the
    other combos), and are counted in each loader's own stats so per-combo
    fail rates and status reporting stay accurate.

    FIXED 2026-08-09: Added per-symbol timeout to prevent hangs on stuck SEC API calls.
    If a single symbol takes >30s to process, skip it and move to next (marks as failed
    to trigger watermark logic for retry). This prevents the entire 5300-symbol load
    from stalling on one bad symbol.
    """
    import queue
    import threading

    # CRITICAL FIX (Session 96): Use centralized timeout config instead of hardcoded 10800s (3h)
    # Hardcoded 10800s was timing out financial_statements at 3h despite config allowing 4h (14400s)
    # This 1-hour shortfall caused Friday cascades that persisted through Monday retries
    # Get from centralized config, fallback to 14400s (4h) if not found
    from loaders.loader_timeout_config import get_loader_timeout

    sla_timeout_seconds = get_loader_timeout("financial_statements")
    per_symbol_timeout_seconds = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "30"))

    # FIXED 2026-08-22: a symbol whose thread.join() times out was previously just logged
    # and abandoned - the daemon thread itself kept running in the background (Python cannot
    # force-kill a thread), potentially still mid-fetch or mid-bulk_insert() with its own real
    # DB connection and an open transaction. Since nothing ever waited for these abandoned
    # threads, they were silently hard-killed - uncommitted - the instant this process exited
    # at the end of the full symbol-major pass, discarding any write that hadn't fully
    # committed yet. This is a strong live-supported root cause candidate for
    # [[quarterly_balance_sheet_fy_end_contamination_fixed_20260822]]'s unresolved
    # "backfill reports COMPLETED but 3,393/3,394 symbols still contaminated" mystery: the
    # 30s-per-symbol budget is cumulative across all 6 statement/period combos (see
    # `remaining_timeout` below), tight enough that a single slow-but-real SEC EDGAR fetch
    # (data.sec.gov, API_REQUEST_TIMEOUT_SECONDS=30 alone) can consume the whole budget - the
    # main loop then abandons the symbol as "failed" and moves on while the real fetch+write
    # keeps running unsupervised, only to be discarded uncommitted at process exit. Now every
    # timed-out thread is tracked and given a real chance to finish (and commit) after the
    # main pass completes, instead of being silently killed. This does NOT change behavior
    # for genuinely hung threads (e.g. a socket that never connects) - those still get
    # abandoned via daemon=True once the final grace join also times out.
    abandoned_threads: list[tuple[threading.Thread, str, str]] = []

    # PERF FIX (goal session 20260908, "optimize all loading activity"): see
    # loaders/helpers/financial_statements_prefetch.py's module docstring for the full
    # rationale (why overlapping just the companyfacts network fetch is safe here, unlike
    # real per-symbol pipelining across the loaders module boundary, which was ruled out
    # separately as a multi-day rearchitecture not safe to attempt mid-reload). Fails open on
    # any setup error (e.g. a test double/loader subclass without a _sec_client) - this is a
    # pure cache-warming optimization, never load-bearing, so an empty never-filled queue
    # (every get_nowait() below raises Empty) reproduces exactly the pre-existing behavior.
    try:
        prefetch_queue, _prefetch_thread = start_companyfacts_prefetch(active[0]._sec_client, symbols, shutdown_watcher)
    except Exception as prefetch_setup_err:
        logger.debug(f"[FINANCIAL_STATEMENTS ALL MODE] Prefetch warm-up not started: {prefetch_setup_err}")
        prefetch_queue = queue.Queue()

    for i, symbol in enumerate(symbols, 1):
        try:
            prefetch_queue.get_nowait()
        except queue.Empty:
            # Prefetcher hasn't reached this symbol yet (or already failed/skipped it) -
            # the loop below falls through to the pre-existing synchronous fetch.
            pass
        if time.time() - start > sla_timeout_seconds:
            logger.critical(
                f"[FINANCIAL_STATEMENTS ALL MODE] HARD LIMIT: exceeded {sla_timeout_seconds}s SLA "
                f"after {i - 1}/{len(symbols)} symbols. Halting."
            )
            raise RuntimeError(f"Loader exceeded hard SLA limit ({sla_timeout_seconds}s) after {i - 1} symbols")
        if shutdown_watcher.check_shutdown_requested():
            logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] Graceful shutdown - stopping after {i - 1} symbols")
            break
        if i % 50 == 0:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT 1")
            except Exception as health_err:
                logger.critical(
                    f"[FINANCIAL_STATEMENTS ALL MODE] Database health check failed "
                    f"at symbol {i}/{len(symbols)}: {health_err}"
                )
                raise RuntimeError(
                    "[FINANCIAL_STATEMENTS ALL MODE] Database health check failed-connection unreliable. "
                    "Halting loader."
                ) from health_err

            # DASHBOARD ACCURACY FIX 2026-08-18 (loader-health review): this loop tracked
            # loader._stats.increment("symbols_processed"/"symbols_failed") in memory every
            # symbol, but never called _status_manager.update_progress() - so
            # data_loader_status.completion_pct stayed frozen at the 0 mark_running() set it
            # to, for this loader's entire run (up to the 540m/9h SLA), indistinguishable
            # from a hang. Live-confirmed: a run 22 minutes in already showed real row_count
            # (66K-163K rows across the combo tables) while completion_pct still read 0.00 -
            # same "frozen at 0%" bug class already fixed for other loaders this week (e.g.
            # load_enhanced_quality_growth_metrics.py's own DASHBOARD ACCURACY FIX). Reuses
            # the existing every-50-symbols cadence (health check above) rather than adding a
            # new one - each `active` loader gets its own row updated since each combo/table
            # has independent status tracking.
            completion_pct = round(100.0 * i / len(symbols), 2)
            for progress_loader in active:
                try:
                    progress_loader._status_manager.update_progress(
                        symbols_loaded=i, symbol_count=len(symbols), completion_pct=completion_pct
                    )
                except Exception as progress_err:
                    # Progress reporting is diagnostic, not load-bearing - never let a
                    # transient status-table write failure abort real data loading.
                    logger.warning(
                        f"[FINANCIAL_STATEMENTS ALL MODE] Failed to update progress for "
                        f"{progress_loader.table_name} at symbol {i}/{len(symbols)}: {progress_err}"
                    )

        # The first combo's fetch downloads this symbol's companyfacts JSON;
        # the shared client's LRU serves the remaining combos from memory.
        # Use timeout for each symbol to prevent single stuck symbol from halting entire run.
        symbol_start = time.time()
        for loader in active:
            symbol_elapsed = time.time() - symbol_start
            remaining_timeout = max(1, per_symbol_timeout_seconds - symbol_elapsed)

            # Run loader.load_symbol() in a thread with timeout
            result = [False]  # mutable to capture result
            exception: list[Exception | None] = [None]  # mutable to capture exception

            # Bind loader/symbol/result/exception as default args (evaluated now, not at
            # call time) - otherwise every closure created across loop iterations shares
            # the SAME enclosing-scope cells. An abandoned (timed-out but not actually
            # dead - daemon threads can't be force-killed) thread that finishes later
            # would then write result[0]/exception[0] into whatever iteration's result
            # list is current *at that point*, silently corrupting a different symbol's
            # processed/failed counters.
            def run_with_timeout(
                loader: "ConsolidatedFinancialStatementsLoader" = loader,
                symbol: str = symbol,
                result: list[bool] = result,
                exception: list[Exception | None] = exception,
            ) -> None:
                try:
                    loader.load_symbol(symbol)
                    result[0] = True
                except Exception as e:
                    exception[0] = e
                    result[0] = False

            # daemon=True (FIXED 2026-08-09): Python cannot force-kill a thread, so a symbol
            # whose load_symbol() call is genuinely stuck (not just slow - e.g. hangs before
            # the socket ever connects, so configure_socket_timeout(30) never engages) leaves
            # this thread running forever after we abandon it below. A non-daemon thread left
            # running blocks the whole process from exiting (CPython's interpreter shutdown
            # waits on every non-daemon thread) - that would silently recreate the exact
            # "hangs 5+ hours in prod" bug this per-symbol timeout exists to prevent, just
            # moved from mid-loop to process-exit time. daemon=True lets the process exit
            # normally even if some abandoned threads never finish.
            thread = threading.Thread(target=run_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=remaining_timeout)

            if thread.is_alive():
                # Thread still running after timeout - mark as failed for this pass's
                # accounting, continue - but track it so we can still wait for it (and let
                # any in-flight bulk_insert() actually commit) after the main loop, instead
                # of leaving it to be silently killed uncommitted at process exit.
                logger.warning(
                    f"[{loader.table_name}] {symbol} exceeded per-symbol timeout ({per_symbol_timeout_seconds}s). "
                    f"Skipping for now - will get a final grace period to finish after the full pass."
                )
                loader._stats.increment("symbols_failed")
                abandoned_threads.append((thread, symbol, loader.table_name))
            elif result[0]:
                loader._stats.increment("symbols_processed")
            else:
                loader._stats.increment("symbols_failed")
                if exception[0]:
                    logger.error(f"[{loader.table_name}] {symbol} failed: {exception[0]}")

        if i % 100 == 0:
            logger.info(f"  Progress: {i}/{len(symbols)}")

    # Give every abandoned-but-possibly-still-running thread a final bounded chance to finish
    # (and let any in-flight bulk_insert() actually commit) before this process exits and
    # daemon=True silently kills them mid-transaction. Bounded by whatever's left of the
    # overall SLA (never blows past it) and a configurable cap (default 300s, override via
    # LOADER_ABANDONED_THREAD_GRACE_SECONDS for fast tests) so a large batch of genuinely
    # stuck threads can't stall the run indefinitely - each thread only consumes its share of
    # the remaining grace window, and join() returns immediately once a thread actually finishes.
    if abandoned_threads:
        grace_cap_seconds = float(os.getenv("LOADER_ABANDONED_THREAD_GRACE_SECONDS", "300"))
        grace_budget = max(0.0, min(grace_cap_seconds, sla_timeout_seconds - (time.time() - start)))
        logger.info(
            f"[FINANCIAL_STATEMENTS ALL MODE] Giving {len(abandoned_threads)} abandoned thread(s) up to "
            f"{grace_budget:.0f}s total to finish before this process exits."
        )
        grace_deadline = time.time() + grace_budget
        recovered = 0
        still_alive = 0
        for thread, symbol, table_name in abandoned_threads:
            thread.join(timeout=max(0.0, grace_deadline - time.time()))
            if thread.is_alive():
                still_alive += 1
                logger.warning(
                    f"[{table_name}] {symbol}: still running after final grace period - genuinely stuck, "
                    f"abandoning (will be killed at process exit; will retry next run)."
                )
            else:
                recovered += 1
                logger.info(
                    f"[{table_name}] {symbol}: finished during grace period - late write got a chance to commit."
                )
        logger.info(
            f"[FINANCIAL_STATEMENTS ALL MODE] Grace period complete: {recovered} thread(s) finished, "
            f"{still_alive} still alive and being abandoned."
        )


def _finalize_combo(
    loader: "ConsolidatedFinancialStatementsLoader",
    symbol_count: int,
    duration_sec: float,
    symbols: list[str],
) -> bool:
    """Per-combo finalization mirroring OptimalLoader.run + run_loader.

    Order matches the old per-combo path: fail-rate check first (the old
    _run_serial raised before metrics/final status were written), then metrics
    publishing (a failure there also failed the combo), then the final
    data_loader_status row and loader_execution_history entry.

    Returns:
        True if the combo succeeded, False if it failed.
    """
    loader._stats.set("duration_sec", duration_sec)
    stats = loader._stats.to_dict()

    symbols_failed = stats["symbols_failed"]
    fail_rate = (symbols_failed / symbol_count * 100) if symbol_count else 0.0
    max_fail_rate = getattr(
        loader, "max_fail_rate", 15.0
    )  # CRITICAL: Default 15% fail tolerance (was dangerously 60%). Fail-fast on data source issues.
    if fail_rate > max_fail_rate:
        msg = (
            f"[{loader.table_name}] {symbols_failed}/{symbol_count} symbols failed "
            f"({fail_rate:.1f}% > {max_fail_rate}% threshold)-incomplete dataset"
        )
        logger.error(msg)
        loader._log_execution_history("failed", msg[:500])
        return False

    try:
        from algo.reporting.metrics import MetricsPublisher

        with MetricsPublisher() as m:
            m.put_loader_result(loader.table_name, stats)
    except Exception as metrics_err:
        msg = f"Loader metrics publishing failed: {metrics_err}"
        logger.error(f"[{loader.table_name}] {msg}")
        loader._log_execution_history("failed", msg[:500])
        return False

    # FIXED 2026-08-23: ALL MODE never went through run_loader()/runner.py, so
    # ConsolidatedFinancialStatementsLoader.post_run() - which force-nulls the cells
    # _reject_implausible_shares_outstanding()/_reject_implausible_eps() rejected this run
    # (see its own docstring / the __init__ comment on why preserve_on_missing_fields can't
    # do this itself) - was never actually called for this codebase's real production
    # invocation path. The single statement/period mode (run_loader()) already picks this up
    # via runner.py's own post_run hook; mirroring that same call+failure-handling here so
    # ALL MODE gets the identical guarantee instead of a silent gap between the two paths.
    if hasattr(loader, "post_run"):
        try:
            loader.post_run()
        except Exception as post_run_err:
            msg = f"post_run failed: {type(post_run_err).__name__}: {str(post_run_err)[:400]}"
            logger.error(f"[{loader.table_name}] {msg}")
            loader._log_execution_history("failed", msg[:500])
            return False

    loader._update_final_status(symbol_count, symbols)
    loader._log_execution_history("success")
    return True


def _finalize_all(
    active: list["ConsolidatedFinancialStatementsLoader"],
    total_combos: int,
    symbol_count: int,
    duration_sec: float,
    symbols: list[str],
) -> int:
    """Finalize every active combo and compute the all-mode exit code."""
    combos_failed = 0
    for loader in active:
        if not _finalize_combo(loader, symbol_count, duration_sec, symbols):
            combos_failed += 1
    active[0]._invalidate_cache()

    if combos_failed:
        logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] {combos_failed}/{total_combos} combos failed")
        return 1 if combos_failed == total_combos else 0  # Return 1 only if all failed

    logger.info(
        f"[FINANCIAL_STATEMENTS ALL MODE] All {len(active)} statement/period combinations loaded in {duration_sec}s"
    )
    return 0


def _release_combo_locks(lock_manager: Any, active: list["ConsolidatedFinancialStatementsLoader"]) -> None:
    """Release the per-table run locks acquired for the symbol-major pass."""
    if lock_manager is None:
        return
    for loader in active:
        try:
            lock_manager.release(lock_key=loader.table_name)
        except Exception as lock_err:
            logger.warning(f"[{loader.table_name}] Failed to release lock: {lock_err}")


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        statement_type = os.environ["LOADER_STATEMENT_TYPE"].lower()
    except KeyError as e:
        raise ValueError(
            "CRITICAL: LOADER_STATEMENT_TYPE environment variable not set. Must be 'income', 'balance', 'cashflow', or 'all'."
        ) from e

    # Handle 'all' mode (load all statement types and periods sequentially)
    if statement_type == "all":
        return load_all_statements()

    # Handle single statement/period mode
    try:
        return run_loader(ConsolidatedFinancialStatementsLoader)
    except Exception as e:
        logger.error(f"[FINANCIAL_STATEMENTS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        table_name = "?"
        try:
            period = os.environ["LOADER_PERIOD"]
            config = get_statement_config(statement_type, period)
            table_name = config["table_name"]
            primary_key = config["primary_key"]

            # FIXED 2026-08-17: every one of this loader's 9 output tables keys its
            # primary_key on (symbol, fiscal_year[, fiscal_quarter]) or
            # (symbol, report_date) - never symbol alone - but a crash occurring before
            # any real row is fetched means fiscal_year/report_date genuinely aren't
            # known here. The INSERT below used to omit those columns (defaulting them
            # to NULL) and rely on "ON CONFLICT (symbol, fiscal_year) DO NOTHING" to
            # dedupe repeat crashes - broken, because SQL NULL never equals NULL, so
            # ON CONFLICT's uniqueness check never matches and every crash appended a
            # fresh full-universe batch of NULL-keyed rows with no bound. Worse, a
            # NULL-fiscal_year row actively corrupts every "get latest" query
            # elsewhere in the codebase shaped `ORDER BY fiscal_year DESC LIMIT 1`
            # (load_sec_valuations.py's book_value/cash_row/debt_row lookups among
            # them) - Postgres's DESC ordering defaults to NULLS FIRST, so the empty
            # marker silently outranks real, freshly-loaded data. Live-confirmed
            # 2026-08-17: a single crashed run of this exact except-block wrote 4,948
            # NULL-fiscal_year rows into annual_balance_sheet in one pass, which
            # immediately made AAPL/MSFT/GOOGL/F all report "book value missing"
            # despite each having real FY2025/2026 balance sheet data loaded the same
            # session. Since the missing key column(s) can't be safely defaulted or
            # deduplicated, skip the placeholder write entirely for these tables
            # (symbols keep whatever data they already had - a stale row is safer
            # than a corrupting NULL-keyed one) rather than writing something no
            # future run can clean up or safely query around.
            non_symbol_key_cols = [c for c in primary_key if c != "symbol"]
            if non_symbol_key_cols:
                logger.error(
                    f"[FINANCIAL_STATEMENTS FATAL] Cannot write a per-symbol crash marker to "
                    f"{table_name}: primary key {primary_key} requires {non_symbol_key_cols}, "
                    f"which is not known at crash time. Skipping marker writes (existing rows "
                    f"are left as-is) instead of writing rows with a NULL key column - see "
                    f"2026-08-17 fix comment above for why that corrupts downstream 'latest "
                    f"fiscal year' queries."
                )
                return 1

            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            # DO NOTHING (not DO UPDATE): a crash/timeout partway through must not
            # clobber symbols already fetched and committed earlier in this same
            # run. Only backfill a placeholder row for symbols never reached.
            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT {get_conflict_target(primary_key)} DO NOTHING
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark {table_name} data unavailable: {mark_err}")
        return 1


def get_conflict_target(primary_key: tuple[str, ...]) -> str:
    cols = ", ".join(primary_key)
    return f"({cols})"


class ConsolidatedFinancialStatementsLoader(
    SecEdgarStatementLoader,
    Q4DerivationSweepMixin,
    FinancialStatementsShareCountValidationMixin,
    FinancialStatementsValueValidationMixin,
):
    """Unified loader for all financial statements (income, balance, cashflow x annual/quarterly).

    Consolidates 8 separate loaders into one, parametrized by:
    - LOADER_STATEMENT_TYPE env var: 'income', 'balance', or 'cashflow'
    - LOADER_PERIOD env var: 'annual' or 'quarterly'

    This eliminates redundant ECS task definitions and reduces scheduler complexity.

    NOTE: 'ttm' is not a supported LOADER_PERIOD - get_all_statement_configs() dropped the
    ("income", "ttm")/("balance", "ttm")/("cashflow", "ttm") combos 2026-07-13 (see that
    function's docstring: SecEdgarStatementLoader never accepted period='ttm', both combos
    crashed on init every run). ttm_income_statement/ttm_cash_flow are real tables but have
    been frozen since 2026-05-22 with no active writer (see loader_registry.py's exclusion
    comment); ttm_balance_sheet was never created by any migration at all - balance sheet is
    a point-in-time snapshot, not a trailing-twelve-month aggregate, so it was never a
    coherent concept. None belong in output_tables below.
    """

    # SESSION 113 FIX: Declare all output tables so runner.py marks them all COMPLETED/FAILED
    # When running with LOADER_STATEMENT_TYPE="all", all 6 tables are processed.
    # runner.py will mark all 6 tables based on this class-level attribute.
    # FIXED 2026-08-18: previously listed 9 tables including ttm_income_statement/
    # ttm_cash_flow/ttm_balance_sheet - none of which this loader has written to since the
    # 2026-07-13 removal of ttm combos (see class docstring). That made runner.py mark all
    # three COMPLETED/100% on every run regardless, live-confirmed in data_loader_status
    # (execution_started 2026-08-18 00:04, all three COMPLETED/100.00%) even though
    # ttm_balance_sheet doesn't exist as a table (dashboard's data-status endpoint hit
    # UndefinedTable querying it) and the other two have been frozen since 2026-05-22.
    # pipeline_health.py and loader_registry.py already carried workaround exclusions for
    # this exact drift; this is the root-cause fix those comments deferred.
    output_tables = [
        "annual_income_statement",
        "quarterly_income_statement",
        "annual_balance_sheet",
        "quarterly_balance_sheet",
        "annual_cash_flow",
        "quarterly_cash_flow",
    ]

    max_fail_rate = 15.0  # Some stocks (foreign, delisted, recently-IPO'd) lack annual reports

    def __init__(
        self,
        backfill_days: int | None = None,
        statement_type: str | None = None,
        period: str | None = None,
        sec_client: SecEdgarClient | None = None,
    ):
        if statement_type is None:
            statement_type = os.environ["LOADER_STATEMENT_TYPE"]
        statement_type = statement_type.lower()
        if period is None:
            period = os.environ["LOADER_PERIOD"]
        period = period.lower()

        logger.info(f"[FINANCIAL_STATEMENTS] Initializing: statement_type={statement_type}, period={period}")

        config = get_statement_config(statement_type, period)
        self.table_name = config["table_name"]

        period_config = {period: config}

        super().__init__(
            statement_type=statement_type,
            period_config=period_config,
            period=period,
            sec_client=sec_client,
        )
        self.backfill_days = backfill_days

        # FIX 2026-07-20: OptimalLoader.__init__ keys self._watermark by
        # self.__class__.__module__ alone (WatermarkManager.table_name is stored but
        # never actually used in get_current_watermark/advance_watermark - verified in
        # utils/data/watermark.py). All 6 statement_type x period combos share this one
        # class, so they all resolved to the SAME watermark row per symbol. Whichever
        # combo ran first for a symbol set the shared watermark to today; the other 5
        # combos then saw "already loaded today", filtered every real fetched row out
        # (fiscal_year <= today's year is always true), and silently wrote nothing -
        # forever, since the watermark never moves back. Verified live: OTLK's SEC
        # income statement fetch returned 11 real rows that were discarded this way.
        # Give each combo its own watermark key so they stop colliding.
        from utils.data.watermark import WatermarkManager

        self._watermark = WatermarkManager(f"financial_statements_{statement_type}_{period}", self.table_name)

        # BUG CLASS FIX (2026-08-17, PRI net_income live-confirmed - see
        # utils/bulk_insert_manager.py's preserve_on_missing_fields docstring for the full
        # mechanism): a symbol's fiscal years going through bulk_insert() as one batch means
        # any single fiscal year whose fetch this run didn't produce a given mapped field
        # (transient concept-fetch gap, or - as live-confirmed for PRI FY2025 - a run using
        # code predating a field_mapping fix) gets that column force-NULLed via COPY
        # FORCE_NULL and overwrites a previously-correct value on ON CONFLICT DO UPDATE.
        # SEC-audited financial statement fields are immutable historical facts once real
        # data exists for a fiscal year (a restatement would arrive with a new value, not
        # silence), so preserving the existing value instead of NULLing it on a sparse
        # re-fetch is the correct semantics here - opt in every mapped data column except the
        # "why is this unavailable" governance markers, which must always reflect the CURRENT
        # run's assessment, never a stale one.
        self._bulk_insert_mgr.preserve_on_missing_fields = frozenset(config["field_mapping"].values()) - {
            "data_unavailable",
            "reason",
        }

        # BUG FOUND 2026-08-23 (goal session: EPS remediation re-fetch turned up almost no
        # change - 159->153 rows despite _reject_implausible_eps() logging a "Rejecting"
        # warning for every one of them): preserve_on_missing_fields' ON CONFLICT clause is
        # `COALESCE(EXCLUDED.col, table.col)` (utils/bulk_insert_manager.py) - this can't
        # distinguish "this run's fetch simply didn't produce a value for this optional
        # concept" (the legitimate PRI net_income case preserve_on_missing_fields exists
        # for) from "this run fetched a value, computed it, and deliberately rejected it as
        # implausible" (_reject_implausible_eps/_reject_implausible_shares_outstanding
        # setting row[field]=None). Both look identical to COALESCE - EXCLUDED.col is NULL
        # either way - so every deliberate rejection on a symbol/fiscal-year that already had
        # a stored value was silently discarded in favor of the stale bad value, for every
        # run since the shares_outstanding guard landed 2026-08-21. Live-confirmed: OLOX
        # FY2024/PACK FY2017-2018/RAYA FY2020+2023/STSS FY2024 all still showed their exact
        # pre-rejection garbage EPS after a live re-fetch that logged them as rejected.
        # Track exactly which (primary key, field) cells the two reject_implausible_*
        # methods null out this run, and force-null them directly in post_run() below via a
        # real UPDATE (not routed through bulk_insert_manager) - the only way to actually
        # overwrite a stale bad value that COALESCE would otherwise protect.
        self._explicit_null_rejections: list[tuple[dict[str, Any], str]] = []
        # Side channel keyed by (pk_key_tuple, field), populated alongside
        # _explicit_null_rejections - kept separate (rather than widening that list's tuple
        # shape) so the many existing tests asserting 2-tuples in _explicit_null_rejections
        # don't all need updating for a label-only fix. See _record_explicit_null_rejection's
        # 2026-09-03 fix comment.
        self._rejection_reasons: dict[tuple[Any, ...], str] = {}
        self._fpi_symbol_cache: dict[str, bool] = {}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        if symbol in SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS:
            self._reject_shared_etf_cik_data(symbol)
            return [self._unavailable_marker(symbol, "shared_issuer_or_trust_cik_not_attributable")]
        rows = super().fetch_incremental(symbol, since)
        # Custom-XBRL-extension fallbacks (CUSTOM_REVENUE_CONCEPTS/CUSTOM_INCOME_DIMENSIONED_
        # CONCEPTS/CUSTOM_CAPEX_CONCEPTS/CUSTOM_CAPEX_DIMENSIONED_CONCEPTS/CUSTOM_DIVIDEND_
        # CONCEPTS/CUSTOM_DEBT_CONCEPTS/CUSTOM_DEBT_LONGTERM_CONCEPTS/CUSTOM_DEBT_SHORTTERM_
        # CONCEPTS) - extracted to loaders/helpers/financial_statements_custom_extension_
        # fallbacks.py 2026-09-10 (file-size ratchet), see that module's docstring for the
        # full root-cause trail on why every one of these is gated to annual rows only
        # (fiscal_period == "FY") - the APA quarterly_revenue_annual_duplicate bug.
        if self.statement_type == "cashflow":
            apply_custom_cashflow_extensions(symbol, rows, self._sec_client)
        elif self.statement_type == "balance":
            apply_custom_debt_extensions(symbol, rows, self._sec_client)
        apply_custom_income_extensions(symbol, rows, self.statement_type, self._sec_client)

        # FIX 2026-09-03 (goal session: "get the missing-XBRL number down the right way" -
        # quality_metrics.interest_coverage's "interest_expense_not_itemized" bucket):
        # live-confirmed 301 of 373 universe symbols hitting this reason (e.g. PKG/Packaging
        # Corp $4.39B debt, GIL/Gildan $4.18B, ARW/Arrow Electronics $3.35B) have real,
        # substantial total_debt already on file, contradicting
        # _get_no_recent_interest_expense_symbols()'s "genuinely debt-free" explanation for
        # most of this bucket - these are real borrowers, not shell companies. Live-checked
        # PKG's actual companyfacts JSON (CIK 75677): no "InterestExpense"/
        # "InterestExpenseNonoperating"/"InterestExpenseDebt"/"InterestAndDebtExpense" fact
        # exists anywhere, but "InterestIncomeExpenseNet" (aliased for nonoperating filers as
        # "InterestIncomeExpenseNonoperatingNet") has real values every year (FY2023 -$53.3M,
        # FY2024 -$41.4M, FY2025 -$79.1M) - PKG nets interest income against interest expense
        # into one line instead of itemizing it, same reporting choice already documented for
        # AAPL (FY2024+) in _get_no_recent_interest_expense_symbols()'s own docstring, just
        # not wired to a fallback. Not handled by simply adding these concepts to
        # sec_statements.py's normal concept list like InterestExpenseNonoperating/
        # InterestExpenseDebt were: those are always-positive "Expense" concepts, but this is
        # a NET line that goes POSITIVE for a cash-rich filer with more interest income than
        # expense (e.g. a normal ratio consumer would then divide by a negative number,
        # producing a nonsensical negative or inverted interest_coverage) - deliberately only
        # used when negative (net expense dominates, the safe/unambiguous case), same
        # "don't guess when the sign is ambiguous" discipline as sec_statements.py's own
        # documented refusal to alias IFRS FinanceCosts (too broad) to InterestExpense.
        # Scoped to only run when at least one row is still missing interest_expense after
        # the normal extraction (the overwhelming majority of symbols never reach this),
        # and get_company_facts(cik) is an in-memory LRU cache hit here (super().
        # fetch_incremental() already fetched and cached this exact CIK's companyfacts JSON
        # a few lines above), so this adds no extra network calls for symbols where the
        # normal concept list already found a value.
        if self.statement_type == "income" and self.period == "annual":
            self._backfill_interest_expense_from_net_concept(symbol, rows)

        # FIXED 2026-08-31 (goal session: "VCIG tops the scores, dig in" investigation -
        # traced to BMA/LOMA/CEPU/CIG and other Argentine/Brazilian FPIs sitting at
        # value_score=100.00 for the same reason: pb_ratio/ps_ratio computed against a
        # STOCKHOLDERS_EQUITY/REVENUE value that is actually raw home-market-currency
        # (ARS/BRL) magnitude, not USD, divided against a USD ADS price - e.g. BMA's
        # annual_balance_sheet.stockholders_equity=$466.7B (2021), live-confirmed via
        # BMA's own real SEC companyfacts JSON (CIK 1347426) to be tagged unit="ARS", not
        # "USD" - a genuine foreign-currency fact, not a filer tagging error.
        # utils/external/sec_statements.py's _aggregate_concepts already correctly REJECTS
        # any non-USD/non-MAJOR_CURRENCIES unit (ARS isn't on that whitelist, by design -
        # see fx_rates.py) - live-verified via a direct call: get_balance_sheet(client,
        # 'BMA', 'annual') returns ZERO rows under CURRENT code, for every fiscal year.
        # But that correct rejection never reaches the DB: __init__'s
        # preserve_on_missing_fields COALESCEs a missing fresh value against whatever
        # already exists on ON CONFLICT DO UPDATE - the exact same "can't distinguish
        # deliberate rejection from a transient fetch gap" bug class already fixed once
        # for _reject_implausible_eps/_reject_implausible_shares_outstanding (see this
        # file's 2026-08-23 fix comment above) - just never extended to this rejection
        # path. BMA's stockholders_equity rows were written/touched as recently as
        # 2026-08-19 (AFTER the 2026-08-17/18 currency-rejection fix landed) with the same
        # stale $466.7B ARS figure untouched, proving this is not a one-time historical
        # artifact but an ongoing, every-run failure to actually apply the fix.
        #
        # sec_base.py's fetch_incremental (super() above) calls get_balance_sheet/
        # get_income_statement/get_cash_flow with NO date cutoff - `rows` there is always
        # the symbol's FULL XBRL history. If THAT is empty, sec_base.py returns
        # `[self._unavailable_marker(symbol, reason)]` (a single data_unavailable=True
        # row, never a bare `[]`) via _try_yfinance_fallback - live-confirmed via this
        # exact BMA/LOMA/CEPU/CIG/GGB run: every one hit "[YFINANCE_FALLBACK] ...
        # financialCurrency=ARS/BRL has no USD conversion available - rejecting", proving
        # the full-history SEC extraction found nothing at all AND the yfinance fallback
        # independently agreed the currency can't be trusted either. A bare empty `[]`
        # only ever comes back from the SEPARATE since/fiscal_year>since_year filter
        # further down in that same method (real history exists, just nothing NEWER than
        # the watermark) - the overwhelmingly common, must-not-touch incremental case.
        # So the correct signal is "every row this run got back is a data_unavailable
        # marker", not "rows is falsy" - checking bare emptiness here would silently never
        # fire (this bug's own first attempt did exactly that - the marker row made `rows`
        # always truthy). Still gated behind an explicit large backfill
        # (self._backfill_days >= 3650, matching this repo's established --backfill-days
        # remediation pattern - see CLAUDE.md) as an extra intentionality guard before a
        # brand-new force-null path runs against production data, and to FPI symbols only
        # (company_info_sec.is_foreign_private_issuer) - a domestic filer's full-history
        # extraction legitimately returning nothing means something else entirely
        # (delisted, no XBRL at all) and should NOT have its historical data wiped here.
        has_real_data = any(not r.get("data_unavailable") for r in rows)
        if rows and not has_real_data and self._backfill_days >= 3650 and self._is_foreign_private_issuer(symbol):
            self._reject_stale_fpi_currency_data(symbol)

        # FIXED 2026-09-01 (goal session: "how does a brand-new IPO have so many growth
        # metrics" - live-confirmed via OFRM/Once Upon a Farm, PBC): sec_statements.py's
        # period=="annual" extraction correctly rejects a short-duration (e.g. ~90-day
        # Q1) fact via its 330-day span guard, but the REJECTION ITSELF is invisible to
        # this loader - `get_income_statement()` just omits the field, producing a row
        # like {"fiscal_year": 2026, "fiscal_quarter": None, "revenue": None,
        # "net_income": None} that is non-empty (so `if not rows:` above never fires,
        # never triggering the yfinance fallback) and whose all-None value fields get
        # silently preserved (COALESCEd away) by preserve_on_missing_fields instead of
        # overwriting whatever was there before - the exact "correctly rejects now, but
        # the stale pre-fix value survives forever" bug class this file's own 2026-08-23
        # and 2026-08-17 fix comments above already describe for other trigger conditions,
        # never extended to this one. Live-confirmed: OFRM's annual_income_statement had
        # FY2025 revenue=$50,603,000 and FY2026 revenue=$72,720,000 - both exactly equal
        # to that fiscal year's real Q1-only quarterly figure (SEC's own companyfacts
        # JSON has no ~365-day revenue entry for OFRM at all, only quarterly/6-month-
        # cumulative ones) - a quarterly duration fact that was once accepted (before or
        # around this symbol's data first loaded) into the annual bucket, now correctly
        # rejected by a fresh fetch, but never actually cleared from the DB because the
        # fresh fetch's all-None row was silently absorbed by COALESCE rather than
        # explicitly nulling the stale cell. Guard: a row where EVERY preserve_on_missing_
        # fields column is None is never a legitimate "found real data for most fields,
        # missing one optional concept" case (that always leaves at least one field
        # populated) - it specifically means "found nothing usable at all for this
        # fiscal_year," so any existing DB value for that (symbol, fiscal_year) is
        # unconfirmed and should be force-nulled the same way _reject_stale_fpi_currency_
        # data already does for the FPI-currency case, not preserved indefinitely.
        # getattr guard: some tests construct this loader via __new__ + a handful of
        # manually-set attributes (bypassing __init__ entirely, e.g.
        # test_financial_statements_custom_extension_capex_fallback.py) and never set
        # _bulk_insert_mgr - harmless to skip this guard for those, since they don't
        # exercise the real upsert path this guard protects anyway.
        # FIXED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" / implausible-
        # values audit, ALMR/MRLN live-confirmed): checking every preserve_on_missing_fields
        # column (the original 2026-09-01 condition) let a cover-page/instant fact that's
        # essentially always present regardless of whether this fiscal year has a real
        # annual filing - entity_common_stock_shares_outstanding (-> shares_outstanding_dei)
        # or the balance-sheet share-count facts (-> shares_outstanding_basic) - masquerade
        # as "real data present," permanently defeating this guard for any symbol whose
        # cover page keeps reporting a share count. Live-confirmed via a direct
        # fetch_incremental("ALMR") call: fresh row was exactly
        # {"fiscal_year": 2026, "fiscal_period": "FY",
        # "entity_common_stock_shares_outstanding": 69392766, "data_source": "sec_audited"}
        # - no revenue/cost_of_revenue/gross_profit/net_income at all - yet the DB's stale
        # FY2026 revenue=$539K/cost_of_revenue=$11.578M/gross_profit=$14.457M (gross_profit
        # exceeding revenue by 26x, a hard accounting impossibility) survived indefinitely
        # via COALESCE because that one DEI field kept `any(...)` true. MRLN's fresh row
        # similarly carried only common_stock_shares_issued/outstanding and the DEI field.
        # Use _REQUIRED_STATEMENT_FIELDS (already the codebase's definition of "usable data"
        # for this exact statement type - see post_run()'s flag-sync use of the same
        # constant) instead of the full preserve_on_missing_fields set: a row missing every
        # required field has no usable data regardless of what cover-page/share-count
        # fields it also carries.
        # FIXED 2026-09-07 (goal session: scores-review regression audit, AAPL/JPM/NVDA/KO/
        # NEE/XOM/F/... live-confirmed): the 2026-09-06 fix above force-nulled a row the
        # moment THIS run's fetch came back with no required fields, with no check against
        # what's already stored - a transient single-run fetch gap (rate limiting, timing, a
        # slow SEC re-serve; see the 2026-08-20/21 "would_downgrade" comment above for the
        # same class of transient gap, just for the data_unavailable flag instead of the
        # value itself) got treated identically to a genuine "no annual filing exists" case,
        # and irreversibly wiped it via _record_explicit_null_rejection's bypass of preserve_
        # on_missing_fields' COALESCE - no retry, no cross-run confirmation. Live-confirmed
        # this morning's 07:43-09:03 run: 3,013 of 5,015 symbols hit this path in ONE run
        # (baseline the two days prior: 3 symbols) - including AAPL FY2024/FY2025, whose real
        # net_income ($93.7B/$112.0B) a direct fetch_incremental()+transform() call
        # immediately afterward reproduced correctly, proving the emptiness was this run's
        # own transient miss, not a real absence. Cascaded into stock_scores.quality_score/
        # value_score going NULL for hundreds of symbols same-day.
        #
        # Fix: apply the same "financial facts are immutable once real" principle preserve_
        # on_missing_fields itself already uses - only force-null when the row NEVER had real
        # required-field data on file (checked against the DB, same pattern as the
        # already_available rescue below), not whenever a single run's fetch happens to miss
        # it. ALMR/MRLN (this guard's original target) are unaffected by this change - the
        # specific gross_profit-exceeds-revenue impossibility they exhibited is independently
        # caught by _reject_implausible_gross_profit's dedicated 3x check above, which doesn't
        # depend on this run's fetch being empty at all.
        bulk_insert_mgr = getattr(self, "_bulk_insert_mgr", None)
        required_fields = _REQUIRED_STATEMENT_FIELDS.get(self.statement_type, set())
        # FIXED 2026-09-07 (goal session: scores-review, CELH/DXCM/SHOP/NU live-confirmed):
        # `rows` here is PRE-transform - its keys are the raw aggregated concept names
        # (e.g. "revenue_from_contract_with_customer_excluding_assessed_tax",
        # "net_income_loss"), not the canonical "revenue"/"net_income" column names
        # `required_fields` names - self._field_mapping (raw concept -> canonical column,
        # applied later by transform()) is what actually produces those. Checking
        # `row.get("revenue")`/`row.get("net_income")` directly against a pre-transform row
        # was therefore checking keys that (almost) never exist pre-mapping, regardless of
        # how much real data the row actually carried - live-confirmed via a direct
        # fetch_incremental("CELH") call: FY2025 row had
        # revenue_from_contract_with_customer_excluding_assessed_tax=2,515,269,000 and
        # net_income_loss=107,999,000 (both real, matching the raw SEC companyfacts cache
        # exactly) yet this check saw neither "revenue" nor "net_income" present and force-
        # nulled the row via _reject_stale_all_none_annual_row - reproduced for all of
        # CELH/DXCM/SHOP/NU's history in one run (all fiscal years share one force-null
        # timestamp), which is what a full/first backfill run looks like under this bug
        # (an incremental run with no new rows never reaches this loop at all, which is why
        # most already-loaded symbols were unaffected). Fix: check the raw keys that
        # self._field_mapping maps onto each required canonical field, not the canonical
        # field name itself.
        field_mapping = getattr(self, "_field_mapping", None) or {}
        required_raw_keys = {raw for raw, mapped in field_mapping.items() if mapped in required_fields}
        if self.period == "annual" and bulk_insert_mgr is not None and required_fields:
            self._reject_all_none_annual_rows_without_existing_data(
                symbol, rows, bulk_insert_mgr, required_fields, required_raw_keys
            )
        return rows

    def _reject_all_none_annual_rows_without_existing_data(
        self,
        symbol: str,
        rows: list[dict[str, Any]],
        bulk_insert_mgr: Any,
        required_fields: set[str],
        required_raw_keys: set[str],
    ) -> None:
        """Force-null an all-none annual row only if the DB has NEVER had real required-field
        data for that (symbol, primary key) - see the 2026-09-07 fix comment above
        fetch_incremental's call site for the full incident writeup (AAPL/NVDA/JPM/... force-
        nulled by treating a transient single-run empty fetch as a genuine absence).
        """
        pk_cols = list(bulk_insert_mgr.primary_key)
        required_cols = sorted(required_fields)
        already_has_data: set[tuple[Any, ...]] | None = None
        for row in rows:
            if row.get("data_unavailable"):
                continue
            if any(row.get(field) is not None for field in required_raw_keys):
                continue  # Real data present for at least one required field

            if already_has_data is None:
                already_has_data = set()
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            f"""
                            SELECT {", ".join(pk_cols)}, {", ".join(required_cols)}
                            FROM {self.table_name}
                            WHERE symbol = %s
                            """,
                            (symbol,),
                        )
                        n_pk = len(pk_cols)
                        for existing_row in cur.fetchall():
                            key = tuple(existing_row[:n_pk])
                            required_vals = existing_row[n_pk:]
                            if any(v is not None for v in required_vals):
                                already_has_data.add(key)
                except Exception as e:
                    logger.debug(f"[{self.table_name}] Existing-row lookup failed for {symbol} (non-fatal): {e}")

            pk_row = {pk: (symbol if pk == "symbol" else row.get(pk)) for pk in pk_cols}
            if any(v is None for v in pk_row.values()):
                continue  # Can't target an UPDATE without a complete primary key
            key = tuple(pk_row[pk] for pk in pk_cols)
            if key in already_has_data:
                continue  # Already-confirmed real data on file - this run's empty fetch is untrusted, let COALESCE preserve it
            self._reject_stale_all_none_annual_row(symbol, row)

    _INTEREST_EXPENSE_NET_CONCEPTS = ("InterestIncomeExpenseNet", "InterestIncomeExpenseNonoperatingNet")

    def _backfill_interest_expense_from_net_concept(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """Fill interest_expense for rows the normal concept list left None, from a real net
        interest income/expense fact, when the sign unambiguously means "expense dominates".
        See the fetch_incremental() call site's 2026-09-03 fix comment for the full PKG-
        verified evidence and why this can't just be added to sec_statements.py's normal
        always-positive concept list.
        """
        target_rows = [r for r in rows if r.get("interest_expense") is None and not r.get("data_unavailable")]
        if not target_rows:
            return
        try:
            cik = self._sec_client.symbol_to_cik(symbol)
            facts = self._sec_client.get_company_facts(cik)
        except Exception:
            return
        us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
        net_by_fiscal_year: dict[int, float] = {}
        for concept in self._INTEREST_EXPENSE_NET_CONCEPTS:
            node = us_gaap.get(concept)
            if not node:
                continue
            for entry in (node.get("units") or {}).get("USD", []):
                form = entry.get("form")
                if entry.get("fp") != "FY" or form is None or not str(form).startswith("10-K"):
                    continue
                fiscal_year, val, start, end = (
                    entry.get("fy"),
                    entry.get("val"),
                    entry.get("start"),
                    entry.get("end"),
                )
                if fiscal_year is None or val is None or not start or not end:
                    continue
                # Same ~330-day annual-duration span guard as _aggregate_concepts uses
                # elsewhere in this codebase (see the OFRM/e9704b11c fix in
                # sec_statements.py) - this helper bypasses that shared function entirely,
                # so it needs its own guard against a short-duration fact mislabeled fp="FY".
                try:
                    span_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                except ValueError:
                    continue
                if span_days < 330:
                    continue
                # last-listed concept / latest-filed entry wins, same overwrite convention
                # as sec_statements.py's normal concept-list extraction.
                net_by_fiscal_year[fiscal_year] = val
        for row in target_rows:
            row_fiscal_year = row.get("fiscal_year")
            if row_fiscal_year is None:
                continue
            val = net_by_fiscal_year.get(row_fiscal_year)
            # Only the unambiguous "net expense dominates" sign - see this method's
            # docstring for why a positive (net interest income) value is left alone.
            if val is not None and val < 0:
                row["interest_expense"] = abs(val)

    def _is_foreign_private_issuer(self, symbol: str) -> bool:
        if symbol not in self._fpi_symbol_cache:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s", (symbol,))
                row = cur.fetchone()
            self._fpi_symbol_cache[symbol] = bool(row[0]) if row else False
        return self._fpi_symbol_cache[symbol]

    def _reject_shared_etf_cik_data(self, symbol: str) -> None:
        """Force-null every preserved-monetary-field cell already stored for `symbol`,
        same force-null mechanism as _reject_stale_fpi_currency_data - see
        _get_shared_etf_cik_symbols' docstring for why any existing data here is another
        entity's (issuer bank's, or umbrella trust's) financials, not `symbol`'s own, and
        must not be preserved by preserve_on_missing_fields' COALESCE.
        """
        pk_cols = list(self.primary_key)
        with DatabaseContext("read") as cur:
            cur.execute(
                f"SELECT {', '.join(pk_cols)} FROM {self.table_name} WHERE symbol = %s",
                (symbol,),
            )
            existing_rows = cur.fetchall()
        if not existing_rows:
            return
        for existing in existing_rows:
            pk_row = dict(zip(pk_cols, existing, strict=True))
            for field in self._bulk_insert_mgr.preserve_on_missing_fields:
                self._record_explicit_null_rejection(pk_row, field, "shared_issuer_or_trust_cik_not_attributable")
        logger.warning(
            f"[{self.table_name}] {symbol}: shares its SEC CIK with another etf_symbols "
            f"ticker - queued {len(existing_rows)} existing row(s) for force-null "
            f"(not attributable to this symbol specifically)."
        )

    def _reject_stale_fpi_currency_data(self, symbol: str) -> None:
        """Force-null every preserved-monetary-field cell this table already holds for
        `symbol`, via the same _record_explicit_null_rejection/post_run() force-null path
        _reject_implausible_eps/_reject_implausible_shares_outstanding use (see this
        method's call site in fetch_incremental for the full BMA-class evidence and why
        this is only reachable on an explicit large-backfill run for a confirmed FPI).
        A full-history extraction that finds nothing usable for a real FPI's filing
        history overwhelmingly means every fact is tagged in a rejected non-USD currency
        (the whole filing shares one reporting currency) - there is no reliable USD value
        underneath to fall back to, so an honest NULL is strictly more correct than
        whatever pre-fix, wrong-currency-magnitude value is currently stored.
        """
        pk_cols = list(self.primary_key)
        with DatabaseContext("read") as cur:
            cur.execute(
                f"SELECT {', '.join(pk_cols)} FROM {self.table_name} WHERE symbol = %s",
                (symbol,),
            )
            existing_rows = cur.fetchall()
        if not existing_rows:
            return
        for existing in existing_rows:
            pk_row = dict(zip(pk_cols, existing, strict=True))
            for field in self._bulk_insert_mgr.preserve_on_missing_fields:
                self._record_explicit_null_rejection(pk_row, field, "fpi_currency_data_rejected")
        logger.warning(
            f"[{self.table_name}] {symbol}: full-history SEC extraction returned zero usable rows "
            f"(foreign private issuer, backfill_days={self._backfill_days}) - queued "
            f"{len(existing_rows)} existing row(s) for stale foreign-currency-value force-null in post_run()."
        )

    def _reject_stale_all_none_annual_row(self, symbol: str, row: dict[str, Any]) -> None:
        """Queue a force-null for every preserve_on_missing_fields column on this exact
        (symbol, fiscal_year) - see the 2026-09-01 fix comment in fetch_incremental for
        the full OFRM-verified evidence and mechanism. Scoped to a single fiscal_year
        (unlike _reject_stale_fpi_currency_data, which force-nulls a symbol's ENTIRE
        history) - a fresh fetch finding nothing usable for ONE year says nothing about
        whether other years' already-stored values are still good.
        """
        pk_cols = list(self._bulk_insert_mgr.primary_key)
        pk_row = {pk: (symbol if pk == "symbol" else row.get(pk)) for pk in pk_cols}
        if any(v is None for v in pk_row.values()):
            return  # Can't target an UPDATE without a complete primary key
        for field in self._bulk_insert_mgr.preserve_on_missing_fields:
            self._record_explicit_null_rejection(pk_row, field, "no_usable_annual_duration_fact")

    def _record_explicit_null_rejection(self, row: dict[str, Any], field: str, reason: str) -> None:
        """Record that `field` was deliberately nulled on this row so post_run() can force
        it to NULL in the DB directly, bypassing preserve_on_missing_fields' COALESCE (see
        the 2026-08-23 fix comment in __init__ for why that's necessary).

        FIXED 2026-09-03 (goal session: SEC/XBRL missing-data sweep): `reason` is required,
        not defaulted, and carried through to post_run()'s data_unavailable flag-sync. Before
        this fix every rejection - regardless of actual cause - got hardcoded to
        'fpi_currency_data_rejected' there, so e.g. _reject_stale_all_none_annual_row's
        Q1-mislabeled-as-annual rows (a genuinely different failure) were mislabeled with the
        FPI-currency reason once their required fields got force-nulled. Same "reason string
        doesn't match the real cause" bug class as the rest of this sweep, just introduced
        by two independently-correct fixes combining rather than by a single call site.
        """
        pk_cols = list(self._bulk_insert_mgr.primary_key)
        pk_values = {pk: row.get(pk) for pk in pk_cols}
        self._explicit_null_rejections.append((pk_values, field))
        self._rejection_reasons[(tuple(pk_values[c] for c in pk_cols), field)] = reason

    def post_run(self) -> None:
        """Force-null every cell _reject_implausible_shares_outstanding()/
        _reject_implausible_eps()/_reject_stale_fpi_currency_data() rejected this run,
        directly via UPDATE - the normal bulk_insert() path already ran and, per this
        file's __init__ comment, silently preserved the stale bad value for any row that
        already existed. This is the only point in the run where the actual rejection can
        take effect against pre-existing rows.
        """
        if self._explicit_null_rejections:
            pk_cols = list(self._bulk_insert_mgr.primary_key)
            required_by_type = _REQUIRED_STATEMENT_FIELDS.get(self.statement_type, set())
            seen: set[tuple[Any, ...]] = set()
            # Only rows where a REQUIRED field itself got force-nulled can possibly end up
            # with every required field NULL - tracking just these (rather than every
            # touched pk) skips a pointless extra query for the far more common eps/
            # shares_outstanding rejections below, which never null a required field.
            # FIXED 2026-09-03 (goal: SEC/XBRL missing-data sweep): tracks the reason that
            # actually caused each pk's required-field force-null, instead of a bare set -
            # see _record_explicit_null_rejection's 2026-09-03 fix comment for why a single
            # hardcoded reason across every rejection cause was itself a mislabeling bug.
            pks_needing_flag_check: dict[tuple[Any, ...], str] = {}
            forced = 0
            with DatabaseContext("write") as cur:
                for pk_values, field in self._explicit_null_rejections:
                    pk_key = tuple(pk_values[c] for c in pk_cols)
                    key = (*pk_key, field)
                    if key in seen or any(v is None for v in pk_values.values()):
                        continue
                    seen.add(key)
                    where_clause = " AND ".join(f"{c} = %s" for c in pk_cols)
                    cur.execute(
                        f"UPDATE {self.table_name} SET {field} = NULL WHERE {where_clause} AND {field} IS NOT NULL",
                        pk_key,
                    )
                    if cur.rowcount:
                        forced += cur.rowcount
                        if field in required_by_type:
                            # .get(..., fallback): a test that pre-seeds
                            # _explicit_null_rejections directly (bypassing
                            # _record_explicit_null_rejection - several existing tests do
                            # this) won't have populated _rejection_reasons; fall back to
                            # the pre-2026-09-03 behavior rather than mislabeling or raising.
                            pks_needing_flag_check[pk_key] = self._rejection_reasons.get(
                                (pk_key, field), "fpi_currency_data_rejected"
                            )

                # FIXED 2026-09-02 (goal: SEC/XBRL missing-data sweep): the force-null UPDATE
                # above only ever touches the value columns it's told to - it never revisits
                # data_unavailable/reason, which stay at whatever a PRIOR successful run last
                # wrote (often data_unavailable=FALSE/reason=NULL, from when the row genuinely
                # had real data). A row whose required field(s) this loop just wiped therefore
                # lands in the DB looking like an available-but-empty row forever, unless some
                # LATER run happens to re-fetch and re-transform() that exact fiscal year
                # (transform() has its own, correct required-field check - see
                # _REQUIRED_STATEMENT_FIELDS - but only runs against rows THIS run's fetch
                # actually returned). Live-confirmed: BMA/LOMA/CEPU self-corrected to
                # data_unavailable=TRUE/'incomplete_sec_filing_balance' after a later run
                # revisited them, but CIG/GGB/STNE/XP/SUZ/ABEV/VIV/PAGS and ~50 more FPI
                # symbols (510 annual_balance_sheet rows total, live-queried) stayed stuck at
                # data_unavailable=FALSE/reason=NULL with every column NULL - a strictly worse
                # state than "missing" (any downstream query filtering `WHERE data_unavailable
                # = FALSE` silently gets NULLs instead of skipping the row). Sync the flags for
                # exactly the rows this run's force-null loop wiped a required field on,
                # instead of hoping a future run's transform() happens to revisit the same
                # fiscal year.
                if pks_needing_flag_check:
                    where_clause = " AND ".join(f"{c} = %s" for c in pk_cols)
                    required_null_clause = " AND ".join(f"{f} IS NULL" for f in sorted(required_by_type))
                    flagged = 0
                    for pk_key, pk_reason in pks_needing_flag_check.items():
                        cur.execute(
                            f"""
                            UPDATE {self.table_name}
                               SET data_unavailable = TRUE,
                                   reason = %s
                             WHERE {where_clause}
                               AND data_unavailable = FALSE
                               AND {required_null_clause}
                            """,
                            (pk_reason, *pk_key),
                        )
                        flagged += cur.rowcount
                    if flagged:
                        logger.warning(
                            f"[{self.table_name}] post_run(): flagged {flagged} force-nulled "
                            "row(s) as data_unavailable=TRUE (were left looking available-but-"
                            "empty after their required fields were force-nulled)."
                        )
            if forced:
                logger.warning(
                    f"[{self.table_name}] post_run(): force-nulled {forced} previously-stored "
                    f"cell(s) across {len(seen)} unique (row, field) rejection(s) that "
                    "preserve_on_missing_fields would otherwise have silently kept at their "
                    "stale implausible value."
                )
        if self.statement_type == "income":
            self._sweep_stale_implausible_eps()
        if self.statement_type == "cashflow" and self.table_name == "annual_cash_flow":
            self._sweep_missing_free_cash_flow()
        if self.statement_type == "income" and self.table_name == "quarterly_income_statement":
            self._sweep_derive_missing_q4()
        if self.statement_type == "balance" and self.table_name == "quarterly_balance_sheet":
            self._sweep_copy_missing_q4_balance_sheet()
        if self.statement_type == "cashflow" and self.table_name == "quarterly_cash_flow":
            self._sweep_derive_missing_q4_cash_flow()

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format and add data_unavailable/reason flags.

        CRITICAL FIX (2026-08-01): Detect spinoff/incomplete SEC filings.
        When fiscal_year exists but ALL financial metrics are NULL, mark as data_unavailable
        instead of creating useless records (e.g., HONA/FDXF recent spinoffs).
        """
        transformed = super().transform(rows)

        # FIXED 2026-08-21 (goal session - broad shares_outstanding cross-check audit,
        # follow-up to the BRK.A/HEI dual-class fix): SEC's companyfacts REST API does NOT
        # always normalize a filer's inline-XBRL scale= attribute (e.g. scale="3" for
        # "reported in thousands") before exposing the "val" field - live-confirmed against
        # HUB Group's real companyfacts JSON (CIK 0000940942):
        # WeightedAverageNumberOfSharesOutstandingBasic for FY2025Q3 is tagged val=60066 (a
        # real share count in the tens of millions reported "in thousands", not 60,066
        # actual shares). ~95 active symbols (HUBG, SWBI, TEM, VPG, DDS, DDT, FLS, and more)
        # showed this exact ~1,000x-too-small pattern when cross-checked against
        # company_info_sec.shares_outstanding (an independently-extracted, unaffected
        # source). load_sec_valuations.py already has its own 20x cross-check guard against
        # company_info_sec (added 2026-08-20 for the LARK/RPAY 1000x scale-error case) that
        # happens to catch this before it reaches market_cap, but the raw
        # shares_outstanding_basic/diluted value stored here was still confidently wrong -
        # per "no cheats, no confidently-wrong data" governance, reject implausibly small
        # values here too rather than relying on a downstream consumer's guard to always be
        # present. Same MIN_PLAUSIBLE_SHARES_OUTSTANDING floor (100,000) already used in
        # load_company_info_sec.py.
        self._reject_implausible_shares_outstanding(transformed)
        self._reject_diluted_shares_below_basic(transformed)
        self._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch(transformed)
        self._reject_implausible_debt_field(transformed, "long_term_debt")
        self._reject_implausible_debt_field(transformed, "short_term_debt")
        self._reject_implausible_goodwill(transformed)
        if self.statement_type == "income":
            self._fill_derived_eps(transformed)
            self._reject_implausible_eps(transformed)
            self._reject_scale_mismatched_net_income(transformed)
            self._reject_scale_mismatched_revenue(transformed)
            self._reject_implausible_gross_profit(transformed)
            self._reject_stale_gross_profit_without_fresh_concept(transformed)
            self._reject_partial_segment_gross_profit_for_managed_care_insurers(transformed)
            self._reject_partial_cost_of_revenue(transformed)

        # Get REQUIRED metrics for current statement type (see module-level
        # _REQUIRED_STATEMENT_FIELDS docstring - shared with post_run()'s flag sync).
        required_by_type = _REQUIRED_STATEMENT_FIELDS.get(self.statement_type, set())

        # BUG FOUND 2026-08-20 (goal session: coverage root-cause audit): the required-metrics
        # check below runs against THIS run's freshly-fetched `row` dict only - but revenue/
        # net_income/etc. are in preserve_on_missing_fields (see __init__), so when this run's
        # SEC fetch comes back empty for a fiscal year (transient concept-extraction gap, rate
        # limiting, a currency-conversion miss) that a PRIOR run already populated with real
        # data, the SQL-level COALESCE preserves the real value in revenue/net_income - but
        # data_unavailable/reason are explicitly excluded from that preserve set (by design,
        # so they always reflect the CURRENT run's assessment), so they get overwritten to
        # True/"incomplete_sec_filing_{type}" based on this run's empty snapshot even though
        # the row ends up with real, usable data after the merge. Live-confirmed: 437 rows
        # across 232 symbols (e.g. GDS - 12 straight years of real revenue/net_income,
        # AIB, AKTS) stuck exactly this way - which then excludes them from
        # load_value_quality_growth_metrics.py's growth-rate computation (WHERE
        # data_unavailable = FALSE), inflating "insufficient_history" for otherwise-complete
        # symbols. Fixed by checking the EXISTING DB row before downgrading: a fiscal year
        # already confirmed available in a prior run keeps that state instead of being
        # re-judged on this run's possibly-incomplete fetch alone (financial statement facts
        # are immutable once real - same "once real, always real" logic __init__'s
        # preserve_on_missing_fields already applies to the value columns themselves).
        has_quarter_col = any("fiscal_quarter" in row for row in transformed)
        key_fields = ("symbol", "fiscal_year", "fiscal_quarter") if has_quarter_col else ("symbol", "fiscal_year")

        def _has_required(row: dict[str, Any]) -> bool:
            return any(row.get(field) is not None for field in required_by_type)

        would_downgrade = required_by_type and any(
            not row.get("data_unavailable") and not _has_required(row) for row in transformed
        )

        already_available: set[tuple[Any, ...]] = set()
        if would_downgrade:
            symbols_in_batch: list[str] = sorted({str(row.get("symbol")) for row in transformed if row.get("symbol")})
            required_cols = sorted(required_by_type)
            select_cols = [*key_fields, *required_cols]
            try:
                with DatabaseContext("read") as cur:
                    # FIXED 2026-08-21 (goal session continuation, same bug class as the
                    # 2026-08-20 fix above): this used to also filter `AND data_unavailable
                    # = FALSE`, on the assumption that's the only reliable signal a row
                    # "really" has data. But the COALESCE-preserve merge this whole check
                    # exists to guard against can ALSO write a real required value onto a
                    # row that's simultaneously (wrongly) marked data_unavailable=TRUE - if
                    # THAT already happened once (e.g. before this fix existed, or before a
                    # required-metric mapping was added), the FALSE-only filter can never
                    # see it, so every future run re-derives the same downgrade from that
                    # run's own (possibly sparse, e.g. an old fiscal year SEC is slow to
                    # re-serve) fetch and writes data_unavailable=TRUE right back - forever,
                    # even though real revenue/net_income sit right there in the row. Live-
                    # confirmed: XP FY2017-2019 (real revenue/net_income, e.g. FY2017
                    # revenue=$1.28B) stuck at data_unavailable=TRUE/
                    # reason='incomplete_sec_filing_income' across multiple runs AFTER the
                    # 2026-08-20 fix landed - 240 rows total. The row's actual column
                    # values, not its own possibly-wrong flag, are the correct source of
                    # truth for "is this really available" - drop the flag filter entirely.
                    cur.execute(
                        f"""
                        SELECT {", ".join(select_cols)}
                        FROM {self.table_name}
                        WHERE symbol = ANY(%s)
                        """,
                        (symbols_in_batch,),
                    )
                    n_key_fields = len(key_fields)
                    # BUG FOUND 2026-08-22 (goal session: CNK/Cinemark balance-sheet puzzle):
                    # DatabaseContext("read") returns rows as psycopg2.extras.DictRow, a LIST
                    # subclass - slicing it (`existing_row[:n]`) returns a plain `list`, not a
                    # tuple, so `already_available.add(key)` below raised `TypeError:
                    # unhashable type: 'list'` on every single call, silently caught by the
                    # broad except below and logged only at DEBUG (invisible at the normal
                    # WARNING/ERROR level this loader's other messages use). This made the
                    # ENTIRE "already_available" rescue - the fix for exactly this
                    # "real data already on file, don't re-downgrade it" bug class, added
                    # 2026-08-20/21 and credited with recovering 240+ XP rows and similar -
                    # silently inert since it was introduced: `already_available` was always
                    # an empty set, every run, for every symbol/table using this loader base
                    # class. Live-confirmed via CNK (Cinemark): FY2022's real total_assets/
                    # stockholders_equity sit in the DB untouched, but every fresh run
                    # re-marked it data_unavailable=TRUE anyway because the rescue that was
                    # supposed to prevent exactly that never actually ran. `tuple(...)` makes
                    # the key hashable so `set.add()` succeeds.
                    for existing_row in cur.fetchall():
                        key = tuple(existing_row[:n_key_fields])
                        required_vals = existing_row[n_key_fields:]
                        if any(v is not None for v in required_vals):
                            already_available.add(key)
            except Exception as e:
                logger.debug(f"[{self.table_name}] Existing-row lookup failed (non-fatal): {e}")

        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): batched alongside
        # already_available above (same would_downgrade gate, same symbols_in_batch) so the
        # unsupported-currency check below has is_foreign_private_issuer available without a
        # per-row query - see has_unsupported_currency_only_fact's docstring for why this
        # check is scoped to FPIs only (a domestic filer with all-NULL required fields is
        # never a currency issue, so this would be wasted API-cache-lookup cost for it).
        fpi_symbols: set[str] = set()
        if would_downgrade:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT symbol FROM company_info_sec WHERE symbol = ANY(%s) "
                        "AND is_foreign_private_issuer = TRUE",
                        (symbols_in_batch,),
                    )
                    fpi_symbols = {row[0] for row in cur.fetchall()}
            except Exception as e:
                logger.debug(f"[{self.table_name}] FPI lookup failed (non-fatal): {e}")

        result = []
        for row in transformed:
            if row.get("data_unavailable"):
                result.append(row)
            else:
                # Check if REQUIRED metrics are NULL (indicates truly incomplete SEC data)
                # OPTIONAL fields (amortization, goodwill, etc.) can be NULL without marking as unavailable
                has_required = _has_required(row)
                row_key = tuple(row.get(f) for f in key_fields)
                if not has_required and required_by_type and row_key not in already_available:
                    # REQUIRED financial metrics are NULL - mark as unavailable (spinoff/incomplete filing)
                    symbol = row.get("symbol", "?")
                    fiscal_year = row.get("fiscal_year", "?")
                    logger.warning(
                        f"[{self.table_name}] SPINOFF/INCOMPLETE DATA: {symbol} FY{fiscal_year} "
                        f"has no {self.statement_type} metrics (likely recent spinoff or incomplete SEC filing)"
                    )
                    row["data_unavailable"] = True
                    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): a
                    # foreign private issuer that only tags this statement's required
                    # concept(s) under an unsupported (non-major, non-USD) currency - see
                    # has_unsupported_currency_only_fact's docstring - gets the specific
                    # "unsupported_currency_no_fx_rate" reason instead of the generic
                    # "incomplete_sec_filing_{type}" every other cause here shares (both are
                    # "Missing SEC/XBRL data" in coverage_category_rules.py, same as this
                    # reason's post_run()-path sibling fpi_currency_data_rejected - this is a
                    # diagnostic-specificity fix, not a recategorization). Gated on FPI status
                    # first (cheap set lookup) so the extra get_company_facts() call - free
                    # here since it hits the same per-CIK cache this row's own extraction
                    # already warmed, but still a dict/API-shape round trip - never runs for
                    # the vastly more common domestic-filer incomplete-filing case.
                    us_gaap_concepts, ifrs_concepts = _UNSUPPORTED_CURRENCY_CHECK_CONCEPTS.get(
                        self.statement_type, ([], [])
                    )
                    if symbol in fpi_symbols and has_unsupported_currency_only_fact(
                        self._sec_client, symbol, us_gaap_concepts, ifrs_concepts
                    ):
                        row["reason"] = "unsupported_currency_no_fx_rate"
                    else:
                        row["reason"] = f"incomplete_sec_filing_{self.statement_type}"
                else:
                    # Has required metrics - data is valid even if optional fields are NULL
                    row["data_unavailable"] = False
                    row["reason"] = None
                    # FIXED 2026-08-18 (goal: "no SEC data" audit, REX American Resources
                    # live-confirmed): filers that never tag "Liabilities" directly but do
                    # report total_assets/stockholders_equity can have total_liabilities
                    # derived from the balance-sheet identity Assets = Liabilities +
                    # StockholdersEquity - not a legitimate gap, just an untagged concept.
                    if (
                        self.statement_type == "balance"
                        and row.get("total_liabilities") is None
                        and row.get("total_assets") is not None
                        and row.get("stockholders_equity") is not None
                    ):
                        row["total_liabilities"] = row["total_assets"] - row["stockholders_equity"]
                    # INVESTIGATED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k"
                    # sweep, pretax_income generic-gap investigation) and deliberately NOT added
                    # here: live-confirmed CVNA (Carvana, CIK 0001690820) never tags ANY of the
                    # three IncomeLossFromContinuingOperationsBeforeIncomeTaxes* concepts above,
                    # in any fiscal year, while NetIncomeLoss/IncomeTaxExpenseBenefit are both
                    # real - net_income + income_tax_expense reconstructs CVNA's real pretax
                    # income exactly. But this same approximation was already tried and
                    # REJECTED one layer up, at the point of use, in
                    # test_roic_pct_zero_tax_untagged_pretax_reason.py's docstring: "only ~75%
                    # agreement across the universe due to noncontrolling-interest/discontinued-
                    # operations adjustments" (289-symbol universe check). Filling it in HERE, at
                    # the source column, would be strictly worse than what was already rejected -
                    # it would silently corrupt pretax_income for every downstream consumer
                    # (not just roic_pct's scoped, confirmed-structural-absence branch via
                    # _get_never_tagged_pretax_income_symbols), indistinguishable from real
                    # tagged data. Leave pretax_income NULL here; the existing scoped
                    # approximation in load_value_quality_growth_metrics.py's roic_pct branch
                    # (only fires for symbols confirmed pretax-absent 3+ years) remains the
                    # correct, narrower place for this identity - do not re-add it as a blanket
                    # column-level fallback without addressing the NCI/discontinued-ops error
                    # rate first.
                    # FIXED 2026-08-18 (missing factor inputs audit): DividendsCommonStockCash/
                    # DividendsCommonStock (see _CASHFLOW_FIELD_MAPPING comment) carry a
                    # debit-balance XBRL definition and live-confirmed flip sign by filing
                    # vintage for the same real dividend program (VSH: negative 2014-2017,
                    # positive 2019-2025) - unlike the "PaymentsOf*" concepts (standard-positive
                    # by convention), a negative value here would silently produce a negative
                    # payout_ratio/dividend figure downstream. dividends_paid is always a
                    # magnitude (cash outflow), so this is a safe normalization for every
                    # source concept, not just the new ones - the existing "PaymentsOf*"
                    # concepts are already always positive in practice, so this is a no-op
                    # for them.
                    if self.statement_type == "cashflow" and row.get("dividends_paid") is not None:
                        row["dividends_paid"] = abs(row["dividends_paid"])

                    # FIXED 2026-09-07 (goal: "run all the tie-outs" sweep, live-verified via
                    # real SEC companyfacts JSON): stock_based_compensation/
                    # common_stock_repurchased have the EXACT same debit-balance sign-flip
                    # bug as dividends_paid above, just never extended to them. AAMI's own
                    # filed 10-K (CIK 0001748824, accn 0001628280-26-012856) tags
                    # AllocatedShareBasedCompensationExpense as -$23.2M (FY2024) and -$47.7M
                    # (FY2025) - a real non-cash compensation addback reported negative by the
                    # filer, not an extraction bug. JCTC's own filed 10-K/10-K/A (CIK
                    # 0000885307) tags PaymentsForRepurchaseOfCommonStock as -$3,075,559/
                    # -$7,188 for FY2012/2013 the same way. Both are always cash-flow-statement
                    # magnitudes (non-cash addback / cash outflow respectively), same as
                    # dividends_paid - live DB scan found 264+1,370 (annual+quarterly) negative
                    # stock_based_compensation rows and 99+477 negative common_stock_repurchased
                    # rows before this fix, all real filer-tagged negatives of this same shape.
                    if self.statement_type == "cashflow":
                        for _sign_flip_field in ("stock_based_compensation", "common_stock_repurchased"):
                            if row.get(_sign_flip_field) is not None:
                                row[_sign_flip_field] = abs(row[_sign_flip_field])
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
