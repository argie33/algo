"""Regression test for the 2026-09-10 fix (goal session: SEC/XBRL missing-data count under
500, dcf_fcf_unavailable_reason='missing_cash_flow_data' investigation): TALK (Talkspace,
Inc.) stopped tagging any PP&E-family capex concept after its FY2023 10-K - its real
FY2024/FY2025 capex is tagged under "PaymentsToAcquireSoftware" instead, a standard
us-gaap concept for capitalized software development costs never fetched before this fix.

Live-confirmed via real SEC companyfacts JSON (CIK 0001803901): $5,443,000 FY2024 /
$10,641,000 FY2025, both real 10-K annual-duration facts - plausible capex for a
light-physical-footprint SaaS/telehealth business. dcf_fcf/free_cash_flow/fcf_margin were
stuck at "missing_cash_flow_data" for FY2024-2025 despite real, current operating_cash_flow
being tagged every year.
"""

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestPaymentsToAcquireSoftwareConceptMapping:
    def test_concept_maps_to_capex(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_software"] == "capex"
        assert "payments_to_acquire_software" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestTalkFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "payments_to_acquire_software": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_talk_style_capex_recovered_when_only_software_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TALK",
            "fiscal_year": 2025,
            "payments_to_acquire_software": 10_641_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 10_641_000.0

    def test_never_overwrites_a_real_ppe_capex_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAON",
            "fiscal_year": 2025,
            "payments_to_acquire_property_plant_and_equipment": 195_700_000.0,
            "payments_to_acquire_software": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 195_700_000.0
