"""Regression test for the 2026-09-02 fix (goal: "get all the data we need" full-coverage
audit): live SEC ground-truth check via VSAT (Viasat)'s real companyfacts JSON confirmed some
filers genuinely stop tagging a discrete PP&E-capex concept in recent 10-Ks -
PaymentsToAcquirePropertyPlantAndEquipment's last fact is FY2023 (filed 2023-05-22), nothing
for FY2024/2025/2026, despite gross PP&E visibly growing ~$800M+/year (real capex is
happening, just no longer disclosed as a discrete cash-flow line). Cross-checked KO and PG the
same day - both still tag capex normally through FY2025/2026 - confirming this is a scattered,
filer-specific disclosure change (~15 capex concept aliases already exist in
utils/external/sec_statements.py's get_cash_flow(), so this isn't a concept-map gap another
alias could close).

Fixed by falling back to the standard indirect estimate analysts use when a filer doesn't
break out capex: Capex ~= (Ending Net PP&E - Beginning Net PP&E) + Depreciation Expense,
annual only, guarded against a disposal/impairment-dominated year (derived value <= 0,
rejected) and a business-combination-inflated year (derived value > 10x depreciation,
rejected) so a bad estimate falls through to the original missing-capex behavior rather than
fabricating a number.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING


class _BaseCashflowLoader:
    @staticmethod
    def _make_loader(ppe_net_by_symbol_year=None, depreciation_by_symbol_year=None):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "operating_cash_flow", "capex", "free_cash_flow", "data_unavailable", "reason"}
        )
        loader._field_mapping = _CASHFLOW_FIELD_MAPPING
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._depository_institution_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        # Explicit cache seeding (not a live DB call) - same test seam already used for
        # _reit_symbols/_depository_institution_symbols above.
        loader._ppe_net_by_symbol_year = ppe_net_by_symbol_year or {}
        loader._depreciation_expense_by_symbol_year = depreciation_by_symbol_year or {}
        return loader


class TestCapexDerivedFromPpeNetDelta(_BaseCashflowLoader):
    def test_vsat_style_gap_recovers_plausible_capex_estimate(self):
        # Real VSAT FY2025 shape: ppe_net shrank slightly (net of depreciation) while
        # depreciation was substantial - derives to ~$885M, in line with VSAT's own real
        # historical reported capex ($827M-$1.077B FY2021-2023) before it stopped tagging.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"VSAT": {2025: 7_405_664_000.0, 2024: 7_557_206_000.0}},
            depreciation_by_symbol_year={"VSAT": {2025: 1_036_467_000.0}},
        )
        row = {
            "symbol": "VSAT",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 908_187_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 884_925_000.0
        assert transformed[0]["data_source"] == "derived_ppe_delta"
        assert transformed[0]["free_cash_flow"] == 908_187_000.0 - 884_925_000.0

    def test_real_reported_capex_never_overwritten_by_derived_estimate(self):
        # Control: a filer that DOES still tag real capex must keep it - the derivation only
        # ever fires when capex is None.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"KO": {2025: 20_000_000_000.0, 2024: 19_000_000_000.0}},
            depreciation_by_symbol_year={"KO": {2025: 1_500_000_000.0}},
        )
        row = {
            "symbol": "KO",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 12_000_000_000.0,
            "payments_to_acquire_property_plant_and_equipment": 2_112_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 2_112_000_000.0
        assert transformed[0].get("data_source") != "derived_ppe_delta"

    def test_disposal_dominated_year_not_derived(self):
        # Net PP&E shrank by MORE than depreciation alone explains (a real, disposal-heavy
        # year) - the resulting estimate would be negative/zero, not a trustworthy capex
        # read, so it must be rejected rather than persisted.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"DIVEST": {2025: 5_000_000_000.0, 2024: 7_000_000_000.0}},
            depreciation_by_symbol_year={"DIVEST": {2025: 500_000_000.0}},
        )
        row = {
            "symbol": "DIVEST",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 900_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("capex") is None
        assert transformed[0].get("data_source") != "derived_ppe_delta"

    def test_business_combination_spike_not_derived(self):
        # PP&E jumped far more than 10x depreciation in one year (an acquisition adding
        # PP&E, not organic capex) - must be rejected as implausible rather than fabricated.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"ACQUIRER": {2025: 50_000_000_000.0, 2024: 10_000_000_000.0}},
            depreciation_by_symbol_year={"ACQUIRER": {2025: 500_000_000.0}},
        )
        row = {
            "symbol": "ACQUIRER",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 900_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("capex") is None
        assert transformed[0].get("data_source") != "derived_ppe_delta"

    def test_missing_prior_year_ppe_not_derived(self):
        # No prior-year ppe_net to diff against - must not fabricate a delta from a single
        # data point.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"NEWCO": {2025: 5_000_000_000.0}},
            depreciation_by_symbol_year={"NEWCO": {2025: 500_000_000.0}},
        )
        row = {
            "symbol": "NEWCO",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 900_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("capex") is None

    def test_quarterly_table_never_derives(self):
        # Scoped to annual only - quarterly PP&E deltas are far noisier and depreciation
        # isn't cleanly quarterly-only for every filer.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"VSAT": {2025: 7_405_664_000.0, 2024: 7_557_206_000.0}},
            depreciation_by_symbol_year={"VSAT": {2025: 1_036_467_000.0}},
        )
        loader.table_name = "quarterly_cash_flow"
        row = {
            "symbol": "VSAT",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 200_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("capex") is None
        assert transformed[0].get("data_source") != "derived_ppe_delta"

    def test_bank_zero_capex_still_takes_priority_over_derivation(self):
        # A confirmed depository institution's genuinely-absent capex is coerced to 0 (the
        # existing, older fix) - the derivation must not run instead, since it would fill a
        # value where "0, not applicable" is the correct, already-established answer.
        loader = self._make_loader(
            ppe_net_by_symbol_year={"ABANK": {2025: 5_000_000_000.0, 2024: 4_000_000_000.0}},
            depreciation_by_symbol_year={"ABANK": {2025: 500_000_000.0}},
        )
        loader._depository_institution_symbols = frozenset({"ABANK"})
        row = {
            "symbol": "ABANK",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 900_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("capex") is None
        assert transformed[0]["free_cash_flow"] == 900_000_000.0
