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

from utils.external.sec_statements import (
    _BALANCE_IFRS_ALIASES,
    _CASHFLOW_IFRS_ALIASES,
    _INCOME_IFRS_ALIASES,
    _to_snake,
)
from loaders.load_financial_statements import (
    _BALANCE_FIELD_MAPPING,
    _CASHFLOW_FIELD_MAPPING,
    _INCOME_FIELD_MAPPING,
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
    "AccountsReceivableNetCurrent",
    "InventoryNet",
    "PropertyPlantAndEquipmentNet",
    "Goodwill",
    "LongTermDebt",
]

_CASHFLOW_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsOfDividends",
]


def _unmapped(concepts, ifrs_aliases, field_mapping):
    target_keys = {_to_snake(c) for c in concepts} | {alias_key for _, alias_key in ifrs_aliases}
    return sorted(target_keys - set(field_mapping.keys()))


class TestFieldMappingCoversFetchedConcepts:
    def test_income_statement_concepts_all_mapped(self):
        unmapped = _unmapped(_INCOME_CONCEPTS, _INCOME_IFRS_ALIASES, _INCOME_FIELD_MAPPING)
        assert not unmapped, f"Fetched but unmapped income concepts (data silently dropped): {unmapped}"

    def test_balance_sheet_concepts_all_mapped(self):
        unmapped = _unmapped(_BALANCE_CONCEPTS, _BALANCE_IFRS_ALIASES, _BALANCE_FIELD_MAPPING)
        assert not unmapped, f"Fetched but unmapped balance sheet concepts (data silently dropped): {unmapped}"

    def test_cash_flow_concepts_all_mapped(self):
        unmapped = _unmapped(_CASHFLOW_CONCEPTS, _CASHFLOW_IFRS_ALIASES, _CASHFLOW_FIELD_MAPPING)
        assert not unmapped, f"Fetched but unmapped cash flow concepts (data silently dropped): {unmapped}"
