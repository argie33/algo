"""Regression test (2026-09-07, goal: "1600 missing XBRL" reduction sweep):
vqg_symbol_gates.py's `_get_structural_entity_type_exemptions()` was added 2026-09-06
specifically to catch CEF/BDC/ETF-trust symbols across every metric in one gate ("Creates a
single gate that captures all entity-type-based structural exemptions" - its own docstring)
but was never actually called anywhere - a fully half-wired fix. Live-confirmed via a fresh
coverage query: 60 of 76 active-universe symbols carrying
`roce_pct_unavailable_reason='missing_sec_data'` (BlackRock B-ticker/Invesco V-ticker CEFs, SPY,
and siblings) are covered by this gate but were still landing on the generic "missing_sec_data"
("Missing SEC/XBRL data") instead of "entity_type_structurally_exempt_10k_filing" ("Legitimate /
not applicable"). Fixed by adding `_apply_structural_entity_type_exemption_reasons()` (defined
alongside the gate in vqg_symbol_gates.py, to avoid growing vqg_quality.py's line count -
that file is already past the file-size ratchet's hard ceiling) and calling it from
_compute_quality_metrics() right after the RIC recategorize loop.
"""

from unittest.mock import patch

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin


def _make_gate_mixin() -> SymbolGateMixin:
    return SymbolGateMixin.__new__(SymbolGateMixin)


class TestStructuralEntityTypeExemptionGateWired:
    def test_structurally_exempt_symbol_recategorizes_generic_reasons(self):
        mixin = _make_gate_mixin()
        metrics = {
            "roce_pct": None,
            "roce_pct_unavailable_reason": "missing_sec_data",
            "debt_to_equity": None,
            "debt_to_equity_unavailable_reason": "total_debt_not_itemized",
            "fcf_margin": None,
            "fcf_margin_unavailable_reason": "operating_income_not_itemized",
        }
        with patch.object(type(mixin), "_get_structural_entity_type_exemptions", return_value=frozenset({"BST"})):
            mixin._apply_structural_entity_type_exemption_reasons("BST", metrics)

        assert metrics["roce_pct_unavailable_reason"] == "entity_type_structurally_exempt_10k_filing"
        assert metrics["debt_to_equity_unavailable_reason"] == "entity_type_structurally_exempt_10k_filing"
        assert metrics["fcf_margin_unavailable_reason"] == "entity_type_structurally_exempt_10k_filing"

    def test_symbol_outside_gate_keeps_generic_reason(self):
        mixin = _make_gate_mixin()
        metrics = {"roce_pct": None, "roce_pct_unavailable_reason": "missing_sec_data"}
        with patch.object(type(mixin), "_get_structural_entity_type_exemptions", return_value=frozenset()):
            mixin._apply_structural_entity_type_exemption_reasons("NORMALCO", metrics)

        assert metrics["roce_pct_unavailable_reason"] == "missing_sec_data"

    def test_does_not_touch_a_field_that_already_computed_a_real_value(self):
        """A symbol in the gate but with a real, computed roce_pct (e.g. it happens to also
        report GAAP financials for one metric) must not have that value's reason overwritten -
        the loop only ever touches fields where metrics[field] is None."""
        mixin = _make_gate_mixin()
        metrics = {"roe": 12.5, "roe_unavailable_reason": None}
        with patch.object(type(mixin), "_get_structural_entity_type_exemptions", return_value=frozenset({"BST"})):
            mixin._apply_structural_entity_type_exemption_reasons("BST", metrics)

        assert metrics["roe"] == 12.5
        assert metrics["roe_unavailable_reason"] is None

    def test_only_recategorizes_known_generic_source_reasons(self):
        """A field already carrying a more specific, correct reason (e.g. a real
        implausible_ratio rejection) must not be swept up just because the symbol is in the
        gate - only the 7 generic catch-all reasons are eligible for recategorization."""
        mixin = _make_gate_mixin()
        metrics = {"roce_pct": None, "roce_pct_unavailable_reason": "implausible_ratio"}
        with patch.object(type(mixin), "_get_structural_entity_type_exemptions", return_value=frozenset({"BST"})):
            mixin._apply_structural_entity_type_exemption_reasons("BST", metrics)

        assert metrics["roce_pct_unavailable_reason"] == "implausible_ratio"

    def test_wired_into_compute_quality_metrics_caller_site(self):
        """Static wiring check: the real pipeline caller (_compute_quality_metrics) must
        actually invoke the new method, not just leave it as dead code the way
        _get_structural_entity_type_exemptions() itself sat unused for a full day."""
        import inspect

        from loaders.helpers.vqg_quality import QualityMetricsMixin

        source = inspect.getsource(QualityMetricsMixin._compute_quality_metrics)
        assert "_apply_structural_entity_type_exemption_reasons(symbol, metrics)" in source
