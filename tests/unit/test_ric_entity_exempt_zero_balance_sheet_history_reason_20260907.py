"""Regression test (2026-09-07, goal: "1600 missing XBRL" reduction sweep): the same
`if not quality_row:` early return fixed for ETFs (SPY/QQQ/IWM,
test_etf_zero_balance_sheet_history_reason_20260906.py) has the identical unfixed gap for the
much larger RIC/CEF population - a closed-end fund (BlackRock B-ticker/Invesco V-ticker CEFs,
GGN, BST, and siblings) also has ZERO annual_balance_sheet rows (same "no 10-K ever filed" root
fact, just a different entity type SEC classifies differently), but `_get_etf_symbols()` doesn't
cover them.

Live-confirmed: BST/BGY/BUI/GGN all still showed "missing_sec_data" for their entire
quality_metrics row after a fresh reload that had already landed
_apply_structural_entity_type_exemption_reasons() (which recategorizes further down
_compute_quality_metrics) - this early return exits before that code, or the RIC/ETF-trust
recategorize loops, are ever reached, so gate coverage everywhere else in the function was
irrelevant for this population. Fixed by checking _get_registered_investment_company_symbols()
and _get_structural_entity_type_exemptions() here too (via the new
_no_balance_sheet_row_reason() helper), before falling back to _get_etf_symbols().
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRicEntityExemptZeroBalanceSheetHistoryReason:
    def test_ric_with_no_balance_sheet_row_reports_ric_reason(self):
        loader = _make_loader()
        with (
            patch.object(type(loader), "_get_registered_investment_company_symbols", return_value=frozenset({"GGN"})),
            patch.object(type(loader), "_get_structural_entity_type_exemptions", return_value=frozenset()),
            patch.object(type(loader), "_get_etf_symbols", return_value=frozenset()),
        ):
            result = loader._compute_quality_metrics("GGN", None)

        assert result["reason"] == "registered_investment_company_no_xbrl"
        assert result["roce_pct_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_structurally_exempt_cef_with_no_balance_sheet_row_reports_entity_exempt_reason(self):
        loader = _make_loader()
        with (
            patch.object(type(loader), "_get_registered_investment_company_symbols", return_value=frozenset()),
            patch.object(type(loader), "_get_structural_entity_type_exemptions", return_value=frozenset({"BST"})),
            patch.object(type(loader), "_get_etf_symbols", return_value=frozenset()),
        ):
            result = loader._compute_quality_metrics("BST", None)

        assert result["reason"] == "entity_type_structurally_exempt_10k_filing"
        assert result["roce_pct_unavailable_reason"] == "entity_type_structurally_exempt_10k_filing"

    def test_ric_gate_wins_over_broader_entity_exempt_gate(self):
        """A symbol caught by both gates should get the more specific RIC reason - matching
        the same preference order the mid-function recategorize loops already use."""
        loader = _make_loader()
        with (
            patch.object(type(loader), "_get_registered_investment_company_symbols", return_value=frozenset({"GGN"})),
            patch.object(type(loader), "_get_structural_entity_type_exemptions", return_value=frozenset({"GGN"})),
            patch.object(type(loader), "_get_etf_symbols", return_value=frozenset()),
        ):
            result = loader._compute_quality_metrics("GGN", None)

        assert result["reason"] == "registered_investment_company_no_xbrl"

    def test_symbol_outside_all_gates_keeps_generic_reason(self):
        loader = _make_loader()
        with (
            patch.object(type(loader), "_get_registered_investment_company_symbols", return_value=frozenset()),
            patch.object(type(loader), "_get_structural_entity_type_exemptions", return_value=frozenset()),
            patch.object(type(loader), "_get_etf_symbols", return_value=frozenset()),
        ):
            result = loader._compute_quality_metrics("ACTU", None)

        assert result["reason"] == "missing_sec_data"
