"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): DRH (DiamondRock Hospitality, a REIT) tags a
real capex figure under "PaymentsForCapitalImprovements" ($81,563,000 FY2025, live-confirmed
via SEC companyfacts JSON, exactly matching the yfinance-flagged value) AND a real "$0 spent
on land this year" fact under "PaymentsToAcquireLand" at the same time.

Before this fix, "payments_to_acquire_land" was a plain (non-fallback) concept - since it's
processed after PaymentsForCapitalImprovements/RealEstateImprovements in
sec_cash_flow.py's concept-list order, its real $0 land-purchases fact unconditionally
overwrote the correct, larger total capex figure via ordinary last-processed-wins. Same bug
class as the senior_notes/PNBK fix in financial_statements_balance_config.py: a concept
representing one narrow acquisition category, not the filer's total capex, must never be
allowed to clobber a more complete concept already resolved.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestDrhPaymentsToAcquireLandFallbackOnly:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "capex": "capex",
            "payments_for_capital_improvements": "capex",
            "payments_to_acquire_land": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"payments_to_acquire_land"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_payments_to_acquire_land_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_land"] == "capex"
        assert "payments_to_acquire_land" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_zero_land_purchases_never_overwrites_the_real_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DRH",
            "fiscal_year": 2025,
            "payments_for_capital_improvements": 81_563_000.0,
            "payments_to_acquire_land": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 81_563_000.0

    def test_payments_to_acquire_land_still_recovered_when_no_other_concept_present(self) -> None:
        """MRP case (2026-09-06 original fix) must keep working: fallback-only still fills
        capex when nothing else already populated it.
        """
        loader = self._make_loader()
        row = {
            "symbol": "MRP",
            "fiscal_year": 2025,
            "payments_to_acquire_land": 858_938_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 858_938_000.0


class TestNscSnpsOtherProductiveAssetsFallbackOnly:
    """Regression test for the 2026-09-16 fix: NSC and SNPS both tag a real, complete
    "PaymentsToAcquirePropertyPlantAndEquipment" AND a real "$0 spent on other productive
    assets this year" fact under "PaymentsToAcquireOtherProductiveAssets" at the same time -
    live-confirmed via SEC companyfacts JSON. Same overwrite bug as payments_to_acquire_land.
    """

    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "capex": "capex",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "payments_to_acquire_other_productive_assets": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"payments_to_acquire_other_productive_assets"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_other_productive_assets"] == "capex"
        assert "payments_to_acquire_other_productive_assets" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_zero_other_productive_assets_never_overwrites_the_real_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "NSC",
            "fiscal_year": 2025,
            "payments_to_acquire_property_plant_and_equipment": 2_204_000_000.0,
            "payments_to_acquire_other_productive_assets": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 2_204_000_000.0


class TestViciRealEstateFallbackOnly:
    """Regression test for the 2026-09-16 fix: VICI tags a real
    "PaymentsToAcquireOtherPropertyPlantAndEquipment" AND a real "$0 real estate acquired
    this year" fact under "PaymentsToAcquireRealEstate" at the same time - live-confirmed
    via SEC companyfacts JSON. Same overwrite bug as payments_to_acquire_land.
    """

    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "capex": "capex",
            "payments_to_acquire_other_property_plant_and_equipment": "capex",
            "payments_to_acquire_real_estate": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"payments_to_acquire_real_estate"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_real_estate"] == "capex"
        assert "payments_to_acquire_real_estate" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_zero_real_estate_never_overwrites_the_real_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "VICI",
            "fiscal_year": 2025,
            "payments_to_acquire_other_property_plant_and_equipment": 1_335_000.0,
            "payments_to_acquire_real_estate": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 1_335_000.0

    def test_real_estate_still_recovered_when_no_other_concept_present(self) -> None:
        """AHR/ABR case (2026-08-24 original fix) must keep working: fallback-only still
        fills capex when nothing else already populated it.
        """
        loader = self._make_loader()
        row = {
            "symbol": "AHR",
            "fiscal_year": 2025,
            "payments_to_acquire_real_estate": 60_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 60_400_000.0
