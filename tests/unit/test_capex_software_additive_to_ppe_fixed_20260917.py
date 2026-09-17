"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up, top-cluster sweep): ACIW (ACI Worldwide, CIK 0000935036) tags BOTH a real
"PaymentsToAcquirePropertyPlantAndEquipment" (physical capex) AND a real
"PaymentsToAcquireSoftware" (capitalized software development costs) fact every fiscal
year - two genuinely distinct, non-overlapping investing-activity cash-flow line items for
a software company, not alternates.

Live-confirmed via real SEC companyfacts JSON 2026-09-17, every fiscal year on file in
xbrl_yfinance_line_item_report, EXACT match to yfinance's flagged capex value only when
BOTH concepts are summed:
    FY2022: $13,103,000 + $26,790,000 = $39,893,000 (yfinance-flagged, exact)
    FY2023: $8,924,000 + $28,853,000 = $37,777,000 (yfinance-flagged, exact)
    FY2024: $15,402,000 + $29,649,000 = $45,051,000 (yfinance-flagged, exact)
    FY2025: $12,907,000 + $20,445,000 = $33,352,000 (yfinance-flagged, exact)

"payments_to_acquire_software" is fallback-only (added 2026-09-10 for TALK, which reports
ONLY software capex with no PP&E concept at all - a genuine either/or case for that
filer), and PaymentsToAcquirePropertyPlantAndEquipment is the plain, always-fetched-first
standard concept, so the ordinary "db_field in row" fallback guard permanently blocked the
software figure once PP&E had already written. Same shape as
test_dividends_paid_and_cost_of_revenue_full_scan_20260916.py's cost_of_revenue/
franchisor_costs pair - see ADDITIVE_CONCEPT_PAIRS' own docstring in
sec_zero_component_guards.py for the live evidence.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING


class TestCapexSoftwareAdditiveToPpeFixed:
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
        loader._fallback_only_fields = frozenset({"payments_to_acquire_software"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts_to_capex(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_property_plant_and_equipment"] == "capex"
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_software"] == "capex"

    def test_aciw_fy2022_ppe_and_software_capex_sum(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ACIW",
            "fiscal_year": 2022,
            "payments_to_acquire_property_plant_and_equipment": 13_103_000.0,
            "payments_to_acquire_software": 26_790_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 39_893_000.0

    def test_aciw_fy2025_ppe_and_software_capex_sum(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ACIW",
            "fiscal_year": 2025,
            "payments_to_acquire_property_plant_and_equipment": 12_907_000.0,
            "payments_to_acquire_software": 20_445_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 33_352_000.0

    def test_talk_style_software_only_filer_still_a_plain_single_write(self) -> None:
        """TALK-style case: no PP&E concept at all, software capex fills the field alone -
        must be unaffected by this additive guard (no existing value to sum against)."""
        loader = self._make_loader()
        row = {
            "symbol": "TALK",
            "fiscal_year": 2025,
            "payments_to_acquire_software": 10_641_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 10_641_000.0
