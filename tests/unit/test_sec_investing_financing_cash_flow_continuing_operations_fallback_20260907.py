"""Regression test for the 2026-09-07 fix (goal session: "make sure the list/checks are
right, then fix issues" audit): investing_cash_flow/financing_cash_flow only mapped from
plain "NetCashProvidedByUsedInInvestingActivities"/"...FinancingActivities" - filers that
report discontinued operations tag these under the ...ContinuingOperations variants instead,
sometimes for years the plain concept has no entry at all.

Live-confirmed via real SEC EDGAR companyfacts cache: Air Products and Chemicals (APD, a
major real 10-K filer) has ZERO entries under either plain concept for EVERY fiscal year
2016-2025, but real figures under the ContinuingOperations concepts for that entire span -
investing_cash_flow/financing_cash_flow were silently NULL for APD's whole recent history.
More broadly, of the 1,887/1,925 filers that tag the financing/investing ContinuingOperations
concepts at all, 1,391/1,373 have at least one individual fiscal year present ONLY under the
ContinuingOperations tag - a widespread partial-year gap, not a single-filer quirk.

Fixed the same way as operating_cash_flow's identical gap (see
test_sec_operating_cash_flow_continuing_operations_fallback.py): added the ContinuingOperations
concepts as fallback-only mappings so a filer that DOES report the plain, fuller total (live-
confirmed via APD reporting both concepts for operating_cash_flow) always keeps that value;
these concepts only fill genuinely empty years/filers.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestInvestingFinancingCashFlowContinuingOperationsFallbackConceptMapping:
    def test_investing_continuing_operations_concept_maps_to_investing_cash_flow(self) -> None:
        assert (
            _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_investing_activities_continuing_operations"]
            == "investing_cash_flow"
        )
        assert (
            "net_cash_provided_by_used_in_investing_activities_continuing_operations"
            in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        )

    def test_financing_continuing_operations_concept_maps_to_financing_cash_flow(self) -> None:
        assert (
            _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_financing_activities_continuing_operations"]
            == "financing_cash_flow"
        )
        assert (
            "net_cash_provided_by_used_in_financing_activities_continuing_operations"
            in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        )

    def test_standard_concepts_still_map_directly_not_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_investing_activities"] == "investing_cash_flow"
        assert _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_financing_activities"] == "financing_cash_flow"
        assert "net_cash_provided_by_used_in_investing_activities" not in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        assert "net_cash_provided_by_used_in_financing_activities" not in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestInvestingFinancingCashFlowFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "investing_cash_flow", "financing_cash_flow", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
            "net_cash_provided_by_used_in_investing_activities_continuing_operations": "investing_cash_flow",
            "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
            "net_cash_provided_by_used_in_financing_activities_continuing_operations": "financing_cash_flow",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_total_not_overwritten_by_continuing_operations_only_figure(self) -> None:
        # A filer reporting both concepts for the same fiscal year - the plain tag is the
        # fuller total (continuing + discontinued) and must keep winning.
        loader = self._make_loader()
        row = {
            "symbol": "ANGI",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_investing_activities": -500_000_000.0,
            "net_cash_provided_by_used_in_investing_activities_continuing_operations": -480_000_000.0,
            "net_cash_provided_by_used_in_financing_activities": 200_000_000.0,
            "net_cash_provided_by_used_in_financing_activities_continuing_operations": 190_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["investing_cash_flow"] == -500_000_000.0
        assert transformed[0]["financing_cash_flow"] == 200_000_000.0

    def test_fallback_concept_populates_values_when_standard_concept_absent(self) -> None:
        # APD-style filer: never tags either plain concept, only the ContinuingOperations
        # variants - must still recover real values instead of leaving them NULL.
        loader = self._make_loader()
        row = {
            "symbol": "APD",
            "fiscal_year": 2017,
            "net_cash_provided_by_used_in_investing_activities_continuing_operations": -1_417_700_000.0,
            "net_cash_provided_by_used_in_financing_activities_continuing_operations": -2_040_900_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["investing_cash_flow"] == -1_417_700_000.0
        assert transformed[0]["financing_cash_flow"] == -2_040_900_000.0
