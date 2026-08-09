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

from loaders.helpers.sec_base import SecEdgarStatementLoader  # noqa: E402
from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders.enum_validator import validate_statement_type, validate_period  # noqa: E402
from utils.external.sec_edgar import SecEdgarClient  # noqa: E402

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


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
# data_unavailable/reason must pass through so marker rows keep their flags.
_MARKER_FIELDS = {
    "data_unavailable": "data_unavailable",
    "reason": "reason",
}

_INCOME_FIELD_MAPPING = {
    "revenues": "revenue",
    # FIXED 2026-08-09: older/narrower goods-revenue tag some pre-2011-ish filers use
    # instead of "Revenues"/"SalesRevenueNet" - see sec_statements.py's concepts-list
    # comment on SalesRevenueGoodsNet for the live-verified AGCO case this recovers.
    "sales_revenue_goods_net": "revenue",
    "sales_revenue_net": "revenue",
    "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
    "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
    # FIXED 2026-08-01: RevenuesNetOfInterestExpense for banks (2020+ data).
    # Maps to same "revenue" column - this is the standard revenue metric for
    # financial services companies since 2020. Ordering in sec_statements.py
    # ensures last-listed concept (this one for banks) wins on overwrite.
    "revenues_net_of_interest_expense": "revenue",
    # FIXED 2026-08-03: mortgage REITs (AGNC, NLY live-confirmed) report gross interest
    # income as their revenue-equivalent line, not any concept above - see sec_statements.py's
    # comment on InterestIncomeOperating for why InterestIncomeExpenseNet (which goes negative
    # in real years) was rejected in favor of this gross, always-positive figure.
    "interest_income_operating": "revenue",
    # FIXED 2026-08-03: community banks/thrifts (FNWB, AMAL, OCFC, and others - live-confirmed
    # via real SEC companyfacts JSON for all three) report neither standard revenue concepts
    # nor RevenuesNetOfInterestExpense (that one's used by larger banks like MS/WFC) - their
    # primary revenue-equivalent line is InterestAndDividendIncomeOperating. Live-verified for
    # FNWB: values for FY2022-2025 line up with the same fiscal years NetIncomeLoss already had
    # real data for, confirming this is the right concept, not a guess. Ordering in
    # sec_statements.py places this after revenues_net_of_interest_expense so it only wins for
    # filers that have nothing else.
    "interest_and_dividend_income_operating": "revenue",
    "cost_of_revenue": "cost_of_revenue",
    "gross_profit": "gross_profit",
    "operating_income_loss": "operating_income",
    "net_income_loss": "net_income",
    "earnings_per_share_basic": "earnings_per_share",
    # FIXED 2026-07-28: EarningsPerShareDiluted (GAAP) and DilutedEarningsLossPerShare
    # (IFRS alias, both target this same key - see sec_statements.py's _INCOME_IFRS_ALIASES)
    # have been fetched from real SEC XBRL data all along, but this mapping never listed a
    # target column - unmapped keys are silently skipped by transform() (see this module's
    # comment above _MARKER_FIELDS), so diluted_eps sat 100% NULL across all 61,427 rows
    # despite the column existing and real data being available every run. Zero consumers
    # currently read diluted_eps (grep-confirmed) so this is additive, not fixing a live
    # scoring bug - but it's a real, standard, already-fetched metric worth actually having.
    "earnings_per_share_diluted": "diluted_eps",
    # FIXED 2026-07-28 (migration 1171): WeightedAverageNumberOfSharesOutstandingBasic has
    # been fetched from real SEC XBRL data all along but had no target column - see
    # sec_statements.py's comment above this concept. load_sec_valuations.py previously
    # derived a lossier proxy (net_income/eps) believing it already used this concept.
    "weighted_average_number_of_shares_outstanding_basic": "shares_outstanding_basic",
    # FIXED (migration 1192): fallback share count column, kept separate from
    # shares_outstanding_basic above - see sec_statements.py's comment on this concept.
    "weighted_average_number_of_diluted_shares_outstanding": "shares_outstanding_diluted",
    # FIXED 2026-08-03: point-in-time/blended share-count fallbacks for filers that tag
    # neither weighted-average concept above - see sec_statements.py's comments on
    # CommonStockSharesOutstanding/WeightedAverageNumberOfShareOutstandingBasicAndDiluted/
    # NumberOfSharesOutstanding (IFRS) for the live-verified filers (PLNT/WHD/YOU/SPT/JG/
    # BNR/TV/FMX) this recovers. All three map to shares_outstanding_basic, same as the
    # real weighted-average concept, since these filers have no separate weighted-average
    # tag to prefer instead.
    # FIXED (migration 1195): shares issued (can include treasury stock, so listed before
    # common_stock_shares_outstanding in sec_statements.py's concepts list to lose on
    # overwrite whenever the real outstanding count is also present).
    "common_stock_shares_issued": "shares_outstanding_basic",
    "common_stock_shares_outstanding": "shares_outstanding_basic",
    "weighted_average_number_of_share_outstanding_basic_and_diluted": "shares_outstanding_basic",
    # FIXED (migration 1195): dei:EntityCommonStockSharesOutstanding cover-page fact -
    # own column, not shares_outstanding_basic, per sec_statements.py's dei_aliases
    # docstring (this fact is present even for filers that already report a real
    # weighted-average count, so sharing a column risks a silent downgrade).
    "entity_common_stock_shares_outstanding": "shares_outstanding_dei",
    "interest_expense": "interest_expense",
    # FIXED 2026-08-03: real, live-confirmed concepts some filers use INSTEAD of plain
    # "InterestExpense" - see sec_statements.py's comment above these concepts. WMT never
    # reports "InterestExpense" at all (only "InterestExpenseDebt"); JNJ's taxonomy migrated
    # to "InterestExpenseNonoperating" starting FY2024.
    "interest_expense_nonoperating": "interest_expense",
    "interest_expense_debt": "interest_expense",
    # This mapping key was always correct - the bug was in sec_statements.py's
    # get_income_statement(), which fetched concept "DepreciationExpense" (not a real
    # us-gaap XBRL concept - live-confirmed absent from both AAPL's and MSFT's
    # companyfacts) instead of "Depreciation" (the real concept, live-confirmed present
    # for both, which _to_snake()'s to this "depreciation" key). Fixed there 2026-07-28;
    # live-verified annual_income_statement.depreciation_expense was 0/61,427 populated
    # before that fix. See that module's comment for the full story.
    "depreciation": "depreciation_expense",  # Session 398: EBITDA extraction
    "depreciation_and_amortization": "amortization_expense",  # Fallback if separate D/A not available
    "amortization_of_intangibles": "amortization_expense",  # Alt source for amortization
    # For roic_pct real effective-tax-rate computation (see sec_statements.py's comment
    # above these concepts for the live-verification note).
    "income_tax_expense_benefit": "income_tax_expense",
    "income_loss_from_continuing_operations_before_income_taxes_minority_interest_and_income_loss_from_equity_method_investments": "pretax_income",
    "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest": "pretax_income",
    **_MARKER_FIELDS,
}

# FIXED 2026-08-09: these two concepts are a last-resort revenue proxy for banks/REITs
# with no standard revenue tag (see the mapping comments above) - the "last-listed wins"
# overwrite this dict relies on only produces the documented behavior ("wins for filers
# with nothing else") when a company genuinely never reports one of the concepts above
# it. Live-confirmed that's not always true: ORLY (a normal retailer) reports a small
# real InterestAndDividendIncomeOperating line item (interest on cash investments)
# alongside its real revenue - sec_base.py's transform() now only writes these two into
# "revenue" if nothing else already has, instead of unconditionally overwriting.
_REVENUE_FALLBACK_ONLY_FIELDS = frozenset(
    {"interest_income_operating", "interest_and_dividend_income_operating"}
)

# FIXED 2026-08-09: REIT-specific fallback (SIC 6798 only, see sec_base.py's
# _reit_only_fallback_fields comment). Equity REITs' real revenue ("revenues", mostly
# lease income) is explicitly out of ASC 606's scope, so their ASC-606 contract-revenue
# tags only ever capture a much smaller non-lease fee-income line - unlike the general
# case (most post-2018 filers), where the ASC-606 tag legitimately supersedes "revenues"
# as the fuller, more current figure. Live-confirmed UDR: revenues=$1.67B (real) vs.
# revenue_from_contract_with_customer_excluding_assessed_tax=$8.3M (real but minor fee
# income) - the general priority chain let the $8.3M win.
_REIT_REVENUE_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "revenue_from_contract_with_customer_including_assessed_tax",
        "revenue_from_contract_with_customer_excluding_assessed_tax",
    }
)

_BALANCE_FIELD_MAPPING = {
    "assets": "total_assets",
    "assets_current": "current_assets",
    "liabilities": "total_liabilities",
    "liabilities_current": "current_liabilities",
    "stockholders_equity": "stockholders_equity",
    # FIXED 2026-07-28: these 6 concepts are fetched from real SEC XBRL data every run
    # (utils/external/sec_statements.py's get_balance_sheet(), GAAP + IFRS aliases both
    # present since the module was written) but had no target column here - a commit on
    # 2026-06-21 ("Clean up loader infrastructure - remove dead code") removed these exact
    # 6 entries from this mapping and from schema_cols below, mistaking real, actively-used
    # score-relevant balance sheet fields for dead code. Confirmed live: annual_balance_sheet
    # kept writing fresh rows every day (294 in the last 7 days) while goodwill/inventory/etc.
    # silently stopped updating on 2026-07-01 (the last rows written before the June 21
    # regression's effect worked through the existing per-symbol watermark backlog) - a real,
    # ~1-month-old active data-loss regression, not historically-always-missing data.
    "cash_and_cash_equivalents_at_carrying_value": "cash_and_equivalents",
    # FIXED 2026-08-03: two fallback concepts for filers that never tag the standard
    # concept above - banks (ZION live-confirmed) tag CashAndDueFromBanks instead, some
    # non-bank filers only tag the post-ASU-2016-18 combined cash+restricted-cash concept.
    # This dict is a flat lookup, not a priority order - actual overwrite precedence comes
    # from sec_statements.py's get_balance_sheet() concept list order (see its comment).
    "cash_and_due_from_banks": "cash_and_equivalents",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": "cash_and_equivalents",
    "accounts_receivable_net_current": "accounts_receivable",
    "inventory_net": "inventory",
    "property_plant_and_equipment_net": "ppe_net",
    "goodwill": "goodwill",
    "long_term_debt": "long_term_debt",
    **_MARKER_FIELDS,
}

_CASHFLOW_FIELD_MAPPING = {
    "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
    "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
    "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
    # Found 2026-07-20: this mapped to "capital_expenditures", a column that has never
    # existed in annual_cash_flow/quarterly_cash_flow (real column is "capex") - every
    # write silently vanished at the schema-validation step below, leaving capex NULL for
    # all ~140K existing rows across both tables since this loader was created (Session
    # 274). Renamed to match the real column so new/incremental writes actually land;
    # existing NULL rows need a backfill (re-run with BACKFILL_DAYS or per-symbol refetch).
    "payments_to_acquire_property_plant_and_equipment": "capex",
    "payments_of_dividends": "dividends_paid",
    # FIXED 2026-08-03: real dividend-payment concepts some filers use INSTEAD of plain
    # "PaymentsOfDividends" - see sec_statements.py's comment above these concepts.
    "payments_of_dividends_common_stock": "dividends_paid",
    "payments_of_ordinary_dividends": "dividends_paid",
    **_MARKER_FIELDS,
}

# Quarterly rows carry fiscal_period ("Q1".."Q4"), which transform() converts to the
# integer fiscal_quarter column. Annual rows' fiscal_period ("FY") stays unmapped -
# annual tables have no fiscal_quarter column.
_QUARTERLY_EXTRA = {"fiscal_period": "fiscal_quarter"}


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


def get_income_statement_config(period: str) -> dict[str, Any]:
    """Income statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_income_statement",
            "field_mapping": dict(_INCOME_FIELD_MAPPING),
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "shares_outstanding_basic",
                    "shares_outstanding_diluted",
                    "shares_outstanding_dei",
                    "income_tax_expense",
                    "pretax_income",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_income_statement",
            "field_mapping": {**_INCOME_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "shares_outstanding_basic",
                    "shares_outstanding_diluted",
                    "shares_outstanding_dei",
                    "income_tax_expense",
                    "pretax_income",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_income_statement",
            "field_mapping": dict(_INCOME_FIELD_MAPPING),
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "earnings_per_share",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")


def get_balance_sheet_config(period: str) -> dict[str, Any]:
    """Balance sheet configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_balance_sheet",
            "field_mapping": dict(_BALANCE_FIELD_MAPPING),
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "cash_and_equivalents",
                    "accounts_receivable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_balance_sheet",
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "cash_and_equivalents",
                    "accounts_receivable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_balance_sheet",
            "field_mapping": dict(_BALANCE_FIELD_MAPPING),
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")


def get_cash_flow_config(period: str) -> dict[str, Any]:
    """Cash flow statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_cash_flow",
            "field_mapping": dict(_CASHFLOW_FIELD_MAPPING),
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "dividends_paid",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_cash_flow",
            "field_mapping": {**_CASHFLOW_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "dividends_paid",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_cash_flow",
            "field_mapping": dict(_CASHFLOW_FIELD_MAPPING),
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")


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
    from utils.db.rds_lock import RDSLockManager

    # get_lock_manager()'s real return type is DynamoDBLockManager | RDSLockManager (see
    # its docstring: DynamoDB preferred, RDS fallback - FileLockManager was a prior
    # fallback this codebase deliberately moved away from, see the RuntimeError handler
    # below). Declared type must match what's actually assigned.
    lock_manager: DynamoDBLockManager | RDSLockManager | None = None
    active: list[ConsolidatedFinancialStatementsLoader] = []
    try:
        lock_table = os.getenv(
            "LOADER_LOCKS_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
        )
        # TTL tied to the loader SLA (matches OptimalLoader.run): this all-mode pass
        # legitimately runs 45+ min, so a 1800s TTL would expire mid-run and allow a
        # concurrent instance to double-write. Locks are still released in finally.
        lock_ttl = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))
        try:
            lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
        except RuntimeError as ddb_err:
            # CRITICAL (Session 282): DynamoDB unavailable - fail fast, no fallback
            # Reason: FileLockManager has Windows race condition (non-atomic file creation).
            # Better to fail-fast and trigger infrastructure retry than silently degrade to unsafe locking.
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

        # CRITICAL FIX 2026-07-27: Lock TTL was set to LOADER_SLA_TIMEOUT_SECONDS (3 hours),
        # but scheduler timeout is 5 minutes. When loader times out, locks stayed held for 3 hours.
        # Reduced default to 30 minutes (1800s), still safe for legitimate long-running loads but
        # prevents multi-hour lockouts when a loader hangs/crashes.
        lock_ttl_seconds = int(os.getenv("LOADER_LOCK_TTL_SECONDS", "1800"))
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
    import threading

    sla_timeout_seconds = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))
    per_symbol_timeout_seconds = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "30"))

    for i, symbol in enumerate(symbols, 1):
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

        # The first combo's fetch downloads this symbol's companyfacts JSON;
        # the shared client's LRU serves the remaining combos from memory.
        # Use timeout for each symbol to prevent single stuck symbol from halting entire run.
        symbol_start = time.time()
        for loader in active:
            symbol_elapsed = time.time() - symbol_start
            remaining_timeout = max(1, per_symbol_timeout_seconds - symbol_elapsed)

            # Run loader.load_symbol() in a thread with timeout
            result = [False]  # mutable to capture result
            exception = [None]  # mutable to capture exception

            def run_with_timeout():
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
                # Thread still running after timeout - mark as failed, continue
                logger.warning(
                    f"[{loader.table_name}] {symbol} exceeded per-symbol timeout ({per_symbol_timeout_seconds}s). Skipping."
                )
                loader._stats.increment("symbols_failed")
            elif result[0]:
                loader._stats.increment("symbols_processed")
            else:
                loader._stats.increment("symbols_failed")
                if exception[0]:
                    logger.error(f"[{loader.table_name}] {symbol} failed: {exception[0]}")

        if i % 100 == 0:
            logger.info(f"  Progress: {i}/{len(symbols)}")


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
    max_fail_rate = getattr(loader, "max_fail_rate", 15.0)  # CRITICAL: Default 15% fail tolerance (was dangerously 60%). Fail-fast on data source issues.
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
        raise ValueError("CRITICAL: LOADER_STATEMENT_TYPE environment variable not set. Must be 'income', 'balance', 'cashflow', or 'all'.") from e

    # Handle 'all' mode (load all statement types and periods sequentially)
    if statement_type == "all":
        return load_all_statements()

    # Handle single statement/period mode
    try:
        return run_loader(ConsolidatedFinancialStatementsLoader)
    except Exception as e:
        logger.error(f"[FINANCIAL_STATEMENTS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        try:
            period = os.environ["LOADER_PERIOD"]
            config = get_statement_config(statement_type, period)
            table_name = config["table_name"]

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
                        ON CONFLICT {get_conflict_target(config["primary_key"])} DO NOTHING
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark {table_name} data unavailable: {mark_err}")
        return 1


def get_conflict_target(primary_key: tuple[str, ...]) -> str:
    cols = ", ".join(primary_key)
    return f"({cols})"


class ConsolidatedFinancialStatementsLoader(SecEdgarStatementLoader):
    """Unified loader for all financial statements (income, balance, cashflow x annual/quarterly/ttm).

    Consolidates 8 separate loaders into one, parametrized by:
    - LOADER_STATEMENT_TYPE env var: 'income', 'balance', or 'cashflow'
    - LOADER_PERIOD env var: 'annual', 'quarterly', or 'ttm'

    This eliminates redundant ECS task definitions and reduces scheduler complexity.
    """

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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        return super().fetch_incremental(symbol, since)

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform to schema format and add data_unavailable/reason flags.

        CRITICAL FIX (2026-08-01): Detect spinoff/incomplete SEC filings.
        When fiscal_year exists but ALL financial metrics are NULL, mark as data_unavailable
        instead of creating useless records (e.g., HONA/FDXF recent spinoffs).
        """
        transformed = super().transform(rows)

        # Define REQUIRED metric fields (must have at least one non-NULL value) vs OPTIONAL fields
        # REQUIRED fields: core SEC metrics that should always be present for real filings
        # OPTIONAL fields: companies-specific (amortization only for acquistive firms, inventory only for retailers, etc)
        required_metrics = {
            "income": {"revenue", "net_income"},  # Must have revenue or net_income for real filing
            "balance": {"total_assets", "stockholders_equity"},  # Must have assets/equity
            "cashflow": {"operating_cash_flow"},  # Must have operating cash flow
        }

        # Optional fields - NULL is expected for many companies (used for EBITDA/quality scores but not validation)
        _OPTIONAL_INCOME_FIELDS = {
            "depreciation_expense", "amortization_expense",  # Only companies with D&A report these separately
            "interest_expense",  # Finance/banks report this, others don't
            "cost_of_revenue", "gross_profit", "operating_income",  # Variations in revenue reporting
        }
        _OPTIONAL_BALANCE_FIELDS = {
            "goodwill", "inventory",  # Only acquire/retail firms report these
            "cash_and_equivalents", "accounts_receivable", "ppe_net", "long_term_debt",  # Varies by industry
        }
        _OPTIONAL_CASHFLOW_FIELDS = {"capex", "investing_cash_flow", "financing_cash_flow"}  # Not always reported

        # Get REQUIRED metrics for current statement type
        required_by_type = required_metrics.get(self.statement_type, set())

        result = []
        for row in transformed:
            if row.get("data_unavailable"):
                result.append(row)
            else:
                # Check if REQUIRED metrics are NULL (indicates truly incomplete SEC data)
                # OPTIONAL fields (amortization, goodwill, etc.) can be NULL without marking as unavailable
                has_required = any(row.get(field) is not None for field in required_by_type)
                if not has_required and required_by_type:
                    # REQUIRED financial metrics are NULL - mark as unavailable (spinoff/incomplete filing)
                    symbol = row.get("symbol", "?")
                    fiscal_year = row.get("fiscal_year", "?")
                    logger.warning(
                        f"[{self.table_name}] SPINOFF/INCOMPLETE DATA: {symbol} FY{fiscal_year} "
                        f"has no {self.statement_type} metrics (likely recent spinoff or incomplete SEC filing)"
                    )
                    row["data_unavailable"] = True
                    row["reason"] = f"incomplete_sec_filing_{self.statement_type}"
                else:
                    # Has required metrics - data is valid even if optional fields are NULL
                    row["data_unavailable"] = False
                    row["reason"] = None
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
