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
from utils.external.sec_edgar import SecEdgarClient  # noqa: E402
from utils.loaders.enum_validator import validate_period, validate_statement_type  # noqa: E402

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
    # FIXED 2026-08-16: added alongside the yfinance fallback (loaders/helpers/sec_base.py's
    # SecEdgarStatementLoader._try_yfinance_fallback) - every row now carries an explicit
    # 'sec_audited' or 'yfinance' tag (migration 1202) so a lower-fidelity fallback row is
    # never indistinguishable from a real SEC filing, per the same governance discipline
    # tests/unit/test_company_info_sec_no_yfinance_pollution.py enforces elsewhere.
    "data_source": "data_source",
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
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "CostOfGoodsAndServicesSold" concept
    # added to sec_statements.py's get_income_statement() concepts list - see that file's
    # comment above the concept for the live-verified AMZN/COST/CI/JD/SHEL/TTE cases this
    # recovers. Same target column as "cost_of_revenue" above.
    "cost_of_goods_and_services_sold": "cost_of_revenue",
    "gross_profit": "gross_profit",
    "operating_income_loss": "operating_income",
    "net_income_loss": "net_income",
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "ProfitLoss" added to sec_statements.py's
    # get_income_statement() concepts list - see that file's comment above the concept for the
    # live-verified PRI (Primerica) case this recovers: PRI has ZERO NetIncomeLoss entries in
    # its us-gaap facts (confirmed via companyfacts JSON) but reports the exact same figure
    # under ProfitLoss instead (FY2025: $751,234,000, matching pretax_income - income_tax_expense
    # exactly). Same target column as "net_income_loss" above.
    "profit_loss": "net_income",
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
    # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): see sec_statements.py's
    # get_income_statement() comment for the live evidence (TXN/BA use
    # InterestAndDebtExpense; NEE uses the cash-basis InterestPaidNet as a last resort).
    "interest_and_debt_expense": "interest_expense",
    "interest_paid_net": "interest_expense",
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
    # CNX-class filers (E&P/domestic-only) report pretax income under this concept instead -
    # see sec_statements.py's get_income_statement() comment for the live-verification note.
    "income_loss_from_continuing_operations_before_income_taxes_domestic": "pretax_income",
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
#
# FIXED 2026-08-09 (same day, later session): "sales_revenue_net" added to this set too.
# That key is fed by two different source concepts depending on taxonomy - us-gaap
# "SalesRevenueNet" (a real total-revenue tag for some legacy/pre-ASC-606 filers, where
# it's meant to be primary) and ifrs-full "RevenueFromSaleOfGoods" (see
# sec_statements.py's _INCOME_IFRS_ALIASES) - but the latter is only the GOODS sub-line
# for companies that also report separate services/subscription revenue, not the total.
# Live-confirmed via KARO (Karooooo/Cartrack, pure IFRS 20-F filer, live companyfacts
# JSON): real total "Revenue" FY2025 = ZAR 4,567,459,000 (built from
# SubscriptionCirculationRevenue ZAR 4,055,394,000 + RevenueFromRenderingOfTransportServices
# ZAR 2,099,000 + RevenueFromSaleOfGoods ZAR 37,018,000 + other lines), but
# "RevenueFromSaleOfGoods" alone (ZAR 37,018,000) was overwriting it in the "revenue"
# column - same "last-listed wins unconditionally" bug class as the ORLY case above, this
# time triggered by two semantically-different concepts colliding on the same alias
# target_key rather than a single concept's fallback role. Making it fallback-only is
# safe for the legacy us-gaap filers this key also serves: when they have no separate
# "Revenues"/ASC-606 tag (the case the AGCO-style fix for sales_revenue_goods_net below
# depends on), "revenue" isn't populated yet when this key is reached, so it still writes
# normally - it only stops clobbering an already-real total. "sales_revenue_goods_net"
# (a separate, distinctly-keyed us-gaap concept - see the AGCO/pre-2011-filer comment on
# it in sec_statements.py) is added for the same defensive reason, though not yet
# live-confirmed as double-booked for any filer.
_REVENUE_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "interest_income_operating",
        "interest_and_dividend_income_operating",
        "sales_revenue_net",
        "sales_revenue_goods_net",
        # FIXED 2026-08-17 (goal: "no SEC data" audit continuation): "cost_of_goods_and_
        # services_sold" (added e1a3ae3b9 as a plain, always-overwrite mapping so retail/
        # product filers that never tag CostOfRevenue/CostOfSales at all - AMZN et al -
        # get a real cost_of_revenue) was NOT fallback-only, so on filers that tag BOTH
        # concepts for unrelated line items it silently clobbered a correct value with a
        # wrong one via sec_base.py's last-processed-wins copy loop. Live-confirmed via
        # real SEC EDGAR companyfacts for CAT: CostOfRevenue FY2025=$44.75B (real,
        # consolidated, ~65% of $67.6B revenue) vs. CostOfGoodsAndServicesSold FY2025=$49M
        # (some unrelated minor line item) - annual_income_statement.cost_of_revenue was
        # $49M, wrong by ~900x, with no data_unavailable/reason flag anywhere. A DB-wide
        # ratio scan (revenue > $1B, cost_of_revenue/revenue < 2%) found 32 symbols with
        # this same implausible-magnitude signature (CAT, CNC, VICI, JEF, ARCO, ...) - not
        # proof for every one without a per-symbol EDGAR check the way CAT was, but the
        # same pattern. Reusing this frozenset (not just "revenue" fields despite the
        # name - it's really "sec_field keys that only fill an already-empty db_field")
        # since it's already wired into every income-statement cfg below; this key now
        # only fills cost_of_revenue when CostOfRevenue/CostOfSales didn't already set it,
        # same as this set's existing entries, so AMZN-style filers are unaffected.
        "cost_of_goods_and_services_sold",
        # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): see sec_statements.py's
        # get_income_statement() comment for the live evidence (TXN/BA/NEE). Reusing this
        # same "fills only an already-empty db_field" set for the same overwrite-safety
        # reason as cost_of_goods_and_services_sold above - live-confirmed TRV reports
        # BOTH a real "InterestExpense" ($425M FY2025) AND "InterestPaidNet" ($393M
        # FY2025, a different, less precise cash-paid figure) for the same fiscal year, so
        # a plain always-overwrite mapping for interest_paid_net would have silently
        # downgraded TRV's real interest_expense on every filer that reports both (a very
        # common combination - "cash paid for interest" is a near-universal ASC 230
        # supplemental cash-flow disclosure). interest_and_debt_expense made fallback-only
        # too for the same reason, even though no live overwrite case was found for it
        # specifically - not exhaustively checked across the universe, so defaulting to
        # the safe convention this file uses everywhere else.
        "interest_and_debt_expense",
        "interest_paid_net",
    }
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

# FIXED 2026-08-17 (loader-review goal continuation): see sec_statements.py's
# get_balance_sheet() comment - these 3 concepts are alternate ways small/micro-cap
# filers tag real long-term debt when they never use the standard "LongTermDebt" concept
# at all (live-confirmed real instant-fact debt for MRKR/MODD/ATNM under these tags,
# part of a live DB scan finding 2,306 symbols with real balance sheet rows but zero
# long_term_debt ever). Fallback-only (not a plain mapping) so a filer that DOES report
# the standard LongTermDebt concept always keeps that value - see sec_base.py's copy
# loop: a non-fallback field always overwrites unconditionally regardless of processing
# order, so "long_term_debt" (from the real LongTermDebt concept) wins over any of these
# 3 whenever both are present for the same fiscal year; these only fill genuinely empty
# years.
_DEBT_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "notes_payable_related_parties_noncurrent",
        "long_term_notes_payable",
        "convertible_notes_payable",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up, goal: "no SEC data"
        # audit): DKNG/DASH-style fallback - see sec_statements.py's get_balance_sheet()
        # comment for the live evidence (DKNG FY2025 $1.26B, DASH FY2025 $2.72B tagged
        # only under this concept, never plain "ConvertibleNotesPayable"/"LongTermDebt").
        "convertible_long_term_notes_payable",
        # FIXED 2026-08-17 (SEC-vs-yfinance audit): JPM-style bank fallback - see
        # sec_statements.py's get_balance_sheet() comment for why this concept is needed
        # (JPM has not tagged plain "LongTermDebt" since FY2013).
        "long_term_debt_and_capital_lease_obligations_including_current_maturities",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" audit): ADM-style fallback for
        # filers that tag total equity including noncontrolling interest instead of the
        # parent-only "StockholdersEquity" concept - see sec_statements.py's
        # get_balance_sheet() comment for the live evidence. Despite the set's name, this
        # has been the shared "balance-sheet fallback-only fields" bucket since the JPM
        # entry above; both annual/quarterly balance configs reference it directly.
        "stockholders_equity_including_portion_attributable_to_noncontrolling_interest",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): CAT/SLB-style and
        # XOM-style fallbacks - see sec_statements.py's get_balance_sheet() comment for the
        # live evidence (CAT FY2025 $30.696B, SLB FY2025 $9.742B, XOM FY2025 $34.241B, none
        # of which tag plain "LongTermDebt").
        "long_term_debt_noncurrent",
        "long_term_debt_and_capital_lease_obligations",
    }
)

# FIXED 2026-08-17 (loader-review goal continuation): the fallback-variant search for
# SBC/buybacks migration 1206's comment flagged as not-yet-done - see sec_statements.py's
# get_cash_flow() comment for the live evidence (FIP/DC/CNA report SBC only under
# "AllocatedShareBasedCompensationExpense"; SPWH reports buybacks only under
# "PaymentsForRepurchaseOfEquity"). Fallback-only for the same reason as
# _DEBT_FALLBACK_ONLY_FIELDS: a filer that DOES report the standard concept
# (ShareBasedCompensation / PaymentsForRepurchaseOfCommonStock) always keeps that value.
_SBC_BUYBACK_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "allocated_share_based_compensation_expense",
        "payments_for_repurchase_of_equity",
    }
)

_BALANCE_FIELD_MAPPING = {
    "assets": "total_assets",
    "assets_current": "current_assets",
    "liabilities": "total_liabilities",
    "liabilities_current": "current_liabilities",
    "stockholders_equity": "stockholders_equity",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" audit): fallback for filers (ADM
    # live-confirmed, CIK 0000007084) that tag total equity including noncontrolling/minority
    # interest instead of the parent-only concept above. Flat lookup, not a priority order -
    # actual overwrite precedence comes from sec_statements.py's get_balance_sheet() concept
    # list order (fallback listed before "StockholdersEquity" there), same convention as the
    # cash fallbacks immediately below.
    "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
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
    # FIXED 2026-08-17 (loader-review goal continuation): fallback-only, see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above.
    "notes_payable_related_parties_noncurrent": "long_term_debt",
    "long_term_notes_payable": "long_term_debt",
    "convertible_notes_payable": "long_term_debt",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above (DKNG/DASH live evidence).
    "convertible_long_term_notes_payable": "long_term_debt",
    "long_term_debt_and_capital_lease_obligations_including_current_maturities": "long_term_debt",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above (CAT/SLB/XOM live evidence).
    "long_term_debt_noncurrent": "long_term_debt",
    "long_term_debt_and_capital_lease_obligations": "long_term_debt",
    # FIXED 2026-08-17 (migration 1204): real short-term/revolving debt concepts, previously
    # fetched nowhere - see sec_statements.py's get_balance_sheet() comment on why LongTermDebt
    # alone (the only debt concept fetched before this fix) misses commercial paper/short-term
    # notes payable. Companion fix to load_sec_valuations.py's total_debt mislabeling bug
    # (was reading total_liabilities, not any debt concept at all).
    "commercial_paper": "short_term_debt",
    "short_term_borrowings": "short_term_debt",
    # FIXED 2026-08-17 (migration 1205): post-ASC 842 capitalized lease liabilities -
    # see sec_statements.py's get_balance_sheet() comment for why these use the combined
    # (not Current/Noncurrent split) XBRL tags. Included in load_sec_valuations.py's
    # total_debt per the S&P/Moody's adjusted-debt convention (operating leases) plus
    # unambiguous debt (finance leases).
    "operating_lease_liability": "operating_lease_liability",
    "finance_lease_liability": "finance_lease_liability",
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
    # FIXED 2026-08-10: real capex concept some filers use INSTEAD of plain
    # "PaymentsToAcquirePropertyPlantAndEquipment" - live-confirmed via AAON, KELYB, CPS,
    # DTIL (all report ONLY "PaymentsToAcquireProductiveAssets", with real recent values -
    # AAON has 112 entries back through FY2023). This was the direct cause of
    # free_cash_flow/fcf_to_net_income being stuck at "SEC data not available" for these
    # symbols despite operating_cash_flow being populated - capex was never NULL because
    # the filer didn't report capex, it was NULL because this loader only looked for one
    # of two real capex tags. See sec_statements.py's get_cash_flow() concept list.
    "payments_to_acquire_productive_assets": "capex",
    # FIXED 2026-08-18 (goal: "missing SEC data" scores audit, AAON live-confirmed): see
    # sec_statements.py's get_cash_flow() comment on this concept - AAON (and likely other
    # filers) switched from PaymentsToAcquireProductiveAssets to this tag starting FY2023,
    # with zero overlap between the two, so capex was silently NULL for 3+ years.
    "payments_to_acquire_machinery_and_equipment": "capex",
    # FIXED 2026-08-18 (goal: "missing factor inputs" audit continuation): see
    # sec_statements.py's get_cash_flow() comments on these 2 concepts - VZ tags capex
    # ONLY under "OtherProductiveAssets" (NULL every year 2021-2026 despite real OCF);
    # LLY/ADP tag it ONLY under "OtherPropertyPlantAndEquipment" (same failure shape).
    "payments_to_acquire_other_productive_assets": "capex",
    "payments_to_acquire_other_property_plant_and_equipment": "capex",
    "payments_of_dividends": "dividends_paid",
    # FIXED 2026-08-17 (migration 1206): ShareBasedCompensation/
    # PaymentsForRepurchaseOfCommonStock were added to sec_statements.py's fetch list but
    # never mapped here - same "fetched but unmapped" bug class this file has hit
    # repeatedly (see test_financial_statements_field_mapping_completeness.py). Real data
    # was being fetched from SEC every run and silently dropped at transform().
    "share_based_compensation": "stock_based_compensation",
    "payments_for_repurchase_of_common_stock": "common_stock_repurchased",
    # FIXED 2026-08-17 (loader-review goal continuation): fallback-only, see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS comment above.
    "allocated_share_based_compensation_expense": "stock_based_compensation",
    "payments_for_repurchase_of_equity": "common_stock_repurchased",
    # FIXED 2026-08-03: real dividend-payment concepts some filers use INSTEAD of plain
    # "PaymentsOfDividends" - see sec_statements.py's comment above these concepts.
    "payments_of_dividends_common_stock": "dividends_paid",
    "payments_of_ordinary_dividends": "dividends_paid",
    # FIXED 2026-08-18 (missing factor inputs audit): ACGL (Arch Capital)/FRT (Federal
    # Realty)/VSH (Vishay) - all 3 live-confirmed real, currently-paying dividend stocks
    # (real recent ex_dividend_date on file in dividend_data) - never tag any of the 3
    # "PaymentsOf*Dividend*" concepts above at all. They report under "DividendsCommonStockCash"
    # instead (a genuine, well-populated concept: VSH's real values run $35M-$57M/year,
    # 2014-2025, growing in line with a normal dividend program). 19 confirmed real payers
    # universe-wide had NULL dividends_paid in every annual_cash_flow row before this fix.
    # Unlike the "PaymentsOf*" family (a payments/outflow concept, standard-positive by XBRL
    # convention), "DividendsCommonStockCash" carries a debit-balance definition and
    # live-confirmed flips sign by filing vintage (VSH: negative 2014-2017, positive
    # 2019-2025, for the exact same real dividend program) - see the abs() normalization in
    # ConsolidatedFinancialStatementsLoader.transform() below, required specifically for
    # this concept so a sign flip can't silently produce a negative payout_ratio/dividend
    # figure downstream.
    "dividends_common_stock_cash": "dividends_paid",
    "dividends_common_stock": "dividends_paid",
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
                    "data_source",
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
                    "data_source",
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
            "fallback_only_fields": _DEBT_FALLBACK_ONLY_FIELDS,
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
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_balance_sheet",
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "fallback_only_fields": _DEBT_FALLBACK_ONLY_FIELDS,
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
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
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
            "fallback_only_fields": _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
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
                    "stock_based_compensation",
                    "common_stock_repurchased",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_cash_flow",
            "field_mapping": {**_CASHFLOW_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "fallback_only_fields": _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
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
                    "stock_based_compensation",
                    "common_stock_repurchased",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
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
    import threading

    # CRITICAL FIX (Session 96): Use centralized timeout config instead of hardcoded 10800s (3h)
    # Hardcoded 10800s was timing out financial_statements at 3h despite config allowing 4h (14400s)
    # This 1-hour shortfall caused Friday cascades that persisted through Monday retries
    # Get from centralized config, fallback to 14400s (4h) if not found
    from loaders.loader_timeout_config import get_loader_timeout

    sla_timeout_seconds = get_loader_timeout("financial_statements")
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


class ConsolidatedFinancialStatementsLoader(SecEdgarStatementLoader):
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
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
