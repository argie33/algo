"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero"
sweep, capex_never_tagged_in_recent_filings scored-symbol follow-up): Tanger Inc (SKT, CIK
0000899715, real outlet-mall REIT) reports NEITHER "PaymentsForCapitalImprovements" nor any
other RealEstate/PP&E-family concept - its real property-improvement capex is tagged under
the standard "RealEstateImprovements" concept instead ($188.863M FY2023, $77.194M FY2024,
$93.868M FY2025, live-confirmed via real companyfacts JSON).
"""

from loaders.helpers.financial_statements_cashflow_config import _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
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


class TestRealEstateImprovementsFallbackOnly:
    # ADDED 2026-09-18 (goal session, xbrl_yfinance_line_item_report capex remediation):
    # "real_estate_improvements" being unconditional (not in the real fallback-only set)
    # let it overwrite AMT's real, much larger PaymentsToAcquirePropertyPlantAndEquipment
    # total every year (live-confirmed via SEC companyfacts: AMT FY2022
    # RealEstateImprovements=$155.4M vs the real $1,873.6M yfinance-matching total) - same
    # bug shape as the long_term_debt narrow-vs-combined-concept fix. This exercises the
    # REAL _SBC_BUYBACK_FALLBACK_ONLY_FIELDS set (unlike the tests above, which construct
    # their own empty frozenset), so it would have caught the regression.
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "real_estate_improvements": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_estate_improvements_is_fallback_only(self) -> None:
        assert "real_estate_improvements" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_amt_style_ptappe_wins_over_narrower_real_estate_improvements(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AMT",
            "fiscal_year": 2022,
            "payments_to_acquire_property_plant_and_equipment": 1_873_600_000.0,
            "real_estate_improvements": 155_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 1_873_600_000.0

    def test_skt_style_capex_still_recovered_with_real_fallback_set(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SKT", "fiscal_year": 2025, "real_estate_improvements": 93_868_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 93_868_000.0
