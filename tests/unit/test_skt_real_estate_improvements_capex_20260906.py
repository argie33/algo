"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero"
sweep, capex_never_tagged_in_recent_filings scored-symbol follow-up): Tanger Inc (SKT, CIK
0000899715, real outlet-mall REIT) reports NEITHER "PaymentsForCapitalImprovements" nor any
other RealEstate/PP&E-family concept - its real property-improvement capex is tagged under
the standard "RealEstateImprovements" concept instead ($188.863M FY2023, $77.194M FY2024,
$93.868M FY2025, live-confirmed via real companyfacts JSON).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING


class TestSktRealEstateImprovementsCapex:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_for_capital_improvements": "capex",
            "real_estate_improvements": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_field_mapping_wires_the_concept_to_capex(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["real_estate_improvements"] == "capex"

    def test_skt_style_capex_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SKT", "fiscal_year": 2025, "real_estate_improvements": 93_868_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 93_868_000.0

    def test_never_overwrites_a_real_capex_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAT",
            "fiscal_year": 2024,
            "payments_for_capital_improvements": 70_200_000.0,
            "real_estate_improvements": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 1.0
