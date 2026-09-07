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
import statistics
import sys
import time

from loaders.loader_helper import setup_imports
from loaders.timeout_config import configure_socket_timeout

setup_imports()

import logging  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

from loaders.helpers.financial_statements_q4_sweeps import Q4DerivationSweepMixin  # noqa: E402
from loaders.helpers.sec_base import SecEdgarStatementLoader  # noqa: E402
from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.sec_custom_xbrl_concepts import (  # noqa: E402
    CUSTOM_CAPEX_CONCEPTS,
    CUSTOM_CAPEX_DIMENSIONED_CONCEPTS,
    CUSTOM_DEBT_CONCEPTS,
    CUSTOM_DEBT_LONGTERM_CONCEPTS,
    CUSTOM_DEBT_SHORTTERM_CONCEPTS,
    CUSTOM_DIVIDEND_CONCEPTS,
    CUSTOM_INCOME_DIMENSIONED_CONCEPTS,
    CUSTOM_REVENUE_CONCEPTS,
    fetch_custom_capex,
    fetch_custom_capex_dimensioned_sum,
    fetch_custom_debt,
    fetch_custom_debt_longterm,
    fetch_custom_debt_shortterm,
    fetch_custom_dividends,
    fetch_custom_income_dimensioned,
    fetch_custom_revenue,
)
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
    # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
    # IFRS 17 InsuranceRevenue now gets its own target_key ("insurance_revenue" - see
    # sec_statements.py's comment on the alias) instead of sharing "revenues" with plain
    # Revenue/RevenueAndOperatingIncome. Live-confirmed via real SEC companyfacts JSON:
    # BBVA (a bank with a minority insurance subsidiary) tags a real but small, sometimes
    # NEGATIVE InsuranceRevenue fact (e.g. FY2025 EUR -3.627B - the segment's net result,
    # not a revenue total at all) that was winning "revenue" over BBVA's real ~EUR26B
    # total (tagged InterestRevenueExpense) purely because both facts share the exact
    # same filed date (same 20-F) and InsuranceRevenue is listed earlier in
    # _INCOME_IFRS_ALIASES - _aggregate_concepts's tiebreak keeps whichever fact was
    # inserted first on an exact filed-date tie, so "last-listed wins" never actually
    # applied here. Same bug independently corrupted HSBC (real total ~$65-68B tagged
    # RevenueAndOperatingIncome, but InsuranceRevenue's small ~$2-3B insurance-segment
    # figure - a real but ~20x-too-small number - silently won instead, undetected until
    # now because it's positive and merely implausibly small rather than negative).
    # See _REVENUE_TOTAL_CANDIDATE_FIELDS in loaders/helpers/sec_base.py for the new
    # magnitude-based resolution among the fields below that fixes this generally rather
    # than special-casing BBVA/HSBC - AEG (a genuine insurer with no bank-interest
    # concepts) is unaffected since InsuranceRevenue is still its only real candidate.
    "insurance_revenue": "revenue",
    # FIXED 2026-08-09: older/narrower goods-revenue tag some pre-2011-ish filers use
    # instead of "Revenues"/"SalesRevenueNet" - see sec_statements.py's concepts-list
    # comment on SalesRevenueGoodsNet for the live-verified AGCO case this recovers.
    "sales_revenue_goods_net": "revenue",
    "sales_revenue_net": "revenue",
    "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
    "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
    # FIXED 2026-08-19: equity REITs' ASC 842 lease-revenue tag - see sec_statements.py's
    # comment on OperatingLeaseLeaseIncome for the live-verified AMH/EQR cases this
    # recovers. REIT-gated via _REIT_REVENUE_FALLBACK_ONLY_FIELDS below, not a plain
    # mapping - see that set's comment for why.
    "operating_lease_lease_income": "revenue",
    # ADDED 2026-09-01 (recovered from the growth-multi-input-blend worktree, found stranded
    # off main): older-era (pre-ASC 842, largely pre-2016) equity REITs used this concept as
    # their real estate rental revenue total before "OperatingLeaseLeaseIncome" existed as a
    # tag at all - see utils/external/sec_statements.py's comment on RealEstateRevenueNet for
    # the live-verified ARE case. Same _REIT_EXCLUSIVE_FIELDS wiring as
    # operating_lease_lease_income below (never touches "revenue" outside a confirmed REIT).
    "real_estate_revenue_net": "revenue",
    # FIXED 2026-08-01: RevenuesNetOfInterestExpense for banks (2020+ data).
    # Maps to same "revenue" column - this is the standard revenue metric for
    # financial services companies since 2020. Ordering in sec_statements.py
    # ensures last-listed concept (this one for banks) wins on overwrite.
    "revenues_net_of_interest_expense": "revenue",
    # FIXED 2026-08-22: foreign IFRS-filing banks' gross interest income/expense line - see
    # sec_statements.py's comment on InterestRevenueExpense (live-verified via WF/Woori
    # Financial Group) for the full rationale. Same target column as every other revenue
    # fallback above.
    "interest_revenue_expense": "revenue",
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
    # FIXED 2026-08-22: a small number of community banks (AROW live-confirmed) tag their
    # combined interest+dividend income total under this concept instead of
    # InterestAndDividendIncomeOperating - see sec_statements.py's comment on
    # InvestmentIncomeInterestAndDividend for the live-verified arithmetic proving this is
    # a real total, not a partial line item. Same target column as every revenue fallback
    # above.
    "investment_income_interest_and_dividend": "revenue",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): BDCs'
    # gross-investment-income top line - see sec_statements.py's comment on
    # GrossInvestmentIncomeOperating for the live-verified CSWC/PFLT/ICMB evidence.
    # Fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS below), same convention as every
    # other revenue proxy above.
    "gross_investment_income_operating": "revenue",
    # FIXED 2026-08-19: regulated electric/gas utilities' post-ASC-606 revenue tags - see
    # sec_statements.py's comments on RegulatedOperatingRevenue/
    # RegulatedAndUnregulatedOperatingRevenue for the live-verified XEL/DTE/OGS cases this
    # recovers (7+ years of real revenue that had gone silently NULL despite the company
    # continuing to file real, current 10-Ks).
    "regulated_operating_revenue": "revenue",
    "regulated_and_unregulated_operating_revenue": "revenue",
    # FIX 2026-09-02 (goal: "SEC/XBRL missing data" audit): identity key
    # ConsolidatedFinancialStatementsLoader.fetch_incremental() sets directly on rows for
    # symbols in utils/external/sec_custom_xbrl_concepts.py's CUSTOM_REVENUE_CONCEPTS -
    # see that module's docstring for why (real revenue tagged under a filer-specific
    # custom XBRL extension taxonomy, structurally invisible to the companyfacts API this
    # file's normal concept-list extraction depends on). fallback_only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) so it never overwrites a real value the normal
    # SEC extraction already found.
    "custom_extension_revenue": "revenue",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, pe_ratio/
    # peg_ratio investigation): identity keys set directly on rows for symbols in
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_INCOME_DIMENSIONED_CONCEPTS - see
    # that module's docstring (DB's real net_income/basic_eps/diluted_eps tagged only under
    # a single-explicitMember dimensioned context, invisible to the normal concept-list
    # extraction the same way CUSTOM_REVENUE_CONCEPTS is above). fallback_only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) so these never overwrite a real value the normal
    # SEC extraction already found.
    "custom_extension_net_income": "net_income",
    "custom_extension_eps_basic": "earnings_per_share",
    "custom_extension_eps_diluted": "diluted_eps",
    "cost_of_revenue": "cost_of_revenue",
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "CostOfGoodsAndServicesSold" concept
    # added to sec_statements.py's get_income_statement() concepts list - see that file's
    # comment above the concept for the live-verified AMZN/COST/CI/JD/SHEL/TTE cases this
    # recovers. Same target column as "cost_of_revenue" above.
    "cost_of_goods_and_services_sold": "cost_of_revenue",
    # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit): see
    # sec_statements.py's comment on these two concepts for the live-verified LIN case -
    # industrial/materials filers that break out D&A separately tag this DD&A-excluded COGS
    # variant instead of any concept above. Same target column, fallback-only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) since excluding D&A makes it a narrower figure
    # than a full COGS-including-D&A tag when a filer reports both.
    "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": "cost_of_revenue",
    "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization": "cost_of_revenue",
    # FIXED 2026-08-31 (goal session, same sweep as the DD&A-excluded COGS fix above): see
    # sec_statements.py's comment on these two concepts (LYV/AWK/WTRG/MSEX/YORW live-
    # verified). Same target column, fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS)
    # since both are narrower, business-model-specific cost measures.
    "direct_operating_costs": "cost_of_revenue",
    "utilities_operating_expense_maintenance_and_operations": "cost_of_revenue",
    "gross_profit": "gross_profit",
    # ADDED 2026-08-27 (goal: close the R&D intensity/Mohanram G-Score literature-checklist gap -
    # see sec_statements.py's get_income_statement() comment for the live-verification note).
    # Both concepts map to the same target column (broader standard tag listed later in that
    # file's concepts list, so it wins on overwrite for filers reporting both).
    "research_and_development_expense_excluding_acquired_in_process_cost": "research_development_expense",
    "research_and_development_expense": "research_development_expense",
    # ADDED 2026-09-07 (goal: SEC/XBRL missing-data audit, migration 1264): see
    # sec_income_statement.py's get_income_statement() comment on
    # "SellingGeneralAndAdministrativeExpense" for the live WMT/TGT/AAR/ABT evidence. Not
    # fallback-only - this is the only concept fetched for this column, same single-concept
    # convention as accounts_payable/accounts_receivable.
    "selling_general_and_administrative_expense": "operating_expenses",
    "operating_income_loss": "operating_income",
    "net_income_loss": "net_income",
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "ProfitLoss" added to sec_statements.py's
    # get_income_statement() concepts list - see that file's comment above the concept for the
    # live-verified PRI (Primerica) case this recovers: PRI has ZERO NetIncomeLoss entries in
    # its us-gaap facts (confirmed via companyfacts JSON) but reports the exact same figure
    # under ProfitLoss instead (FY2025: $751,234,000, matching pretax_income - income_tax_expense
    # exactly). Same target column as "net_income_loss" above.
    "profit_loss": "net_income",
    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): ESOA-class filers that
    # stop tagging both NetIncomeLoss and ProfitLoss - see sec_statements.py's
    # get_income_statement() comment on "IncomeLossFromContinuingOperationsIncludingPortion
    # AttributableToNoncontrollingInterest" for the live evidence. Same target column as
    # "net_income_loss"/"profit_loss" above; fallback-only via _REVENUE_FALLBACK_ONLY_FIELDS.
    "income_loss_from_continuing_operations_including_portion_attributable_to_noncontrolling_interest": "net_income",
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
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): JKHY (Jack
    # Henry & Associates) taxonomy-relabeled concept - see sec_statements.py's
    # get_income_statement() comment on InterestExpenseOperating for the live evidence
    # (identical value to plain InterestExpense in the one overlap year). Not fallback-
    # only, same "plain relabel" convention as interest_expense_nonoperating/
    # interest_expense_debt below.
    "interest_expense_operating": "interest_expense",
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
    # FIXED 2026-09-03 (same sweep): EPAC (Enerpac Tool Group) has tagged real,
    # continuous, non-zero interest expense under this concept for its entire filing
    # history - see sec_statements.py's get_income_statement() comment on
    # FinancingInterestExpense for the live evidence (EPAC has no "InterestExpense" at
    # all, and its rare "InterestAndDebtExpense" entries are a genuinely different,
    # smaller line item, not a duplicate). Fallback-only (added to
    # _REVENUE_FALLBACK_ONLY_FIELDS below, which despite its name is this file's shared
    # "only fills an already-empty db_field" bucket for the whole income-statement
    # config) so it never overwrites InterestAndDebtExpense's rare real value for EPAC.
    "financing_interest_expense": "interest_expense",
    "interest_paid_net": "interest_expense",
    # FIXED 2026-09-03 (same "cash paid" fallback tier as interest_paid_net above - see
    # sec_statements.py's get_income_statement() comment on "InterestPaid", ARW).
    "interest_paid": "interest_expense",
    # This mapping key was always correct - the bug was in sec_statements.py's
    # get_income_statement(), which fetched concept "DepreciationExpense" (not a real
    # us-gaap XBRL concept - live-confirmed absent from both AAPL's and MSFT's
    # companyfacts) instead of "Depreciation" (the real concept, live-confirmed present
    # for both, which _to_snake()'s to this "depreciation" key). Fixed there 2026-07-28;
    # live-verified annual_income_statement.depreciation_expense was 0/61,427 populated
    # before that fix. See that module's comment for the full story.
    "depreciation": "depreciation_expense",  # Session 398: EBITDA extraction
    "depreciation_and_amortization": "amortization_expense",  # Fallback if separate D/A not available
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): combined
    # D&A taxonomy-transition concept - see sec_statements.py's get_income_statement()
    # comment on DepreciationDepletionAndAmortization for the live-verified PG/WM/ULTA/
    # WSM/CP evidence. Same target column as depreciation_and_amortization above.
    "depreciation_depletion_and_amortization": "amortization_expense",
    "amortization_of_intangibles": "amortization_expense",  # Alt source for amortization
    # For roic_pct real effective-tax-rate computation (see sec_statements.py's comment
    # above these concepts for the live-verification note).
    "income_tax_expense_benefit": "income_tax_expense",
    # CNX-class filers (E&P/domestic-only) report pretax income under this concept instead -
    # see sec_statements.py's get_income_statement() comment for the live-verification note.
    "income_loss_from_continuing_operations_before_income_taxes_domestic": "pretax_income",
    "income_loss_from_continuing_operations_before_income_taxes_minority_interest_and_income_loss_from_equity_method_investments": "pretax_income",
    "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest": "pretax_income",
    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): identity entries for
    # the two derived final-column keys sec_statements.py's
    # _fill_income_tax_expense_from_current_deferred_split()/
    # _fill_pretax_income_from_results_of_operations_when_validated() write directly (e.g.
    # row["income_tax_expense"] = current + deferred) - unlike every other fallback in this
    # dict, those two functions set the DB column name itself, not a raw SEC-concept-derived
    # key, because they combine two SEPARATE concepts (no single concept alias to hang the
    # mapping off). Without these entries, transform()'s `if sec_field not in field_mapping`
    # check silently discarded both computed values on every row that reached this path
    # (verified empirically: dict(_INCOME_FIELD_MAPPING) has no "income_tax_expense"/
    # "pretax_income" key without this fix) - the exact "wiring half-landed" bug class
    # already caught twice before (see debt_fallback_wiring_half_landed_recurring_bug_class
    # in memory), just for a fill-function's OWN output key instead of a missing concept
    # string. This silently no-opped the CNS (income_tax_expense) and RRC
    # (pretax_income) fixes those functions' own docstrings/tests describe - their unit
    # tests only exercised the pure function in isolation, never round-tripped through
    # transform(), so the gap passed CI undetected.
    "income_tax_expense": "income_tax_expense",
    "pretax_income": "pretax_income",
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
        # FIXED 2026-08-22: same fallback-only reasoning as interest_and_dividend_income_
        # operating just above - see sec_statements.py's comment on
        # InvestmentIncomeInterestAndDividend and this dict's own comment on that key.
        "investment_income_interest_and_dividend",
        # FIXED 2026-09-03: BDC gross-investment-income fallback - see
        # _INCOME_FIELD_MAPPING's comment on "gross_investment_income_operating" above.
        "gross_investment_income_operating",
        # FIXED 2026-08-22 (goal session: "Insufficient history"/revenue-gap audit): IFRS 7
        # requires ALL filers with financial instruments (not just banks with no other
        # revenue tag) to disclose interest revenue/expense, so a filer that already reports
        # a real "Revenue"/"RevenuesNetOfInterestExpense" figure could ALSO separately report
        # InterestRevenueExpense as a supplementary disclosure - without fallback-only status
        # sec_base.py's last-processed-wins copy loop would let it silently clobber a correct,
        # more complete revenue figure with the narrower gross-interest-income one (same risk
        # class as the cost_of_goods_and_services_sold/CAT incident above). See
        # sec_statements.py's comment on InterestRevenueExpense (live-verified via WF/Woori
        # Financial Group, which has zero data under any other revenue concept, for the case
        # this genuinely does need to fill).
        "interest_revenue_expense",
        # WIDENED 2026-08-31: both also added to sec_base.py's _REVENUE_TOTAL_CANDIDATE_
        # FIELDS (magnitude-resolved group, checked BEFORE this fallback-only set - see
        # that set's own comment for the ANDE/PRGO/TKR cases that motivated it), same dual-
        # membership precedent as interest_revenue_expense above. Their fallback-only
        # membership here is now vestigial for filers that reach that check at all (the
        # magnitude branch always continues first) but kept rather than removed - harmless,
        # and this set is still the operative one for any other field that might someday
        # legitimately need pure fallback-only (never-overwrite-if-populated) semantics
        # without the magnitude comparison.
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
        # FIXED 2026-08-31: see sec_statements.py's comment on these two concepts (LIN
        # live-verified) - same "fills only an already-empty db_field" reasoning as
        # cost_of_goods_and_services_sold just above, since excluding D&A makes this a
        # narrower figure than a full COGS-including-D&A tag when both are reported.
        "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization",
        "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization",
        # FIXED 2026-08-31: same "fills only an already-empty db_field" reasoning - see
        # sec_statements.py's comments on these two concepts (LYV/AWK/WTRG/MSEX/YORW live-
        # verified) and _INCOME_FIELD_MAPPING's comment on them above.
        "direct_operating_costs",
        "utilities_operating_expense_maintenance_and_operations",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): same
        # "fills only an already-empty db_field" reasoning - see
        # _INCOME_FIELD_MAPPING's comment on "financing_interest_expense" above (EPAC
        # live-verified). Listed after interest_and_debt_expense in sec_statements.py's
        # concept list, so a filer with a rare real interest_and_debt_expense value keeps
        # it.
        "financing_interest_expense",
        "interest_paid_net",
        # FIXED 2026-09-03 (same reasoning as interest_paid_net just above - see
        # _INCOME_FIELD_MAPPING's comment on "interest_paid" above, ARW live-verified).
        "interest_paid",
        # FIX 2026-09-02 (goal: "SEC/XBRL missing data" audit): same "fills only an
        # already-empty db_field" reasoning as this set's other entries - see
        # _INCOME_FIELD_MAPPING's comment on "custom_extension_revenue" above. Only ever
        # populated for CUSTOM_REVENUE_CONCEPTS-registered symbols in the first place, so
        # this is a defensive-in-depth guard rather than a live-confirmed clobber risk.
        "custom_extension_revenue",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, pe_ratio/
        # peg_ratio investigation): same "fills only an already-empty db_field" reasoning as
        # custom_extension_revenue above - see _INCOME_FIELD_MAPPING's comment on these keys.
        # Only ever populated for CUSTOM_INCOME_DIMENSIONED_CONCEPTS-registered symbols.
        "custom_extension_net_income",
        "custom_extension_eps_basic",
        "custom_extension_eps_diluted",
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): ESOA-class filers
        # that stop tagging NetIncomeLoss/ProfitLoss - see _INCOME_FIELD_MAPPING's comment on
        # this key above.
        "income_loss_from_continuing_operations_including_portion_attributable_to_noncontrolling_interest",
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

# BUG FOUND 2026-08-19 (goal: "no SEC data"/loader audit): "operating_lease_lease_income"
# used to live in _REIT_REVENUE_FALLBACK_ONLY_FIELDS above, but that set's "unaffected for
# non-REIT filers" semantics is only correct for the two ASC-606 concepts (which SHOULD
# also win normally for non-REIT filers via the general priority chain - see
# test_sec_reit_lease_revenue_not_overwritten.py's AAPL case). OperatingLeaseLeaseIncome is
# different: for a non-REIT filer it's an unrelated, minor line item (real-estate sublease
# income), never a revenue analog, and must never touch "revenue" regardless of processing
# order. Live-confirmed via IHRT (iHeartMedia, SIC 7812, not a REIT): its real annual
# "Revenues" ($3.75B/$3.85B/$3.86B for FY2023-2025) was silently clobbered by its tiny
# sublease income under this concept ($2.01M/$787K/$562K - exact match to the corrupted DB
# values), a ~1000x understatement with no data_unavailable/reason flag anywhere. Wired via
# sec_base.py's new, stricter "reit_exclusive_fields" - skip (never write) for any symbol
# that isn't a confirmed REIT, fallback-only (skip if already populated) for symbols that
# are.
_REIT_EXCLUSIVE_FIELDS = frozenset(
    {
        "operating_lease_lease_income",
        "real_estate_revenue_net",
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
        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep): MembersEquity
        # sibling of the entry above - see sec_balance_sheet.py's get_balance_sheet() comment
        # for the live evidence (ARXS).
        "limited_liability_company_llc_members_equity_including_portion_attributable_to_noncontrolling_interest",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): CAT/SLB-style and
        # XOM-style fallbacks - see sec_statements.py's get_balance_sheet() comment for the
        # live evidence (CAT FY2025 $30.696B, SLB FY2025 $9.742B, XOM FY2025 $34.241B, none
        # of which tag plain "LongTermDebt").
        "long_term_debt_noncurrent",
        "long_term_debt_and_capital_lease_obligations",
        # FIXED 2026-08-18 (missing factor inputs audit, roic_pct/total_debt follow-up):
        # net-lease REITs (ADC/Agree Realty live-confirmed via real SEC companyfacts
        # JSON) stop tagging "LongTermDebt" mid-history (ADC's last real fact under that
        # concept is 2022-03-31) and switch to reporting debt only via
        # "DebtInstrumentCarryingAmount" going forward (ADC FY2022-2025: $1.96B/$2.43B/
        # $2.81B/$3.32B, a clean sum roughly matching SecuredDebt+UnsecuredDebt+
        # SeniorNotes reported the same years) - not debt-free, just a taxonomy switch.
        # Without this fallback, load_sec_valuations.py's total_debt fell back to summing
        # only ADC's tiny lease liabilities (~$25M) instead of its real ~$3B+ debt load,
        # producing a wildly understated invested_capital for roic_pct (and any other
        # consumer of total_debt/long_term_debt).
        "debt_instrument_carrying_amount",
        # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, KKR live-
        # confirmed): see sec_statements.py's get_balance_sheet() comment on
        # "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest" -
        # limited-partnership-structured filers (KKR pre-2018) tag total consolidated
        # partner capital (including third-party LP capital in consolidated managed
        # funds - live-confirmed KKR FY2014 $51.4B under this concept vs $5.38B under
        # the parent-only "PartnersCapital" concept the same year, a ~10x gap from
        # consolidated variable-interest entities) under this concept. Fallback-only so
        # the precise parent-only "partners_capital" mapping below (NOT fallback-only,
        # same non-fallback precedence as "stockholders_equity" itself) always wins when
        # both are present for the same fiscal year - same "IncludingPortion" vs.
        # parent-only precedence convention as the StockholdersEquity pair above.
        "partners_capital_including_portion_attributable_to_noncontrolling_interest",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): see
        # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS module comment
        # (BRK.A/BRK.B live evidence) - must never win over a real value the normal
        # concept-list extraction already found.
        "custom_extension_total_debt",
        # FIXED 2026-09-03 (same sweep): see
        # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_SHORTTERM_CONCEPTS
        # module comment (AES live evidence) - must never win over a real value the normal
        # concept-list extraction already found.
        "custom_extension_total_debt_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "NotesPayable" (AFL/MAA live evidence) - must never win over a real,
        # more complete LongTermDebt/SeniorNotes value.
        "notes_payable",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "DebtLongtermAndShorttermCombinedAmount" (PGR live evidence) - must
        # never win over a real LongTermDebt value from an earlier fiscal year.
        "debt_longterm_and_shortterm_combined_amount",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "SubordinatedDebt"/"JuniorSubordinatedDebentureOwedTo
        # UnconsolidatedSubsidiaryTrust" (IBOC/HBT live evidence) - must never win over
        # any of the standard debt concepts already fetched above.
        "subordinated_debt",
        "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" sweep): Donegal Group
        # (DGICA/DGICB) real revolving-credit debt - see sec_statements.py's
        # get_balance_sheet() comment on "LineOfCredit" for the live evidence ($35M FY2025).
        "line_of_credit",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "DebtCurrent" (DE live evidence) - a generic enough concept name
        # that a filer reporting a more specific standard concept (CommercialPaper/
        # ShortTermBorrowings/SeniorNotesCurrent/...) must always keep that value; this
        # only fills the gap when nothing else populated short_term_debt.
        "debt_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "ShortTermBankLoansAndNotesPayable" (EXPD live evidence).
        "short_term_bank_loans_and_notes_payable",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): mortgage
        # REIT repo-agreement financing - see sec_statements.py's get_balance_sheet() comment
        # on "SecuritiesSoldUnderAgreementsToRepurchase" (AGNC/ARR live evidence, $60.8B/
        # $10.7B FY2024 respectively, both previously NULL for every debt-component column).
        "securities_sold_under_agreements_to_repurchase",
        # FIXED 2026-09-03 (same sweep, SEVN follow-up): see sec_statements.py's
        # get_balance_sheet() comment on "SecuredDebtRepurchaseAgreements" (SEVN live
        # evidence).
        "secured_debt_repurchase_agreements",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "PublicUtilitiesPropertyPlantAndEquipmentNet" (ES live evidence) and
        # the finance-lease-combined PP&E concept (DASH/DINO live evidence) - despite this
        # set's debt-focused name it's the shared balance-sheet fallback-only bucket (see
        # the stockholders_equity entry's comment above), covers non-debt fields too.
        "public_utilities_property_plant_and_equipment_net",
        "property_plant_and_equipment_and_finance_lease_right_of_use_asset_after_accumulated_depreciation_and_amortization",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "ReceivablesNetCurrent" (WMT/COST/RTX live evidence).
        "receivables_net_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"
        # (BA/Boeing, HII/Huntington Ingalls live evidence).
        "inventory_net_of_allowances_customer_advances_and_progress_billings",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation): ACHV/BENF
        # real convertible-debt/other-long-term-debt concepts - see sec_statements.py's
        # get_balance_sheet() comment on "ConvertibleDebt"/"OtherLongTermDebt" for the live
        # evidence. Must never win over a real value the standard concepts already found.
        "convertible_debt",
        "convertible_debt_current",
        "convertible_debt_noncurrent",
        "other_long_term_debt",
        # FIXED 2026-09-05 (same continuation): SCM (Stellus Capital, a BDC) real secured
        # term-debt concept - see sec_statements.py's get_balance_sheet() comment on
        # "SecuredLongTermDebt" for the live evidence.
        "secured_long_term_debt",
        # FIXED 2026-09-05 (same continuation): KBDC (Kayne Anderson BDC) real fair-value
        # credit-facility concept - see sec_statements.py's get_balance_sheet() comment on
        # "LineOfCreditFacilityFairValueOfAmountOutstanding" for the live evidence and
        # magnitude cross-check.
        "line_of_credit_facility_fair_value_of_amount_outstanding",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): see
        # sec_statements.py's get_cash_flow() comment on StockOptionPlanExpense (CVX
        # live-confirmed) - must never win over a real ShareBasedCompensation/
        # AllocatedShareBasedCompensationExpense value.
        "stock_option_plan_expense",
        "payments_for_repurchase_of_equity",
        # FIXED 2026-08-29 (shipping-sector custom-XBRL-concept capex fallback): must
        # never win over a real value the normal concept-list extraction already found -
        # this key only exists for symbols where that extraction structurally can't work
        # at all (see _CASHFLOW_FIELD_MAPPING's comment on this same key).
        "custom_extension_vessel_capex",
        # FIXED 2026-09-03 (same sweep): NJR's dimensioned-sum capex - same "never win
        # over a real value the normal concept-list extraction already found" reasoning
        # as custom_extension_vessel_capex above (see CUSTOM_CAPEX_DIMENSIONED_CONCEPTS's
        # docstring in sec_custom_xbrl_concepts.py).
        "custom_extension_capex_dimensioned_sum",
        # FIXED 2026-09-03 (same sweep): CMS's custom-extension dividends_paid - same
        # "never win over a real value the normal concept-list extraction already found"
        # reasoning as the capex/revenue custom-extension fields above (see
        # CUSTOM_DIVIDEND_CONCEPTS's docstring in sec_custom_xbrl_concepts.py).
        "custom_extension_dividends_paid",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): ED's
        # narrower "construction work in progress" concept - see this dict's own comment
        # on "payments_for_construction_in_process" above and sec_statements.py's
        # get_cash_flow() comment for the live evidence it must never overwrite a real
        # standard-concept capex value.
        "payments_for_construction_in_process",
        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): see sec_statements.py's
        # get_cash_flow() comment on "NetCashProvidedByUsedInOperatingActivities
        # ContinuingOperations" (ASH/Ashland live-confirmed: zero entries under the plain
        # concept, ever - real OCF stuck NULL for its entire history). Fallback-only so
        # APD/ANGI (which report both concepts) keep the fuller plain-concept total
        # whenever it's actually present for that fiscal year.
        "net_cash_provided_by_used_in_operating_activities_continuing_operations",
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): BDC-
        # specific distribution concept - see sec_statements.py's get_cash_flow() comment
        # on this concept (MAIN live-confirmed: tags this AND a real, materially LARGER
        # DividendsCommonStock figure - a narrower/different sub-component, not a
        # duplicate) - must never overwrite a real standard-concept dividends_paid value.
        "investment_company_dividend_distribution",
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
    # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, KKR live-confirmed):
    # see _DEBT_FALLBACK_ONLY_FIELDS's comment on the IncludingPortion key -
    # limited-partnership-structured filers (KKR pre-2018) tag total partner capital
    # instead of any StockholdersEquity concept. "partners_capital" (parent-only, NOT
    # fallback-only) is the direct partnership analogue of "stockholders_equity" above
    # and always wins; the IncludingPortion variant only fills years where the
    # parent-only concept is absent entirely.
    "partners_capital_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
    "partners_capital": "stockholders_equity",
    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep): mirrors
    # "stockholders_equity_including_portion_attributable_to_noncontrolling_interest"
    # above, for the MembersEquity family - see sec_balance_sheet.py's get_balance_sheet()
    # comment on the matching concept-list entry for the live evidence (ARXS). Fallback-only
    # (listed BEFORE "members_equity" below so the direct legal-structure analogue always
    # wins when both are present for the same fiscal year).
    "limited_liability_company_llc_members_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" audit): LLC-
    # structured domestic filers (APGE/ARXS/ITG live-confirmed) tag "MembersEquity"
    # instead of any StockholdersEquity/PartnersCapital concept - see sec_statements.py's
    # get_balance_sheet() comment on the matching concept-list entry for the live
    # evidence. Direct legal-structure analogue, not fallback-only, same convention as
    # "partners_capital" above.
    "members_equity": "stockholders_equity",
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
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comment
    # on "ReceivablesNetCurrent" (WMT/COST/RTX live evidence) - fallback-only (see
    # _DEBT_FALLBACK_ONLY_FIELDS below), must never win over the standard concept.
    "receivables_net_current": "accounts_receivable",
    "accounts_receivable_net_current": "accounts_receivable",
    "inventory_net": "inventory",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comment
    # on "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings" - fallback-only
    # (see _DEBT_FALLBACK_ONLY_FIELDS above), must never win over the standard concept.
    "inventory_net_of_allowances_customer_advances_and_progress_billings": "inventory",
    # ADDED 2026-09-07 (goal: SEC/XBRL missing-data audit, migration 1263): see
    # sec_balance_sheet.py's get_balance_sheet() comment on "AccountsPayableCurrent" for the
    # live WMT/TGT evidence. Not fallback-only - this is the only concept fetched for this
    # column, same single-concept convention as accounts_receivable/inventory above.
    "accounts_payable_current": "accounts_payable",
    # ADDED 2026-09-07 (goal: check_balance_sheet_identity NCI gap rootcaused, migration
    # 1265): see sec_balance_sheet.py's get_balance_sheet() comment on "MinorityInterest" for
    # the live XOM FY2009 evidence ($4,823,000,000, closing the assets vs.
    # liabilities+stockholders_equity gap exactly). Not fallback-only - single directly-tagged
    # concept, same convention as accounts_payable above.
    "minority_interest": "noncontrolling_interest",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comments
    # on "PublicUtilitiesPropertyPlantAndEquipmentNet" (ES live evidence) and
    # "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciation
    # AndAmortization" (DASH/DINO live evidence) - both fallback-only (see
    # _DEBT_FALLBACK_ONLY_FIELDS below), must never win over the standard concept.
    "public_utilities_property_plant_and_equipment_net": "ppe_net",
    "property_plant_and_equipment_and_finance_lease_right_of_use_asset_after_accumulated_depreciation_and_amortization": "ppe_net",
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
    # FIXED 2026-08-18 (missing factor inputs audit): see _DEBT_FALLBACK_ONLY_FIELDS
    # comment above (ADC/net-lease-REIT live evidence - taxonomy switch mid-history, not
    # a genuine debt-free filer).
    "debt_instrument_carrying_amount": "long_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): BRK.A/BRK.B
    # (Berkshire Hathaway) real, ~$129B combined debt - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS module comment for
    # the live evidence (two entity-level segment totals, no single consolidated "total
    # debt" line exists at all, structurally invisible to companyfacts). No current/
    # noncurrent split in the source data (Berkshire's balance sheet is unclassified), so
    # this maps to long_term_debt only, same convention as the other single-figure debt
    # fallbacks above. Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS below) so it never
    # overwrites a real value the normal concept-list extraction already found.
    "custom_extension_total_debt": "long_term_debt",
    # FIXED 2026-09-03 (same sweep): AES Corporation's real, ~$29.9B combined debt - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_LONGTERM_CONCEPTS/
    # CUSTOM_DEBT_SHORTTERM_CONCEPTS module comment for the live evidence (filer-specific
    # recourse/non-recourse debt tags, structurally invisible to companyfacts, same class as
    # CUSTOM_CAPEX_CONCEPTS's DHT/CMRE - not the Berkshire dimensioned-sum case above).
    # AES's source data DOES have a real current/noncurrent split (unlike Berkshire), so
    # this is a separate short_term_debt target, distinct from custom_extension_total_debt.
    "custom_extension_total_debt_current": "short_term_debt",
    # FIXED 2026-08-17 (migration 1204): real short-term/revolving debt concepts, previously
    # fetched nowhere - see sec_statements.py's get_balance_sheet() comment on why LongTermDebt
    # alone (the only debt concept fetched before this fix) misses commercial paper/short-term
    # notes payable. Companion fix to load_sec_valuations.py's total_debt mislabeling bug
    # (was reading total_liabilities, not any debt concept at all).
    "commercial_paper": "short_term_debt",
    "short_term_borrowings": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): DE (Deere &
    # Company) real short-term debt - see sec_statements.py's get_balance_sheet() comment
    # on "DebtCurrent" for the live evidence and why its smaller sibling "SecuredDebt" is
    # deliberately NOT also mapped here (no summing mechanism exists for two concepts on
    # one target column - see that comment for the full reasoning).
    "debt_current": "short_term_debt",
    # FIXED 2026-09-03 (same sweep): EXPD (Expeditors International) real short-term
    # debt - see sec_statements.py's get_balance_sheet() comment on
    # "ShortTermBankLoansAndNotesPayable" for the live evidence.
    "short_term_bank_loans_and_notes_payable": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): mortgage
    # REIT repo-agreement financing - see sec_statements.py's get_balance_sheet() comment
    # on "SecuritiesSoldUnderAgreementsToRepurchase" for the live evidence (AGNC/ARR).
    "securities_sold_under_agreements_to_repurchase": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, SEVN
    # follow-up): see sec_statements.py's get_balance_sheet() comment on
    # "SecuredDebtRepurchaseAgreements" for the live evidence (SEVN).
    "secured_debt_repurchase_agreements": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): VRSN
    # (VeriSign) real debt concept - see sec_statements.py's get_balance_sheet() comment
    # on SeniorNotes/SeniorNotesCurrent for the live evidence. Same either/or-alternative,
    # plain-mapping convention as commercial_paper/short_term_borrowings above.
    "senior_notes": "long_term_debt",
    "senior_notes_current": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): AFL/MAA
    # real debt concept - see sec_statements.py's get_balance_sheet() comment on
    # "NotesPayable" for the live evidence. Same either/or-alternative, plain-mapping
    # convention as senior_notes above.
    "notes_payable": "long_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): PGR
    # (Progressive) real debt concept - see sec_statements.py's get_balance_sheet()
    # comment on "DebtLongtermAndShorttermCombinedAmount" for the live evidence. Same
    # fallback-only, single-figure convention as notes_payable above.
    "debt_longterm_and_shortterm_combined_amount": "long_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): IBOC/HBT
    # real trust-preferred/subordinated-debenture debt - see sec_statements.py's
    # get_balance_sheet() comment on "SubordinatedDebt"/"JuniorSubordinatedDebentureOwedTo
    # UnconsolidatedSubsidiaryTrust" for the live evidence. Same fallback-only,
    # single-figure convention as notes_payable/debt_longterm_and_shortterm_combined_
    # amount above.
    "subordinated_debt": "long_term_debt",
    "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": "long_term_debt",
    # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" sweep): Donegal Group
    # (DGICA/DGICB) real revolving-credit debt - see sec_statements.py's get_balance_sheet()
    # comment on "LineOfCredit" for the live evidence. Same fallback-only, single-figure
    # convention as notes_payable/subordinated_debt above.
    "line_of_credit": "long_term_debt",
    # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation,
    # total_debt_not_itemized investigation): ACHV/BENF real convertible-note debt - see
    # sec_statements.py's get_balance_sheet() comment on "ConvertibleDebt" for the live
    # evidence ($16.66M ACHV FY2023; split into Current/Noncurrent starting FY2024). Same
    # either/or-alternative convention as senior_notes/senior_notes_current above - a
    # filer reporting the split never also reports the bare concept for the same year.
    "convertible_debt": "long_term_debt",
    "convertible_debt_current": "short_term_debt",
    "convertible_debt_noncurrent": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): BENF (Beneficient) real long-term debt - see
    # sec_statements.py's get_balance_sheet() comment on "OtherLongTermDebt" for the live
    # evidence ($117.9M FY2025/$96.8M FY2026). Fallback-only, single-figure convention as
    # notes_payable/subordinated_debt above.
    "other_long_term_debt": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): SCM (Stellus Capital, a BDC) real secured term-debt -
    # see sec_statements.py's get_balance_sheet() comment on "SecuredLongTermDebt" for the
    # live evidence ($299M FY2025). Fallback-only, single-figure convention as above.
    "secured_long_term_debt": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): KBDC (Kayne Anderson BDC) real fair-value credit-
    # facility balance - see sec_statements.py's get_balance_sheet() comment on
    # "LineOfCreditFacilityFairValueOfAmountOutstanding" for the live evidence and
    # magnitude cross-check against implied total liabilities (96% match). Fallback-only,
    # single-figure convention as above.
    "line_of_credit_facility_fair_value_of_amount_outstanding": "long_term_debt",
    # FIXED 2026-08-17 (migration 1205): post-ASC 842 capitalized lease liabilities -
    # see sec_statements.py's get_balance_sheet() comment for why these use the combined
    # (not Current/Noncurrent split) XBRL tags. Included in load_sec_valuations.py's
    # total_debt per the S&P/Moody's adjusted-debt convention (operating leases) plus
    # unambiguous debt (finance leases).
    "operating_lease_liability": "operating_lease_liability",
    "finance_lease_liability": "finance_lease_liability",
    **_MARKER_FIELDS,
}

# ADDED 2026-08-26 (Quality pillar literature audit): Altman Z''-Score's Retained Earnings/
# Total Assets term - see sec_statements.py's get_balance_sheet() comment. Kept out of the
# shared _BALANCE_FIELD_MAPPING base dict deliberately: that dict is reused by every period's
# balance-sheet config, and each period has its own schema_cols frozenset - merging a mapping
# into the shared base for a column not every period's table has raises sec_base.py's "not in
# target schema" RuntimeError (self._schema_cols is hardcoded per-config, not introspected
# from the live DB). Live-caught 2026-08-26 when this exact mistake broke every quarterly
# fetch. Migration 1234 added `retained_earnings` to annual_balance_sheet; migration 1266
# (2026-09-07) added the equivalent to quarterly_balance_sheet too, via its own
# _QUARTERLY_BALANCE_EXTRA below rather than merging here - same pattern,
# _QUARTERLY_INCOME_EXTRA already established it for period_end. TTM still has no
# retained_earnings column - nothing in this codebase consumes a TTM Altman Z''-Score.
_ANNUAL_BALANCE_EXTRA = {"retained_earnings_accumulated_deficit": "retained_earnings"}

_CASHFLOW_FIELD_MAPPING = {
    "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
    # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): fallback-only, see
    # _OCF_FALLBACK-style comment on _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above and
    # sec_statements.py's get_cash_flow() comment for the live ASH evidence.
    "net_cash_provided_by_used_in_operating_activities_continuing_operations": "operating_cash_flow",
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
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live CTOS evidence: a standard
    # (not filer-specific) equipment-rental-fleet capex concept, never fetched at all.
    "payments_to_acquire_equipment_on_lease": "capex",
    # FIXED 2026-08-24 (goal: "Margin of Safety (DCF)" cash-flow-coverage audit): REIT-sector
    # capex concepts - see sec_statements.py's get_cash_flow() comment for the live AAT/AHT/
    # AHR/ABR evidence. Same "capex" target column as the PP&E-family concepts above.
    "payments_to_acquire_and_develop_real_estate": "capex",
    "payments_to_acquire_real_estate": "capex",
    "payments_for_capital_improvements": "capex",
    # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep, scored-symbol
    # follow-up beyond the earlier REIT capex sweep) - see sec_cash_flow.py's get_cash_flow()
    # comment for the live SKT (Tanger Inc) evidence: a standard REIT property-improvement
    # capex concept, never fetched at all.
    "real_estate_improvements": "capex",
    # FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification of
    # the 2026-08-24 fix's "pending separate verification" exclusion) - see sec_statements.py's
    # get_cash_flow() comment for the live SLG (SL Green) evidence: 8 straight years of real,
    # varying (including genuine $0) values under this concept since it replaced
    # "payments_to_acquire_real_estate" in SLG's FY2020 10-K.
    "payments_to_acquire_commercial_real_estate": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live DLR/REG evidence: a standard
    # (not filer-specific) real-estate-development-spend concept, never fetched at all.
    "payments_to_develop_real_estate_assets": "capex",
    # FIXED 2026-09-06 (capex_never_tagged_in_recent_filings sweep) - see
    # sec_cash_flow.py's get_cash_flow() comment for the live MRP (Millrose Properties)
    # evidence: a land-banking REIT's direct capex-equivalent concept, never fetched at
    # all. Same "capex" target column as the other REIT concepts above.
    "payments_to_acquire_land": "capex",
    # FIXED 2026-08-24 (same audit, insurance-sector continuation): insurer investment-
    # real-estate capex concepts - see sec_statements.py's get_cash_flow() comment for the
    # live MET/RGA/BHF/PFG/TRV/WRB evidence.
    "payments_to_acquire_real_estate_and_real_estate_joint_ventures": "capex",
    "payments_to_acquire_real_estate_held_for_investment": "capex",
    # FIXED 2026-08-29 (goal: "full data" audit continuation): oil & gas E&P sector capex
    # concepts - see sec_statements.py's get_cash_flow() comment for the live APA/AR/CHRD/
    # CRGY/AMPY/EGY/DVN evidence. Same "capex" target column as the PP&E-family concepts
    # above.
    "costs_incurred_oil_and_gas_property_acquisition_exploration_and_development_activities": "capex",
    "payments_to_acquire_oil_and_gas_property": "capex",
    "payments_to_explore_and_develop_oil_and_gas_properties": "capex",
    # FIXED 2026-08-29 (same audit, MGY/GTE follow-up): see sec_statements.py's get_cash_flow()
    # comment for the live evidence - a distinct concept from payments_to_acquire_oil_and_gas_
    # property above, not a duplicate.
    "payments_to_acquire_oil_and_gas_property_and_equipment": "capex",
    # FIXED 2026-08-29 (same audit, shipping-sector follow-up): identity key
    # ConsolidatedFinancialStatementsLoader.fetch_incremental() sets directly on rows for
    # symbols in utils/external/sec_custom_xbrl_concepts.py's CUSTOM_CAPEX_CONCEPTS - see
    # that module's docstring for why (real capex tagged under a filer-specific custom
    # XBRL extension taxonomy, structurally invisible to the companyfacts API this file's
    # normal concept-list extraction depends on). fallback_only (see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) so it never overwrites a real value the
    # normal SEC extraction already found.
    "custom_extension_vessel_capex": "capex",
    "custom_extension_capex_dimensioned_sum": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live CWT (water utility)
    # evidence. Same "capex" target column as the other sector-specific PP&E-family
    # concepts above.
    "payments_to_acquire_water_and_waste_water_systems": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, capex_never_
    # tagged_in_recent_filings continuation): see sec_statements.py's get_cash_flow()
    # comment on this concept - D (Dominion Energy) live-confirmed, a pure taxonomy
    # relabeling of the same real capex line, not fallback-only (value-identical to the
    # standard concept in every year both are present).
    "payments_for_proceeds_from_productive_assets": "capex",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_cash_flow() comment on
    # this concept - ED (Consolidated Edison) live-confirmed. Fallback-only (added to
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below): unlike the concept above, this is a
    # narrower "construction work in progress" sub-line that reports a genuinely smaller
    # figure than the standard concept in years both are present, so it must never
    # overwrite a real standard-concept value.
    "payments_for_construction_in_process": "capex",
    # FIXED 2026-09-05: fetched since the 2026-09-03 PSA fix to sec_statements.py's
    # get_cash_flow() concept list but never mapped here, so it was silently dropped at
    # transform() - PSA payments_of_capital_distribution=$2,303,381,000 FY2025
    # live-confirmed. Least-preferred/first in the concept list so last-listed-wins
    # ordering still lets a real DividendsCommonStock*/PaymentsOfDividends* value win.
    "payments_of_capital_distribution": "dividends_paid",
    # FIXED 2026-09-05: see sec_statements.py's get_cash_flow() comment on this concept -
    # BDC-specific (TRIN live-confirmed as the only concept it tags at all). Fallback-only
    # (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below): MAIN tags this AND a real,
    # materially larger DividendsCommonStock figure, so this must never overwrite a real
    # standard-concept value.
    "investment_company_dividend_distribution": "dividends_paid",
    "payments_of_dividends": "dividends_paid",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): CMS's
    # filer-specific custom XBRL extension dividends concept - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DIVIDEND_CONCEPTS docstring.
    # fallback_only (see _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) so it never overwrites a
    # real value the normal SEC extraction already found.
    "custom_extension_dividends_paid": "dividends_paid",
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
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): CVX
    # (Chevron) live-confirmed - see sec_statements.py's get_cash_flow() comment on this
    # concept. Fallback-only (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below), least
    # preferred of the three SBC concepts.
    "stock_option_plan_expense": "stock_based_compensation",
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
    # ADDED 2026-09-07 (goal: "SEC/XBRL missing data" + tie-out sweep): net_change_cash was
    # a declared schema column with zero rows ever populated (0/66,580) - fetched by none of
    # sec_cash_flow.py's concepts and mapped by no entry here. See that file's get_cash_flow()
    # comment on these 4 concepts for the live AMZN evidence (pre- and post-ASU-2016-18
    # generations, each with an ExcludingExchangeRateEffect sibling).
    "cash_and_cash_equivalents_period_increase_decrease_excluding_exchange_rate_effect": "net_change_cash",
    "cash_and_cash_equivalents_period_increase_decrease": "net_change_cash",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents_period_increase_decrease_excluding_exchange_rate_effect": "net_change_cash",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents_period_increase_decrease_including_exchange_rate_effect": "net_change_cash",
    **_MARKER_FIELDS,
}

# Quarterly rows carry fiscal_period ("Q1".."Q4"), which transform() converts to the
# integer fiscal_quarter column. Annual rows' fiscal_period ("FY") stays unmapped -
# annual tables have no fiscal_quarter column.
_QUARTERLY_EXTRA = {"fiscal_period": "fiscal_quarter"}

# Migration 1256 ("implausible values" sweep, quarterly fiscal-year-ordering bug): only
# quarterly_income_statement has a period_end column (see that migration's own header for
# why fiscal_year/fiscal_quarter alone can't reliably sort into true chronological order for
# non-December-fiscal-year-end filers) - kept separate from _QUARTERLY_EXTRA (shared by
# cashflow/balance sheet quarterly configs too) so this doesn't map a field into a column
# those two tables don't have.
_QUARTERLY_INCOME_EXTRA = {**_QUARTERLY_EXTRA, "period_end": "period_end"}

# ADDED 2026-09-07 (goal session: quarterly_balance_sheet missing retained_earnings column):
# every quarterly balance-sheet fetch already pulls the real SEC-tagged
# "RetainedEarningsAccumulatedDeficit" concept (see sec_balance_sheet.py's get_balance_sheet(),
# concept list is shared with annual) but quarterly_balance_sheet had no column to store it in,
# so it was discarded post-fetch with an "Unmapped SEC field" warning on every symbol, every
# quarter. Kept separate from _QUARTERLY_EXTRA (shared by cashflow/income-statement quarterly
# configs too) for the same reason _QUARTERLY_INCOME_EXTRA is separate above - merging into the
# shared dict would raise sec_base.py's "not in target schema" RuntimeError for the other two
# statement types, whose schema_cols don't have this column (see _ANNUAL_BALANCE_EXTRA's
# comment for the live 2026-08-26 incident this exact mistake caused).
_QUARTERLY_BALANCE_EXTRA = {**_QUARTERLY_EXTRA, "retained_earnings_accumulated_deficit": "retained_earnings"}


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
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "operating_expenses",
                    "net_income",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "research_development_expense",
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
            "field_mapping": {**_INCOME_FIELD_MAPPING, **_QUARTERLY_INCOME_EXTRA},
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
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
                    "operating_expenses",
                    "net_income",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "research_development_expense",
                    "shares_outstanding_basic",
                    "shares_outstanding_diluted",
                    "shares_outstanding_dei",
                    "income_tax_expense",
                    "pretax_income",
                    "period_end",
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
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
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
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_ANNUAL_BALANCE_EXTRA},
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
                    "accounts_payable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "noncontrolling_interest",
                    "retained_earnings",
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
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_QUARTERLY_BALANCE_EXTRA},
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
                    "accounts_payable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "noncontrolling_interest",
                    "retained_earnings",
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


class ConsolidatedFinancialStatementsLoader(SecEdgarStatementLoader, Q4DerivationSweepMixin):
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
        if self.statement_type == "cashflow":
            self._apply_custom_cashflow_extensions(symbol, rows)

        # FIX 2026-09-02 (goal: "SEC/XBRL missing data" audit, no_revenue_reported bucket):
        # same structural gap as the capex block above, for the top-line revenue figure -
        # see utils/external/sec_custom_xbrl_concepts.py's CUSTOM_REVENUE_CONCEPTS
        # docstring for the live-verified APA evidence (real $8.951B FY2025 consolidated
        # revenue tagged only under its own apachecorp.com extension concept, invisible to
        # the companyfacts-API-driven normal extraction). Cheap no-op for every other
        # symbol (dict lookup miss, zero extra network calls).
        if self.statement_type == "income" and symbol in CUSTOM_REVENUE_CONCEPTS:
            custom_revenue_by_year = fetch_custom_revenue(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_revenue_by_year:
                    row["custom_extension_revenue"] = custom_revenue_by_year[fiscal_year]

        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, pe_ratio/
        # peg_ratio investigation, BRK diluted_eps follow-up): DB's real net_income/basic_
        # eps/diluted_eps are tagged only under a single-explicitMember dimensioned context
        # (dei:LegalEntityAxis=db:ConsolidatedBankEntityMember), invisible to the normal
        # concept-list extraction the same way CUSTOM_DEBT_CONCEPTS's Berkshire debt is -
        # see utils/external/sec_custom_xbrl_concepts.py's CUSTOM_INCOME_DIMENSIONED_CONCEPTS
        # docstring for the live-verified evidence. Cheap no-op for every other symbol.
        if self.statement_type == "income" and symbol in CUSTOM_INCOME_DIMENSIONED_CONCEPTS:
            custom_income_fields = fetch_custom_income_dimensioned(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                for field_key, values_by_year in custom_income_fields.items():
                    if fiscal_year in values_by_year:
                        row[field_key] = values_by_year[fiscal_year]

        if self.statement_type == "balance":
            self._apply_custom_debt_extensions(symbol, rows)

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

    def _apply_custom_cashflow_extensions(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """Supplement `rows` with any of this loader's per-symbol custom-XBRL-extension
        cash-flow fallbacks, for symbols where the normal companyfacts-driven concept-list
        extraction structurally can't reach the real figure. Extracted out of
        fetch_incremental() to keep its own cyclomatic complexity in check (ruff C901) -
        purely a call-site split, no behavior change (same reasoning as
        _apply_custom_debt_extensions below, for the balance-sheet case).

        - CUSTOM_CAPEX_CONCEPTS (DHT/CMRE/...): filer-specific custom XBRL extension
          concept(s) -> custom_extension_vessel_capex (capex). See
          utils/external/sec_custom_xbrl_concepts.py's module docstring.
        - CUSTOM_CAPEX_DIMENSIONED_CONCEPTS (NJR/MUX): real capex split across N axis
          members with no consolidated total -> custom_extension_capex_dimensioned_sum
          (capex). See that module's CUSTOM_CAPEX_DIMENSIONED_CONCEPTS docstring.
        - CUSTOM_DIVIDEND_CONCEPTS (CMS/SPG/RS/HUBB): filer-specific custom XBRL extension
          (or, for HUBB, a mistagged standard) dividends concept ->
          custom_extension_dividends_paid (dividends_paid). See that module's
          CUSTOM_DIVIDEND_CONCEPTS docstring.

        Cheap no-op for every symbol in none of these registries (dict lookup miss, zero
        extra network calls) - only called when self.statement_type == "cashflow".
        """
        if symbol in CUSTOM_CAPEX_CONCEPTS:
            custom_capex_by_year = fetch_custom_capex(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_capex_by_year:
                    row["custom_extension_vessel_capex"] = custom_capex_by_year[fiscal_year]

        if symbol in CUSTOM_CAPEX_DIMENSIONED_CONCEPTS:
            dimensioned_capex_by_year = fetch_custom_capex_dimensioned_sum(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in dimensioned_capex_by_year:
                    row["custom_extension_capex_dimensioned_sum"] = dimensioned_capex_by_year[fiscal_year]

        if symbol in CUSTOM_DIVIDEND_CONCEPTS:
            custom_dividends_by_year = fetch_custom_dividends(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_dividends_by_year:
                    row["custom_extension_dividends_paid"] = custom_dividends_by_year[fiscal_year]

    def _apply_custom_debt_extensions(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """Supplement `rows` with any of this loader's per-symbol custom-XBRL-extension
        debt fallbacks, for symbols where the normal companyfacts-driven concept-list
        extraction structurally can't reach the real figure. Extracted out of
        fetch_incremental() to keep its own cyclomatic complexity in check (ruff C901) -
        purely a call-site split, no behavior change.

        - CUSTOM_DEBT_CONCEPTS (BRK.A/BRK.B): dimensioned-sum extraction, single combined
          figure -> custom_extension_total_debt (long_term_debt). See
          utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS module comment.
        - CUSTOM_DEBT_LONGTERM_CONCEPTS/CUSTOM_DEBT_SHORTTERM_CONCEPTS (AES): plain
          filer-extension concepts, real current/noncurrent split preserved ->
          custom_extension_total_debt (long_term_debt) / custom_extension_total_debt_current
          (short_term_debt). See that module's CUSTOM_DEBT_LONGTERM_CONCEPTS comment.

        Cheap no-op for every symbol in none of these registries (dict lookup miss, zero
        extra network calls) - only called when self.statement_type == "balance".
        """
        if symbol in CUSTOM_DEBT_CONCEPTS:
            custom_debt_by_year = fetch_custom_debt(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_debt_by_year:
                    row["custom_extension_total_debt"] = custom_debt_by_year[fiscal_year]
        if symbol in CUSTOM_DEBT_LONGTERM_CONCEPTS:
            custom_debt_lt_by_year = fetch_custom_debt_longterm(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_debt_lt_by_year:
                    row["custom_extension_total_debt"] = custom_debt_lt_by_year[fiscal_year]
        if symbol in CUSTOM_DEBT_SHORTTERM_CONCEPTS:
            custom_debt_st_by_year = fetch_custom_debt_shortterm(symbol, self._sec_client)
            for row in rows:
                fiscal_year = row.get("fiscal_year")
                if fiscal_year in custom_debt_st_by_year:
                    row["custom_extension_total_debt_current"] = custom_debt_st_by_year[fiscal_year]

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

    def _reject_implausible_shares_outstanding(self, transformed: list[dict[str, Any]]) -> None:
        """Reject shares_outstanding_basic/diluted values that are confidently wrong due to
        SEC's companyfacts API not always normalizing a filer's "reported in thousands"
        inline-XBRL scale attribute. Mutates `transformed` in place.

        FIXED 2026-08-21 (goal session - broad shares_outstanding cross-check audit,
        follow-up to the BRK.A/HEI dual-class fix): live-confirmed against HUB Group's real
        companyfacts JSON (CIK 0000940942): WeightedAverageNumberOfSharesOutstandingBasic
        for FY2025Q3 is tagged val=60066 (a real share count in the tens of millions
        reported "in thousands", not 60,066 actual shares). ~95 active symbols showed this
        exact ~1,000x-too-small pattern when cross-checked against
        company_info_sec.shares_outstanding (an independently-extracted, unaffected
        source). Rejects values below MIN_PLAUSIBLE_SHARES_OUTSTANDING (100,000, same floor
        already used in load_company_info_sec.py) rather than relying on a downstream
        consumer's guard to always be present.

        FIXED 2026-08-21 (same session, follow-up): the absolute floor above only catches
        the thousands-scale bug for SMALLER companies - a large-cap's real share count
        divided by 1000 can easily still clear 100,000 (e.g. NTNX's real ~270M shares,
        stored as 267,479 - "267,479 thousand" per the unconverted XBRL scale= attribute -
        sails right past the floor). Bulk cross-check of
        annual_income_statement.earnings_per_share against
        net_income/shares_outstanding_basic surfaced 891 rows where the implied EPS is
        ~1,000x the reported EPS - live-confirmed NTNX FY2025 exactly this way: stored
        shares_outstanding_basic=267,479 vs company_info_sec's independently-extracted
        270,320,509 (real value, ~1010x higher). Extends the guard with a relative
        cross-check against company_info_sec.shares_outstanding (the same independent
        source load_sec_valuations.py's own 20x scale-mismatch guard already trusts for
        exactly this purpose), not just an absolute floor.

        FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" / tie-out sweep): the
        relative cross-check just below only runs when company_info_sec.shares_outstanding
        has a real value for the symbol - NMR (Nomura Holdings, a Japanese 20-F filer) has
        NULL there, so its shares_outstanding_diluted sailed straight through with no upper
        bound at all. Live-verified via SEC's own companyfacts API
        (WeightedAverageNumberOfDilutedSharesOutstanding, CIK0001163653): the RAW SEC-tagged
        fact itself is 3,041,190,068,000,000 "shares" for FY2026 (and every other fiscal
        year on file, 2018-2026) - a real filer/filing-agent XBRL tagging error on SEC's
        side, not an extraction bug in this codebase (net_income and diluted_eps for the
        same rows are both correct and consistent with each other: implied share count
        net_income/diluted_eps ~= 3.04 BILLION, exactly 1,000,000x smaller than the tagged
        3.04 QUADRILLION). An absolute ceiling closes this gap independent of whether a
        reference value exists. Calibrated against every real value already in this
        table (2026-09-06 DB scan): the largest genuine share counts on file are NVDA
        (~24.5-25.1B, real post-split), MFG/Mizuho Financial (~24.5-25.4B, another large
        Japanese bank ADR), CIGI (~36-38B), AKTX (~24-67B) and UXIN (~63B) - all comfortably
        under 100B even for the most heavily-diluted real filers. 500B leaves ~7x headroom
        above the largest genuine value in this table while still catching NMR's (and any
        similar) many-orders-of-magnitude tagging error.
        """
        min_plausible_shares_outstanding = 100_000
        max_plausible_shares_outstanding = 500_000_000_000
        for row in transformed:
            for field in ("shares_outstanding_basic", "shares_outstanding_diluted"):
                val = row.get(field)
                if val is not None and 0 < val < min_plausible_shares_outstanding:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={val:,.0f} is implausibly small (< {min_plausible_shares_outstanding:,}) "
                        "- likely an unconverted 'reported in thousands' XBRL value SEC's "
                        "companyfacts API didn't normalize. Rejecting rather than storing a "
                        "confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")
                elif val is not None and val > max_plausible_shares_outstanding:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={val:,.0f} is implausibly large (> {max_plausible_shares_outstanding:,}) "
                        "- likely a real filer/filing-agent XBRL tagging error (e.g. NMR's "
                        "~1,000,000x-too-large tagged share count). Rejecting rather than "
                        "storing a confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")

        shares_check_symbols = sorted({str(row.get("symbol")) for row in transformed if row.get("symbol")})
        reference_shares: dict[str, float] = {}
        if shares_check_symbols:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT symbol, shares_outstanding FROM company_info_sec "
                        "WHERE symbol = ANY(%s) AND shares_outstanding > 0",
                        (shares_check_symbols,),
                    )
                    reference_shares = {sym: float(val) for sym, val in cur.fetchall()}
            except Exception as e:
                logger.debug(f"[{self.table_name}] company_info_sec cross-check lookup failed (non-fatal): {e}")

        if not reference_shares:
            return
        for row in transformed:
            symbol = row.get("symbol")
            reference = reference_shares.get(symbol) if symbol else None
            if not reference:
                continue
            for field in ("shares_outstanding_basic", "shares_outstanding_diluted"):
                val = row.get(field)
                if val is None or val <= 0:
                    continue
                ratio = reference / float(val)
                if ratio > 20 or ratio < 1 / 20:
                    # BUG FOUND 2026-08-21 (goal session - log-accuracy audit): `{ratio:.0f}x`
                    # only reads sensibly when val is too SMALL (ratio > 1). When val is too
                    # LARGE instead (ratio < 1, e.g. ALMU FY2026's shares_outstanding_basic=
                    # 17,354,370,000 vs company_info_sec's 18,305,335 - the ~1000x-too-large
                    # mirror image of the same scale bug), `ratio:.0f` rounds to "0x",
                    # printing the nonsensical "disagrees ... by 0x" - live-confirmed 241
                    # occurrences in a single run. Report the magnitude symmetrically
                    # (always >= 1x) and say which side is off so the log is actually usable
                    # for diagnosing which direction the scale error went.
                    times_off = ratio if ratio >= 1 else 1 / ratio
                    direction = "too small" if ratio >= 1 else "too large"
                    logger.warning(
                        f"[{self.table_name}] {symbol} FY{row.get('fiscal_year')}: {field}={val:,.0f} "
                        f"disagrees with company_info_sec.shares_outstanding={reference:,.0f} - "
                        f"{field} looks {times_off:.0f}x {direction} - likely an unconverted "
                        "'reported in thousands' XBRL scale error the absolute floor above didn't "
                        "catch. Rejecting rather than storing a confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")

    def _fill_derived_eps(self, transformed: list[dict[str, Any]]) -> None:
        """Fill earnings_per_share when the filer never tagged EarningsPerShareBasic/Diluted
        at all, using data this same row already carries. Mutates `transformed` in place.

        ADDED 2026-09-01 (goal: data-loading gap investigation). Live-verified DB-wide: 7,397
        annual_income_statement rows have revenue but NULL earnings_per_share; 77 of those
        already carry a real diluted_eps (a different XBRL concept, EarningsPerShareDiluted,
        mapped to its own column since the 2026-07-28 fix above but never used as a fallback
        for earnings_per_share itself) and 4,434 have net_income plus a usable share count
        that could derive one. Both recover real signal that growth_metrics/quality_metrics/
        value_metrics currently discard outright (eps_growth_1y/3y/5y, EPS-based quality
        inputs) purely because one specific EPS tag was never filed - the filer still reported
        net income and share count, which is all EPS is defined as.

        Order matters: called AFTER _reject_implausible_shares_outstanding (so the shares this
        derives from have already survived both the absolute-floor and the company_info_sec
        cross-check scale guards above) and BEFORE _reject_implausible_eps (so a still-bad
        derived value gets the same implied-shares/absolute-magnitude rejection a directly-
        reported one would). Both source and derived values come from the SAME row/filing, so
        unlike the shares=net_income/eps derivation in load_sec_valuations.py (which mixed
        values that turned out to come from inconsistently-converted sources, see that file's
        MAX_PLAUSIBLE_SHARES_OUTSTANDING comment for the NMR case) there's no cross-source
        currency/scale mismatch possible here - net_income and shares_outstanding_basic/
        diluted are both this filer's own same-period, same-currency figures.

        Never overwrites a real reported earnings_per_share - only fills when it's still None
        after direct XBRL mapping.

        CROSS-CHECKS ADDED 2026-09-01 (same pass, live-caught while sanity-checking derived
        values before backfilling): dividing by a scale-corrupted share count would derive a
        plausible-looking-but-wrong EPS, and neither existing guard reliably catches that here
        - _reject_implausible_shares_outstanding's company_info_sec cross-check only fires when
        a reference row exists (foreign large-caps without one, e.g. VALE, sail through), and
        the absolute floor (100,000) doesn't catch a corrupted value that's still comfortably
        above it (VALE's own FY2008 shares_outstanding_basic=5,062,148 would derive
        ~$2,611/share, ~1030x its own FY2009 row of 5,212,406,000). So before dividing:
        1. Cross-check against company_info_sec.shares_outstanding when a reference exists
           (same 20x threshold as _reject_implausible_shares_outstanding above).
        2. Otherwise cross-check against this SAME symbol's OWN other fiscal years already
           present in this batch (same idea as EPS_SPLIT_GUARD_CLEAN_MULTIPLES's adjacent-year
           scan in load_value_quality_growth_metrics.py, applied here to catch a scale error
           rather than a real split).
        3. If NEITHER cross-check has anything to compare against (a symbol with exactly one
           ever-fetched share-count data point and no company_info_sec row - live-confirmed on
           ATHS: shares_outstanding_basic=203,805 alone would derive an uncorroborated
           ~$13,301/share), don't derive at all rather than trust a single, uncorroborated
           number - same "missing scores are better than fabricated heuristics" governance this
           file already applies elsewhere, just applied to a single input instead of a score.
        """
        # First fill the zero-risk diluted_eps fallback - no cross-check needed, it's already a
        # real reported XBRL value under a different concept.
        needs_division: list[dict[str, Any]] = []
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation, Visa
        # investigation): a filer whose EPS/weighted-average-share concepts are tagged
        # EXCLUSIVELY with a required dimension (live-confirmed via Visa's real SEC data:
        # its 2025 10-K's own R-file plainly shows "us-gaap:EarningsPerShareBasic"/
        # "WeightedAverageNumberOfSharesOutstandingBasic" with real values on the primary
        # income statement, but all three concepts 404 on SEC's own live companyconcept
        # API and are entirely absent from companyfacts - the same aggregation gap this
        # loader's own get_income_statement() draws from) has NONE of shares_outstanding_
        # diluted/basic/dei on this row at all, so the existing needs_division gate above
        # never even considers it - despite company_info_sec.shares_outstanding having a
        # real, independently-extracted value (Visa: 1,687,629,770, via that loader's own
        # dei:EntityCommonStockSharesOutstanding/filing-text fallback chain, a completely
        # separate, non-dimensional extraction path). Tracked separately from
        # needs_division since there is no per-row share count to corroborate the
        # company_info_sec reference AGAINST here (the whole point is none exists) - the
        # reference is used directly, trusting its own already-applied plausibility floor
        # (MIN_PLAUSIBLE_SHARES_OUTSTANDING, load_sec_valuations.py) rather than guessed.
        #
        # KNOWN LIMITATION (found 2026-09-05, same investigation, verified against Visa's
        # own real numbers before shipping): company_info_sec.shares_outstanding is a
        # SINGLE current snapshot, not a per-fiscal-year history - every fiscal year for a
        # symbol that reaches this tier divides by the exact same share count. This is
        # fine for a single-year consumer (pe_ratio's TTM EPS), but for a MULTI-YEAR
        # consumer (growth_metrics' eps_growth_1y/3y/5y, which compares two derived years
        # against each other), the constant divisor cancels out of the ratio entirely -
        # the resulting "EPS growth rate" becomes mathematically identical to net_income
        # growth, silently losing any real EPS growth contributed by share buybacks
        # (or diluted by issuance). Live-quantified via Visa (an active repurchaser):
        # real FY25-vs-FY24 basic EPS growth was +4.93% ($10.22 vs $9.74, both real
        # reported values) - derived-from-this-tier growth using the same net_income
        # figures would only show +1.62%, roughly 1/3 of the real rate. Not fabricated or
        # wrong-signed, just a real, quantifiable floor on precision for any buyback-
        # active symbol in this tier's population - the true fix (recovering the exact
        # per-year reported EPS) requires parsing each fiscal year's raw XBRL instance
        # document for a StatementClassOfStockAxis-dimensioned EarningsPerShareBasic fact
        # (confirmed technically feasible via Visa's real filing - see this session's
        # notes - but needs the same per-symbol dimensional-member verification the
        # sec_xbrl_segments.py segment-revenue fixes already do one company at a time,
        # not a blanket rule), deliberately not attempted here.
        needs_reference_only_division: list[dict[str, Any]] = []
        for row in transformed:
            if row.get("earnings_per_share") is not None:
                continue
            diluted = row.get("diluted_eps")
            if diluted is not None:
                row["earnings_per_share"] = diluted
                continue
            net_income = row.get("net_income")
            if net_income is None:
                continue
            # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, PJT
            # follow-up): shares_outstanding_diluted/basic (period weighted-average concepts)
            # are the preferred denominator, but a filer that never tags EITHER - live-
            # confirmed via PJT Partners (net_income real every year 2019-2026, no
            # EarningsPerShareBasic/Diluted OR any WeightedAverageNumberOfShares* concept
            # anywhere in its real companyfacts history since 2016) - can still have a real,
            # non-fabricated share count via dei:EntityCommonStockSharesOutstanding (the
            # mandatory SEC cover-page fact, a point-in-time count rather than a period
            # average, but the same "genuinely reported, not guessed" standard already applied
            # to shares_outstanding_dei elsewhere in this codebase as a last-resort shares
            # source). Last in the fallback chain - never overrides a real period-average count.
            shares = (
                row.get("shares_outstanding_diluted")
                or row.get("shares_outstanding_basic")
                or row.get("shares_outstanding_dei")
            )
            if shares is None or shares <= 0:
                # FIXED 2026-09-05 (same Visa investigation, caught by this file's own
                # regression suite before shipping): shares is None here for TWO very
                # different reasons that look identical at this point in the pipeline -
                # (a) genuinely never tagged (Visa's real case), or (b) a real value WAS
                # tagged but _reject_implausible_shares_outstanding (which runs before
                # this method - see this function's own docstring) already nulled it for
                # being a scale-corrupted VALE-style outlier. Using company_info_sec
                # directly is only safe for (a) - for (b), the filer's own reporting for
                # this exact fiscal year is already known-unreliable, so silently
                # substituting a different source's share count would defeat the
                # rejection that just ran. Skip whenever this exact row+field pair is in
                # _explicit_null_rejections (case (b)); a bare `shares is None` case that
                # was never even in the raw fetch (case (a)) never appears there.
                pk_cols = list(self._bulk_insert_mgr.primary_key)
                pk_key = tuple(row.get(pk) for pk in pk_cols)
                was_rejected = any(
                    tuple(pk_values.get(pk) for pk in pk_cols) == pk_key
                    and field in ("shares_outstanding_basic", "shares_outstanding_diluted")
                    for pk_values, field in self._explicit_null_rejections
                )
                # A field that's present but non-positive (e.g. an explicit 0, not simply
                # absent) is itself a known-bad reported value, the same "don't trust this
                # filing's own share count, but don't just substitute a different source
                # either" situation as an explicit rejection above - not the "never tagged
                # at all" case company_info_sec is meant to fill in for.
                _share_field_values = (
                    row.get(f)
                    for f in ("shares_outstanding_diluted", "shares_outstanding_basic", "shares_outstanding_dei")
                )
                any_field_reported_non_positive = any(v is not None and v <= 0 for v in _share_field_values)
                if not was_rejected and not any_field_reported_non_positive:
                    needs_reference_only_division.append(row)
                continue
            needs_division.append(row)

        if not needs_division and not needs_reference_only_division:
            return

        # Only issue the company_info_sec round-trip when at least one row actually needs it -
        # same "skip the query in the common healthy case" pattern the downgrade-guard lookup
        # above already uses.
        symbols_needing_division = sorted(
            {str(row["symbol"]) for row in (*needs_division, *needs_reference_only_division) if row.get("symbol")}
        )
        reference_shares: dict[str, float] = {}
        if symbols_needing_division:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol, shares_outstanding FROM company_info_sec "
                    "WHERE symbol = ANY(%s) AND shares_outstanding > 0",
                    (symbols_needing_division,),
                )
                reference_shares = {sym: float(val) for sym, val in cur.fetchall()}

        shares_history_by_symbol: dict[str, list[float]] = {}
        for row in transformed:
            symbol = row.get("symbol")
            if not symbol:
                continue
            for field in ("shares_outstanding_diluted", "shares_outstanding_basic", "shares_outstanding_dei"):
                val = row.get(field)
                if val:
                    shares_history_by_symbol.setdefault(str(symbol), []).append(float(val))

        for row in needs_division:
            net_income = row["net_income"]
            shares = (
                row.get("shares_outstanding_diluted")
                or row.get("shares_outstanding_basic")
                or row.get("shares_outstanding_dei")
            )
            assert shares is not None  # narrows for mypy; needs_division's filter already guarantees this
            symbol = str(row.get("symbol") or "")

            reference = reference_shares.get(symbol)
            if reference:
                ratio = reference / float(shares)
                if ratio > 20 or ratio < 1 / 20:
                    continue
            else:
                siblings = [v for v in shares_history_by_symbol.get(symbol, []) if v != float(shares)]
                if not siblings:
                    continue
                ratio = statistics.median(siblings) / float(shares)
                if ratio > 20 or ratio < 1 / 20:
                    continue
            row["earnings_per_share"] = float(net_income) / float(shares)

        for row in needs_reference_only_division:
            symbol = str(row.get("symbol") or "")
            reference = reference_shares.get(symbol)
            if not reference:
                continue
            row["earnings_per_share"] = float(row["net_income"]) / reference

    def _reject_implausible_eps(self, transformed: list[dict[str, Any]]) -> None:
        """Reject earnings_per_share/diluted_eps values that are confidently wrong due to
        filer-side XBRL tagging errors, not a SEC API normalization issue like the shares
        guard above. Mutates `transformed` in place.

        FOUND 2026-08-23 (goal session: real-money-readiness "why does earnings_per_share
        say -$24,852,333/share" audit): live-confirmed via GIBO's real companyfacts JSON -
        the filer itself tagged EarningsPerShareBasic under the correct "USD/shares" unit
        but with the SAME raw value as that year's NetIncomeLoss (FY2023: both exactly
        -12,117,569; FY2024: both exactly -24,852,333) - i.e. the filer's own XBRL reports
        total net income as if it were per-share, not a unit-parsing bug on our side (no
        currency/unit filter would catch this - the unit tag is correct, the underlying
        number is wrong). Also live-confirmed on BTTC, HQ, GROY, BRUN, and EP's FY2013/2014
        (eps==net_income exactly), plus a related /1000 variant (FLOC: eps=32,729 vs
        net_income=32,729,000 - implied ~1,000 shares). No consumer downstream (growth_metrics'
        eps_growth_*) reliably catches this: the resulting YoY growth RATIO between two
        similarly-corrupted years can look like an ordinary percentage (GIBO's eps_growth_1y
        computed a plausible-looking -100.00), so a wrong-by-millions per-share value was
        reaching stock_scores/growth_metrics undetected. Implied-shares floor deliberately
        low (10,000) - BRK.A (~1.6M real shares) and foreign large-caps reporting in local
        currency (BSAC ~471M CLP shares, EC ~2.06B COP shares) all clear it comfortably;
        only implies-basically-no-real-float cases like the ones above trip it.
        """
        min_plausible_implied_shares = 10_000
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, eps_
        # reconciliation follow-up): the implied-shares floor above only catches the
        # "eps==net_income" extreme (implies basically zero real shares) - it does NOT catch
        # a filer-side decimal/scale error that lands on a still-plausible-looking implied
        # share count. Live-confirmed via NRC (National Research Corporation, CIK 0000070487):
        # FY2025 10-K tags EarningsPerShareDiluted=$50.00 against real NetIncomeLoss=
        # $11,600,000 - implied_shares = 232,000, comfortably above the 10,000 floor (so the
        # check above never fires), but NRC's OWN real weighted-average diluted share count
        # for the SAME row is 22,396,000 - a ~96x gap, and $50/share is obviously wrong for a
        # company whose real diluted EPS is ~$0.52 (a real, filed 10-K/Q shows the correct
        # scale in adjacent periods: FY2024 diluted_eps=$1.04 against 23,743,000 shares, an
        # entirely normal-looking figure). Unlike the shares_outstanding guard above, this
        # row already carries its own real share count from the SAME extraction - a much
        # tighter, symbol-specific cross-check than the earlier absolute floor, so a generous
        # 10x tolerance (well outside any real dilution/NCI/preferred-dividend spread, which
        # tie_out.py's own eps_reconciliation check already tolerates at 15%) still leaves no
        # room for a genuine EPS to trip it while catching this exact scale-error shape.
        eps_shares_field = {
            "earnings_per_share": "shares_outstanding_basic",
            "diluted_eps": "shares_outstanding_diluted",
        }
        max_implied_vs_reported_shares_ratio = 10.0
        # BUG FOUND 2026-08-31 (goal session: "let's check the logs" sweep of live loader
        # output): SWK/UAMY quarterly rows hit the raw NUMERIC(12,4) column-overflow guard in
        # sec_base.py instead of this smarter rejection (e.g. "earnings_per_share=150330000")
        # - live-confirmed the reason: this function's implied-shares check requires
        # net_income to be present and non-zero for the SAME row, but a quarterly row can
        # have net_income missing/None while still carrying a garbage per-share value from
        # the identical filer-side mistagging bug this function already exists to catch. The
        # `continue` above skipped the whole row, so the garbage value reached the DB-insert
        # layer's overflow guard instead - which fails safe (data_unavailable) but with a
        # worse error and none of the informative "why" this function provides. Add an
        # absolute-magnitude fallback that doesn't need net_income at all: no real company has
        # ever reported anywhere near $1,000,000/share EPS in a single period (BRK.A's real
        # historical extremes, driven by unrealized investment gains, stay under $200,000/share
        # even in exceptional years - this floor leaves >5x headroom above that).
        max_plausible_abs_eps = 1_000_000
        for row in transformed:
            net_income = row.get("net_income")
            has_net_income = net_income is not None and net_income != 0
            for field in ("earnings_per_share", "diluted_eps"):
                eps = row.get(field)
                if eps is None or eps == 0:
                    continue
                if has_net_income:
                    assert net_income is not None  # narrows for mypy; has_net_income already guarantees this
                    implied_shares = abs(float(net_income) / float(eps))
                    if implied_shares < min_plausible_implied_shares:
                        logger.warning(
                            f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                            f"{field}={eps} implies only {implied_shares:,.0f} shares outstanding "
                            f"against net_income={net_income:,.0f} - implausibly low for any real "
                            "public float. Filer-side XBRL tagging error (raw net income reported "
                            "as per-share), not a currency/scale issue. Rejecting rather than "
                            "storing a confidently-wrong per-share value."
                        )
                        row[field] = None
                        self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                        continue
                    reported_shares = row.get(eps_shares_field[field])
                    if reported_shares is not None and float(reported_shares) > 0:
                        shares_ratio = max(implied_shares, float(reported_shares)) / min(
                            implied_shares, float(reported_shares)
                        )
                        if shares_ratio > max_implied_vs_reported_shares_ratio:
                            logger.warning(
                                f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                                f"{field}={eps} implies {implied_shares:,.0f} shares against "
                                f"net_income={net_income:,.0f}, but this row's own "
                                f"{eps_shares_field[field]}={float(reported_shares):,.0f} - a "
                                f"{shares_ratio:,.0f}x gap. Filer-side decimal/scale tagging error "
                                "(NRC-shaped: a plausible-looking implied share count that still "
                                "disagrees with this row's own real share count), not a currency/"
                                "scale issue. Rejecting rather than storing a confidently-wrong "
                                "per-share value."
                            )
                            row[field] = None
                            self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                            continue
                if abs(float(eps)) > max_plausible_abs_eps:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={eps} exceeds ${max_plausible_abs_eps:,}/share - implausible for "
                        "any real filer regardless of net_income availability (net_income was "
                        f"{'unavailable/zero' if not has_net_income else f'{net_income:,.0f}'} for "
                        "this row, so the implied-shares cross-check above couldn't run). Same "
                        "filer-side XBRL tagging error class, caught via absolute magnitude "
                        "instead. Rejecting rather than storing a confidently-wrong per-share "
                        "value or letting it hit the raw column-overflow guard downstream."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")

    def _reject_scale_mismatched_net_income(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `net_income` when it's a clean 1,000x or 1,000,000x-too-small multiple of
        (pretax_income - income_tax_expense) - the same filer-side "reported in thousands/
        millions under a whole-dollar concept" scale error `_reject_implausible_eps`'s own
        docstring already names (the FLOC case: eps=32,729 vs net_income=32,729,000), just
        caught here from the other side of that same identity, for rows where pretax_income/
        income_tax_expense happen to carry the correct scale while net_income itself doesn't.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, pretax_to_
        net_income follow-up - this identity's own 593-symbol tie-out failure count hadn't
        moved all session despite several sibling fixes landing). Live-confirmed via 3 of
        this check's own top offenders: MVBF (pretax=$36,850,000, tax=$9,928,000,
        net_income=$26,922 - pretax-tax=$26,922,000, an EXACT 1,000x match), KWY
        (pretax=-$14,004,000, tax=-$3,752,000, net_income=-$10,252 - pretax-tax=-$10,252,000,
        exact match), NXPL (pretax=-$10,463,000, tax=$0, net_income=-$10,463 - exact match).
        Unlike `_reject_implausible_eps`'s fp=None non-integer detector (which catches this
        exact bug shape but only for EPS, and only for proxy-statement-sourced facts), this
        targets net_income directly, regardless of source form, since a clean multiplicative
        match against this row's own pretax_income/income_tax_expense is precise enough on
        its own - no reliance on the fact's form/fp (already gone by the time `transformed`
        rows reach this stage).

        Deliberately does NOT attempt to "fix" the value by multiplying it back up: with
        `pretax_income - income_tax_expense` itself sometimes wrong instead (ambiguous from
        magnitude alone, same as `_reject_implausible_eps`'s MVBF/TE-shaped mirror case),
        nulling is the same "honest NULL over a confidently-wrong number" choice made
        throughout this file - either value being wrong corrupts the same downstream ratios
        (ROE, net_margin, ...) equally, so which one gets nulled doesn't change the outcome.
        Tolerance (20% of the scaled comparison, not tie_out.py's tighter 10%/$500K) is
        deliberately loose: this only needs to recognize "unmistakably the same multiplicative
        family", not reconcile the identity precisely - genuine NCI/discontinued-operations
        noise this file's own pretax_to_net_income WARN check already tolerates can push a
        real match a few points off 1,000x/1,000,000x without this guard losing confidence
        that it's still the same scale-error shape.
        """
        min_plausible_abs_expected = 100_000.0
        scale_tolerance_pct = 0.20
        for row in transformed:
            net_income = row.get("net_income")
            pretax_income = row.get("pretax_income")
            income_tax_expense = row.get("income_tax_expense")
            if net_income is None or net_income == 0 or pretax_income is None or income_tax_expense is None:
                continue
            expected = float(pretax_income) - float(income_tax_expense)
            if abs(expected) < min_plausible_abs_expected:
                continue
            for scale in (1_000, 1_000_000):
                scaled_net_income = float(net_income) * scale
                relative_error = abs(scaled_net_income - expected) / abs(expected)
                if relative_error <= scale_tolerance_pct:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"net_income={net_income:,.0f} is a {scale:,}x-too-small match against "
                        f"pretax_income({pretax_income:,.0f}) - income_tax_expense("
                        f"{income_tax_expense:,.0f}) = {expected:,.0f} (net_income*{scale:,} = "
                        f"{scaled_net_income:,.0f}, {relative_error:.1%} residual). Filer-side "
                        "scale tagging error (reported in thousands/millions under a whole-"
                        "dollar concept), not a currency issue. Rejecting rather than storing a "
                        "confidently-wrong net_income."
                    )
                    row["net_income"] = None
                    self._record_explicit_null_rejection(row, "net_income", "net_income_scale_error")
                    break

    def _reject_implausible_gross_profit(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `gross_profit` when it exceeds revenue by more than 3x while cost_of_revenue
        is a real, positive figure - not a tolerance/measurement-noise check like
        algo/monitoring/data_patrol/checks/tie_out.py's own gross_profit_identity WARN (2%
        tolerance, still exploratory per that file's own docstring), but a hard mathematical
        impossibility check: gross_profit = revenue - cost_of_revenue, so with a real positive
        cost_of_revenue on the same row, gross_profit can never legitimately exceed revenue at
        all, let alone by 3x+.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
        identity follow-up). Live-confirmed via HCTI: FY2025 10-K/A tags GrossProfit=
        $1,235,000,000 against real revenue=$13,891,000 and cost_of_revenue=$12,001,000 (real
        FY2025 gross profit is ~$1.89M - HCTI's own Q2 2026 10-Q shows a comparable-scale
        $4.459M half-year gross profit, confirming the real business is nowhere near
        $1.235B) - an ~89x overstatement, a filer/filing-agent tagging error in the amendment
        itself. Not a clean round-multiple scale error (unlike `_reject_scale_mismatched_
        net_income` above) - no single scale factor to detect, so this uses the simpler
        "impossible under the definitional identity" signal instead. 3x threshold (not 1x)
        deliberately leaves room for a company reporting an adjusted/non-strictly-definitional
        gross profit figure that legitimately differs somewhat from the raw subtraction -
        only rejects an extreme, order-of-magnitude-style violation.
        """
        max_plausible_gross_profit_to_revenue_ratio = 3.0
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or revenue <= 0 or cost_of_revenue is None or cost_of_revenue <= 0:
                continue
            if gross_profit is None:
                continue
            if float(gross_profit) > float(revenue) * max_plausible_gross_profit_to_revenue_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"gross_profit={gross_profit:,.0f} exceeds {max_plausible_gross_profit_to_revenue_ratio:.0f}x "
                    f"revenue({revenue:,.0f}) while cost_of_revenue({cost_of_revenue:,.0f}) is a real positive "
                    "figure - mathematically impossible under gross_profit = revenue - cost_of_revenue. "
                    "Filer-side tagging error, not a currency/scale issue with a clean multiple. Rejecting "
                    "rather than storing a confidently-wrong gross_profit."
                )
                row["gross_profit"] = None
                self._record_explicit_null_rejection(row, "gross_profit", "implausible_gross_profit_scale_error")

    def _reject_stale_gross_profit_without_fresh_concept(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null a stale `gross_profit` value for any (symbol, fiscal_year) where this
        run's fresh SEC extraction has both revenue and cost_of_revenue but no fresh
        gross_profit fact of its own. Mutates nothing in `transformed` directly - records the
        rejection so post_run() force-nulls the DB column, bypassing preserve_on_missing_
        fields' COALESCE (see the 2026-08-23 fix comment in __init__ for why that's necessary
        for a deliberate rejection, as opposed to a transient fetch gap).

        ADDED 2026-09-06 (goal session: tie-out-checker follow-up on the gross_profit_identity
        magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/tie_out.py's Round 2
        docstring). Live-confirmed via real SEC companyfacts JSON: ABBV/GILD/AMGN/ABT's only
        "GrossProfit" XBRL facts are a supplementary Q4-only quarterly-data-table stub (e.g.
        ABBV FY2024: start=2024-10-01/end=2024-12-31, a 91-day span) - correctly rejected by
        the annual span_days<330 check in sec_statements_entry_resolution.py, so the CURRENT
        extraction code produces no gross_profit value for these filers at all (confirmed via a
        direct get_income_statement() call: fresh rows have revenue/cost_of_revenue populated,
        no "gross_profit" key). The non-NULL gross_profit already stored for these rows
        (ABBV FY2025: $12.066B, live-identified by the tie-out checker as failing revenue
        ($61.16B) - cost_of_revenue($18.204B) ~= gross_profit by a ~3.6x margin - the real
        implied figure is ~$42.96B) is a leftover from BEFORE that span check existed, silently
        protected ever since by preserve_on_missing_fields' COALESCE. fetch_incremental()
        always refetches a symbol's FULL XBRL history in one company-facts API call (no
        incremental date cutoff), so this run's absence of a gross_profit fact for a fiscal
        year that DOES have fresh revenue/cost_of_revenue is not the kind of transient gap
        preserve_on_missing_fields exists to protect - the concept genuinely produces no usable
        annual value for this filer/year under the current, correct code, so any stored value
        must be stale. Same force-null-bypasses-COALESCE mechanism as
        _reject_implausible_eps/_reject_implausible_shares_outstanding above; post_run()'s
        UPDATE is a no-op for a row where gross_profit is already NULL, so this is safe to run
        unconditionally for every annual income-statement row with fresh revenue and
        cost_of_revenue, not just the 4 symbols found so far. Annual-only (self.period ==
        "annual") - quarterly's own real Q4 GrossProfit fact legitimately has this same ~90-day
        span, so quarterly extraction isn't affected by (or exposed to) this bug.
        """
        if self.period != "annual":
            return
        for row in transformed:
            if row.get("revenue") is None or row.get("cost_of_revenue") is None or row.get("gross_profit") is not None:
                continue
            self._record_explicit_null_rejection(row, "gross_profit", "gross_profit_stale_no_fresh_annual_concept")

    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
    # identity follow-up to the ABBV/GILD/AMGN/ABT stale-stub fix above): live-confirmed via
    # real SEC companyfacts JSON that Centene (CNC) and Elevance Health (ELV) - both managed-
    # care health insurers, SIC "Hospital & Medical Service Plans" - tag their OWN "GrossProfit"/
    # "CostOfGoodsAndServicesSold" XBRL concepts to a narrow, real sub-calculation (their non-
    # premium service-fee segments only, ~$2.7-21B) that EXCLUDES their dominant cost line -
    # medical claims/benefits expense, tagged separately as PolicyholderBenefitsAndClaims
    # IncurredHealthCare/BenefitsLossesAndExpenses (CNC FY2023 $118.9B, ELV H1'26-annualized
    # ~$193B) - which this pipeline never maps to cost_of_revenue at all. Unlike HCTI's
    # gross_profit bug above (a filing-agent tagging ERROR, not a real number at all), CNC's/
    # ELV's $2.67B/$21.2B "GrossProfit"/"CostOfGoodsAndServicesSold" figures ARE real, filer-
    # reported facts - just not economically comparable to a retailer's gross margin, since they
    # cover only a small slice of the filer's true cost structure. Live-cross-checked their real
    # peers to confirm this is NOT a blanket "insurers are all wrong" issue: MOH/HUM (no
    # GrossProfit tag at all, correctly NULL already) and UNH/CI/CVS (real, meaningful
    # CostOfGoodsAndServicesSold figures for their own genuine PBM/retail-pharmacy product
    # segments, ~50-55% of revenue - a real, comparable cost ratio, not this bug) are unaffected
    # and must NOT be touched by this fix. A curated, individually-verified rejection (same
    # discipline as this file's other symbol-specific overrides) rather than a SIC-wide null,
    # which would incorrectly also blank UNH/CI/CVS's real PBM segment cost data.
    _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS = frozenset({"CNC", "ELV"})

    def _reject_partial_segment_gross_profit_for_managed_care_insurers(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null gross_profit/cost_of_revenue for the curated managed-care symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS:
                continue
            for field in ("gross_profit", "cost_of_revenue"):
                if row.get(field) is None:
                    continue
                row[field] = None
                self._record_explicit_null_rejection(row, field, "managed_care_partial_segment_cost_not_total")

    # ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI sweep,
    # gross_profit_identity live re-check after the CNC/ELV/TYGO fixes): live-confirmed via
    # real SEC companyfacts JSON that Altria (MO) is the MIRROR IMAGE of CNC/ELV's bug - here
    # `GrossProfit` is the real, complete, filer-tagged total (matches Revenue exactly minus
    # Altria's true cost of sales), but `CostOfGoodsAndServicesSold` is the PARTIAL concept:
    # every single fiscal year 2016-2025 (`data.sec.gov/api/xbrl/companyconcept/
    # CIK0000764180/us-gaap/CostOfGoodsAndServicesSold.json` vs `.../GrossProfit.json` vs
    # `.../RevenueFromContractWithCustomerExcludingAssessedTax.json`), Revenue - COGS !=
    # GrossProfit by a large, growing margin (FY2025: $23.279B - $5.597B = $17.682B tagged-
    # COGS-implied gross profit vs. the real, filer-tagged GrossProfit of only $14.542B - a
    # $3.14B gap, this pipeline's own `gross_profit_identity` tie-out check's residual).
    # Peer-checked to confirm this is Altria-specific, NOT a tobacco/excise-tax-industry-wide
    # pattern: Philip Morris International (PM, CIK 0001413329) reconciles EXACTLY for the
    # same FY2025 period ($40.648B revenue - $13.366B COGS = $27.282B GrossProfit, to the
    # dollar) - a real, comparable filer in the same industry with the identical excise-tax-
    # exclusion revenue concept shows no such gap, ruling out an industry-wide accounting
    # convention as the explanation. Curated single-symbol rejection (same discipline as
    # _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS above) - only cost_of_revenue is
    # nulled here, NOT gross_profit, since GrossProfit is the reliable, complete figure in
    # this case (opposite of CNC/ELV, where GrossProfit itself was the partial concept).
    #
    # ADDED 2026-09-07 (same goal session, gross_profit_identity live triage continuation,
    # batch 21-45 by residual): ZIM Integrated Shipping (ZIM, CIK 0001654126, a container-
    # shipping line filing 20-F under IFRS) - live-confirmed via real SEC companyfacts JSON:
    # ifrs-full "RevenueFromContractsWithCustomers" ($6.9042B FY2025) - "CostOfSales"
    # ($4.4608B) implies a $2.4434B gross profit (35.4% margin), but the real, filer-tagged
    # "GrossProfit" is only $1.3209B (19.1% margin) - a $1.1225B gap, exactly this pipeline's
    # own gross_profit_identity residual. Unlike TTEK/TAP (a single missing additive concept
    # that reconciles the gap exactly - see _fill_cost_of_revenue_from_other_operating_cost()),
    # an exhaustive scan of every ifrs-full concept for this exact fiscal-year period found NO
    # single concept matching the $1.1225B gap (TransportationExpense $2.1021B and FuelExpense
    # $1.1467B are both real, large, separately-tagged shipping-specific cost lines, but neither
    # alone nor their sum closes the gap exactly) - ruling out the clean-sum pattern. The lower,
    # real GrossProfit figure is corroborated as the reliable one: GrossProfit ($1.3209B) -
    # ProfitLossFromOperatingActivities ($1.016B) = $304.9M, a plausible SG&A-scale residual,
    # while CostOfSales's implied 35.4% gross margin is implausibly high for bulk container
    # shipping's well-known thin-margin economics. No good SEC-registered direct peer exists
    # (most major container lines - Maersk, COSCO, CMA CGM, Hapag-Lloyd - aren't SEC-listed) so
    # this is verified via internal consistency (the operating-income cross-check above) rather
    # than a peer comparison, same as this constant's original MO entry when it predated the PM
    # peer-check precedent.
    _PARTIAL_COST_OF_REVENUE_SYMBOLS = frozenset({"MO", "ZIM"})

    def _reject_partial_cost_of_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null cost_of_revenue (keeping gross_profit) for the curated symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_COST_OF_REVENUE_SYMBOLS:
                continue
            if row.get("cost_of_revenue") is None:
                continue
            row["cost_of_revenue"] = None
            self._record_explicit_null_rejection(row, "cost_of_revenue", "cost_of_revenue_partial_concept_not_total")

    def _reject_scale_mismatched_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `revenue` when it's a clean power-of-10 multiple (100x/1000x/10000x, within
        1%) of (cost_of_revenue + gross_profit) - the same magic-ratio detection already
        proven safe in sec_statements_entry_resolution.py's frame_magnitude_scale_guard (the
        IPAR fix), applied to this pipeline's own concept-priority chain instead of SEC's
        frame-preference tiebreak.

        FOUND 2026-09-06 (goal: score/tie-out sanity audit, gross_profit_identity's current
        top-flagged-by-magnitude non-CNC/ELV offender). Live-confirmed via TYGO's (Tigo
        Energy) real SEC companyfacts JSON: the filer's OWN XBRL genuinely mistags
        RevenueFromContractWithCustomerExcludingAssessedTax at exactly 1000x the correct value
        for every single fiscal year on record (2022: $81.323B tagged vs. $81.323M real;
        2023/2024/2025 same shape) - NOT an extraction-side wrong-context bug like the tie-out
        checker's other gross_profit_identity leads (CNC/ELV, ABBV/GILD/AMGN/ABT): TYGO's own
        "Revenues" concept for the identical periods is correctly tagged every time, and
        _INCOME_FIELD_MAPPING's documented "ExcludingAssessedTax must win when both are
        present" priority (correct for the overwhelming majority of filers, where
        ExcludingAssessedTax is the more precise net-revenue figure) picks the corrupted one
        for this filer specifically. cost_of_revenue/gross_profit are unaffected (both come
        from separate, correctly-tagged concepts), so their sum is the independent, trustworthy
        anchor to validate revenue against - exactly the same role gross_profit_identity's
        `implied_gross_profit` plays in algo/monitoring/data_patrol/checks/tie_out.py, just run
        pre-storage instead of as a post-hoc read-only WARN. DB-wide live scan confirmed this
        exact 1000x pattern currently affects only TYGO (4 rows total, all its own fiscal
        years) - not a systemic bug, so this guard is expected to fire rarely; a legitimate
        filer's revenue vs. cost_of_revenue+gross_profit will essentially never land within 1%
        of an exact power of 10 by chance.
        """
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or cost_of_revenue is None or gross_profit is None:
                continue
            implied_revenue = float(cost_of_revenue) + float(gross_profit)
            if implied_revenue == 0 or revenue == 0:
                continue
            ratio = abs(float(revenue)) / abs(implied_revenue)
            if ratio < 1:
                ratio = 1 / ratio
            if any(abs(ratio - power) / power < 0.01 for power in (100, 1000, 10000)):
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"revenue={revenue:,.0f} is a {ratio:.0f}x-scaled outlier vs. "
                    f"cost_of_revenue+gross_profit={implied_revenue:,.0f} - likely a filer-side "
                    "XBRL tagging error on the higher-priority revenue concept, not a real "
                    "business figure. Rejecting rather than storing a confidently-wrong value."
                )
                row["revenue"] = None
                self._record_explicit_null_rejection(row, "revenue", "revenue_scale_mismatch_vs_cogs_plus_gp")

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
                result.append(row)

        return result

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Execute loader. Delegates to base class."""
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)


if __name__ == "__main__":
    sys.exit(main())
