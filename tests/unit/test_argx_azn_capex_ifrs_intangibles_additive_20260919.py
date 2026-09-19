"""Regression test for the ARGX/AZN IFRS capex gap found live 2026-09-19 (/goal
data-confidence audit).

"PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities" is a real, genuinely additive
IFRS capex component (licensing/IP/capitalized-software spend) alongside PP&E purchases, not
an alternate figure - live-confirmed via real SEC companyfacts JSON for 2 unrelated IFRS 20-F
filers:

- ARGX (argenx SE) FY2023: PP&E $812,000 + intangibles $43,000,000 = $43,812,000, exact
  yfinance match (our stored value before this fix was PP&E alone, $812,000).
- AZN (AstraZeneca PLC) FY2023: PP&E $1,361,000,000 + intangibles $2,417,000,000 =
  $3,778,000,000, exact yfinance match.
"""

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.helpers.sec_zero_component_guards import ADDITIVE_CONCEPT_PAIRS


class TestIfrsIntangiblesCapexAdditive:
    def test_concept_mapped_fallback_only_and_additive(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["purchase_of_intangible_assets_classified_as_investing_activities"] == "capex"
        assert "purchase_of_intangible_assets_classified_as_investing_activities" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        assert ("capex", "purchase_of_intangible_assets_classified_as_investing_activities") in ADDITIVE_CONCEPT_PAIRS

    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "purchase_of_intangible_assets_classified_as_investing_activities": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_ppe_and_intangibles_sum_for_argx(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ARGX",
            "fiscal_year": 2023,
            "payments_to_acquire_property_plant_and_equipment": 812_000.0,
            "purchase_of_intangible_assets_classified_as_investing_activities": 43_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 43_812_000.0

    def test_intangibles_still_fills_when_ppe_absent(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEFILER",
            "fiscal_year": 2020,
            "purchase_of_intangible_assets_classified_as_investing_activities": 5_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 5_000_000.0
