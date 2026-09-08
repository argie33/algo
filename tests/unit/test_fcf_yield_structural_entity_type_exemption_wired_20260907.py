"""Regression test (2026-09-07, goal: "1600 missing XBRL" reduction sweep):
value_metrics.fcf_yield_unavailable_reason's reason chain (vqg_value.py) already checks the
narrower _get_registered_investment_company_symbols()/_get_etf_trust_no_stockholders_equity_
symbols()/royalty-trust/blank-check/unsupported-currency gates, but never the broader
_get_structural_entity_type_exemptions() gate (SIC-code/entity_type based CEF/BDC/ETF-trust
membership) that quality_metrics' _compute_quality_metrics was wired up to use this same
session. Live-confirmed 64 of 153 active-universe fcf_yield "missing_sec_data" symbols
(BlackRock B-ticker CEF tickers: ASA/BBN/BCAT/BDJ/BGR/BST/... ) are covered by this gate but
fall through every narrower check above to the generic fallback.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _run(monkeypatch, symbol, gate_overrides=None, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = _make_loader()
    for gate_name, gate_value in (gate_overrides or {}).items():
        monkeypatch.setattr(loader, gate_name, lambda v=gate_value: v)
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


class TestFcfYieldStructuralEntityTypeExemptionWired:
    def test_structurally_exempt_symbol_gets_entity_type_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "BST",
            gate_overrides={"_get_structural_entity_type_exemptions": frozenset({"BST"})},
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "entity_type_structurally_exempt_10k_filing"

    def test_narrower_ric_gate_still_wins_when_symbol_is_in_both(self, monkeypatch):
        """A symbol caught by BOTH the narrower RIC gate and the new broad exemption gate
        keeps the RIC block's own more specific reason - the new check is the last fallback
        before the generic reason, never overriding an earlier, more specific match."""
        result = _run(
            monkeypatch,
            "ETO",
            gate_overrides={
                "_get_registered_investment_company_symbols": frozenset({"ETO"}),
                "_get_structural_entity_type_exemptions": frozenset({"ETO"}),
            },
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_symbol_outside_gate_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "NORMALCO",
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] != "entity_type_structurally_exempt_10k_filing"
