"""Regression test for the 2026-09-10 fix (goal session: SEC/XBRL missing-data count under
500, missing_cash_flow_data investigation): KN (Knowles Corporation) tags its real, full-year
operating cash flow under "NetCashProvidedByUsedInContinuingOperations" - a DIFFERENT,
shorter concept name than the already-fetched "NetCashProvidedByUsedInOperatingActivities
ContinuingOperations" sibling - so it was never captured.

Live-confirmed via real SEC companyfacts JSON (CIK 0001587523): real, continuous,
plausible-scale annual figures ($78.4M-$182.1M) under this concept for every FY2012-2025
10-K, while both "NetCashProvidedByUsedInOperatingActivities" and its "...ContinuingOperations"
sibling only ever carry quarterly/YTD partial-period facts for KN, never a full annual
duration. operating_cash_flow (and everything derived: free_cash_flow, fcf_to_net_income,
fcf_yield, dcf_fcf) was NULL for KN's entire 14-year history, and the whole annual_cash_flow
row was marked data_unavailable=True ("incomplete_sec_filing_cashflow") despite capex being
real and present every year.
"""

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestKnNetCashContinuingOperationsConceptMapping:
    def test_concept_maps_to_operating_cash_flow(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["net_cash_provided_by_used_in_continuing_operations"] == "operating_cash_flow"
        assert "net_cash_provided_by_used_in_continuing_operations" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestKnFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "operating_cash_flow", "data_unavailable", "reason"})
        loader._field_mapping = {
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            "net_cash_provided_by_used_in_continuing_operations": "operating_cash_flow",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_kn_style_ocf_recovered_when_only_this_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "KN",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_continuing_operations": 114_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["operating_cash_flow"] == 114_000_000.0

    def test_never_overwrites_a_real_plain_ocf_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "net_cash_provided_by_used_in_operating_activities": 118_254_000_000.0,
            "net_cash_provided_by_used_in_continuing_operations": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["operating_cash_flow"] == 118_254_000_000.0
