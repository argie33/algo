"""Regression test for the 2026-08-19 fix (goal: "no SEC data"/loader audit): the only
concept mapped to annual_cash_flow/quarterly_cash_flow.operating_cash_flow was plain
"NetCashProvidedByUsedInOperatingActivities" - filers that report discontinued operations
(a common occurrence, not rare - divestitures, spinoffs) often tag operating cash flow
under "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations" instead, sometimes
exclusively.

Live-confirmed via real SEC EDGAR companyfacts for ASH (Ashland, a normal specialty-
chemicals 10-K filer): ZERO entries under the plain concept for any fiscal year, but real,
plausible-scale figures ($134M-$703M) under the ContinuingOperations concept for every
FY2014-2025. operating_cash_flow (and everything derived from it: free_cash_flow,
fcf_to_net_income, fcf_yield, intrinsic_value, margin_of_safety) was NULL for this filer's
entire history - worse, the whole annual_cash_flow row was marked data_unavailable=True
("incomplete_sec_filing_cashflow") since load_financial_statements.py's transform()
requires operating_cash_flow specifically, discarding real investing/financing/capex data
that was actually present alongside it. This was the largest single "missing_sec_data"
contributor across quality_metrics/value_metrics's cash-flow-derived fields universe-wide
(annual_cash_flow had the highest NULL rate of any fundamentals table, ~12.8% of rows).

Fixed by adding the ContinuingOperations concept as a fallback-only mapping (same
"don't clobber a real value" mechanism as _REVENUE_FALLBACK_ONLY_FIELDS/
_SBC_BUYBACK_FALLBACK_ONLY_FIELDS) so a filer that DOES report the plain, fuller total
(continuing + discontinued operations - live-confirmed via APD/Air Products, which reports
both concepts) always keeps that value; this concept only fills genuinely empty years.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestOperatingCashFlowContinuingOperationsFallbackConceptMapping:
    def test_continuing_operations_concept_maps_to_operating_cash_flow(self) -> None:
        assert (
            _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_operating_activities_continuing_operations"]
            == "operating_cash_flow"
        )
        assert (
            "net_cash_provided_by_used_in_operating_activities_continuing_operations"
            in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        )

    def test_standard_operating_cash_flow_concept_still_maps_directly(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_operating_activities"] == "operating_cash_flow"
        assert "net_cash_provided_by_used_in_operating_activities" not in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestOperatingCashFlowFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "operating_cash_flow", "data_unavailable", "reason"})
        loader._field_mapping = {
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            "net_cash_provided_by_used_in_operating_activities_continuing_operations": "operating_cash_flow",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_total_ocf_not_overwritten_by_continuing_operations_only_figure(self) -> None:
        # APD-style filer: reports both concepts for the same fiscal year - the plain tag
        # is the fuller total (continuing + discontinued) and must keep winning.
        loader = self._make_loader()
        row = {
            "symbol": "APD",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 3_256_800_000.0,
            "net_cash_provided_by_used_in_operating_activities_continuing_operations": 3_100_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["operating_cash_flow"] == 3_256_800_000.0

    def test_fallback_concept_populates_ocf_when_standard_concept_absent(self) -> None:
        # ASH-style filer: never tags plain "NetCashProvidedByUsedInOperatingActivities"
        # at all, only the ContinuingOperations variant - must still recover a real value
        # instead of leaving the whole row marked incomplete_sec_filing_cashflow.
        loader = self._make_loader()
        row = {
            "symbol": "ASH",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities_continuing_operations": 134_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["operating_cash_flow"] == 134_000_000.0
