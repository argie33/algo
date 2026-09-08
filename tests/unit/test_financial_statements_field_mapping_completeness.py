"""Regression test: every XBRL concept sec_statements.py fetches must have a target
column in load_financial_statements.py's field_mapping, or the real data it fetches
from SEC every run is silently dropped by transform() (unmapped keys are skipped).

FOUND 2026-07-28 (real, ~1-month-old active data-loss regression, live-verified): a
2026-06-21 commit ("Clean up loader infrastructure - remove dead code") removed 6
balance-sheet concepts (cash/AR/inventory/PP&E/goodwill/long-term-debt) from
_BALANCE_FIELD_MAPPING and schema_cols, mistaking real, still-actively-fetched XBRL
concepts for dead code - annual_balance_sheet kept writing fresh rows every day while
those 6 columns silently stopped updating. Separately, EarningsPerShareDiluted had been
fetched but never mapped to diluted_eps at all, since the module was first written.
Both fixed same session; this test exists so a future "cleanup" pass can't silently
reintroduce the same class of bug without a test failing.
"""

from loaders.load_financial_statements import (
    _ANNUAL_BALANCE_EXTRA,
    _BALANCE_FIELD_MAPPING,
    _CASHFLOW_FIELD_MAPPING,
    _INCOME_FIELD_MAPPING,
)
from utils.external.sec_statements import (
    _BALANCE_IFRS_ALIASES,
    _CASHFLOW_IFRS_ALIASES,
    _INCOME_IFRS_ALIASES,
    _to_snake,
)

# Mirrors the concepts lists inside sec_statements.py's get_income_statement/
# get_balance_sheet/get_cash_flow - kept here rather than imported since those concepts
# lists are local variables, not module-level constants. If a concept is added there,
# add it here too (that's the point: this test only protects concepts it knows about).
_INCOME_CONCEPTS = [
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfRevenue",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "InterestExpense",
    "Depreciation",
    "DepreciationAndAmortization",
    "AmortizationOfIntangibles",
]

_BALANCE_CONCEPTS = [
    "Assets",
    "AssetsCurrent",
    "Liabilities",
    "LiabilitiesCurrent",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "ReceivablesNetCurrent",
    "AccountsReceivableNetCurrent",
    "InventoryNet",
    "PublicUtilitiesPropertyPlantAndEquipmentNet",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
    "PropertyPlantAndEquipmentNet",
    "Goodwill",
    "NotesPayableRelatedPartiesNoncurrent",
    "LongTermNotesPayable",
    "ConvertibleNotesPayable",
    "LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "CommercialPaper",
    "ShortTermBorrowings",
    "OperatingLeaseLiability",
    "FinanceLeaseLiability",
    "RetainedEarningsAccumulatedDeficit",
]

_CASHFLOW_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfOrdinaryDividends",
    "AllocatedShareBasedCompensationExpense",
    "ShareBasedCompensation",
    "PaymentsForRepurchaseOfEquity",
    "PaymentsForRepurchaseOfCommonStock",
    # ADDED 2026-09-07: net_change_cash was fetched by none of these and mapped nowhere -
    # see sec_cash_flow.py's get_cash_flow() comment on these 4 concepts.
    "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
    "CashAndCashEquivalentsPeriodIncreaseDecrease",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
]


# Fallback-only alias target keys that a dedicated post-processing "fill" function (in
# sec_statements.py, e.g. _fill_earnings_per_share_from_continuing_discontinued_split)
# pops and sums into a real, already-mapped column before the row is ever returned - never
# silently dropped, just never meant to reach field_mapping directly (same reasoning as
# LongTermDebtCurrent/LongTermDebtNoncurrent, which this test doesn't track at all since
# they're plain concepts, not IFRS aliases, and were simply left out of _BALANCE_CONCEPTS
# above). Add here (not to field_mapping) whenever a new alias exists solely to feed a
# fill-function sum, or this test will treat the deliberately-transient key as a real leak.
_FALLBACK_ONLY_ALIAS_KEYS = {
    "earnings_per_share_basic_continuing",
    "earnings_per_share_basic_discontinued",
    "earnings_per_share_diluted_continuing",
    "earnings_per_share_diluted_discontinued",
}


def _unmapped(concepts: list[str], ifrs_aliases: list[tuple[str, str]], field_mapping: dict[str, str]) -> list[str]:
    target_keys = {_to_snake(c) for c in concepts} | {alias_key for _, alias_key in ifrs_aliases}
    target_keys -= _FALLBACK_ONLY_ALIAS_KEYS
    return sorted(target_keys - set(field_mapping.keys()))


class TestFieldMappingCoversFetchedConcepts:
    def test_income_statement_concepts_all_mapped(self) -> None:
        unmapped = _unmapped(_INCOME_CONCEPTS, _INCOME_IFRS_ALIASES, _INCOME_FIELD_MAPPING)
        assert not unmapped, f"Fetched but unmapped income concepts (data silently dropped): {unmapped}"

    def test_balance_sheet_concepts_all_mapped(self) -> None:
        # RetainedEarningsAccumulatedDeficit is annual-only (_ANNUAL_BALANCE_EXTRA, merged into
        # the annual balance-sheet config's field_mapping - see load_financial_statements.py's
        # get_balance_sheet_config()) - annual_balance_sheet is the only table with a
        # retained_earnings column (migration 1234); quarterly/TTM balance sheet configs must
        # NOT gain this mapping or every fetch raises sec_base.py's "not in target schema"
        # RuntimeError (live-caught 2026-08-26 - see _ANNUAL_BALANCE_EXTRA's own comment).
        combined_mapping = {**_BALANCE_FIELD_MAPPING, **_ANNUAL_BALANCE_EXTRA}
        unmapped = _unmapped(_BALANCE_CONCEPTS, _BALANCE_IFRS_ALIASES, combined_mapping)
        assert not unmapped, f"Fetched but unmapped balance sheet concepts (data silently dropped): {unmapped}"

    def test_cash_flow_concepts_all_mapped(self) -> None:
        unmapped = _unmapped(_CASHFLOW_CONCEPTS, _CASHFLOW_IFRS_ALIASES, _CASHFLOW_FIELD_MAPPING)
        assert not unmapped, f"Fetched but unmapped cash flow concepts (data silently dropped): {unmapped}"
