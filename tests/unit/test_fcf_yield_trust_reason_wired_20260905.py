"""Regression test (2026-09-05, goal session: "SEC/XBRL missing data to zero" sweep):
value_metrics.fcf_yield_unavailable_reason (and its intrinsic_value/margin_of_safety
derivatives) must report "registered_investment_company_no_xbrl"/"etf_trust_no_gaap_financials"
for a closed-end fund or physical commodity/crypto trust, not the generic
"no_recent_free_cash_flow_reported".

quality_metrics.fcf_margin's sibling reason chain (vqg_quality.py) already checks
_get_registered_investment_company_symbols()/_get_etf_trust_no_stockholders_equity_symbols()
before falling through to the generic reasons - value_metrics.fcf_yield's chain (vqg_value.py)
never had this wired in, despite deriving from the exact same "does this filer have a GAAP
cash-flow statement at all" structural fact. Live-sampled the 146-symbol "Missing SEC/XBRL
data" fcf_yield bucket and found real CEFs (ETO/EIC/BTT/KTF/GUT/TYG-class) and ETF trusts
(SLV/IAU/GBTC, confirmed present in etf_symbols) mixed in with genuine gaps.
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


class TestFcfYieldTrustReasonWired:
    def test_etf_trust_symbol_gets_etf_trust_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "GLDM",
            gate_overrides={"_get_etf_trust_no_stockholders_equity_symbols": frozenset({"GLDM"})},
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert result["intrinsic_value_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert result["margin_of_safety_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_registered_investment_company_symbol_gets_ric_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "ETO",
            gate_overrides={"_get_registered_investment_company_symbols": frozenset({"ETO"})},
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

    def test_non_trust_symbol_keeps_generic_reason(self, monkeypatch):
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

        assert result["fcf_yield_unavailable_reason"] != "etf_trust_no_gaap_financials"
        assert result["fcf_yield_unavailable_reason"] != "registered_investment_company_no_xbrl"

    def test_royalty_trust_symbol_gets_reit_special_entity_reason(self, monkeypatch):
        # FIXED 2026-09-06 (same-day follow-up, comprehensive RIC-gap scan): royalty trusts
        # (_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS - NRT/MTR/CRT/PBT/SBR/SJT) are the third
        # member of this "no real cash-flow-statement concepts" family, already recategorized
        # in quality_metrics' fcf_margin sibling chain, but never checked here.
        result = _run(
            monkeypatch,
            "NRT",
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "reit_special_entity"
        assert result["intrinsic_value_unavailable_reason"] == "reit_special_entity"
        assert result["margin_of_safety_unavailable_reason"] == "reit_special_entity"

    def test_unsupported_currency_ocf_symbol_gets_specific_reason(self, monkeypatch):
        # ADDED 2026-09-06 (same-day follow-up, comprehensive RIC-gap scan): a foreign private
        # issuer whose annual_cash_flow row was already tagged "unsupported_currency_no_fx_
        # rate" (real OCF, only tagged under an unsupported currency like ARS) has a real,
        # non-fabricatable ocf=None - same structural-fact class as RIC/ETF-trust/royalty-
        # trust, never checked here before.
        result = _run(
            monkeypatch,
            "GGAL",
            gate_overrides={"_get_unsupported_currency_ocf_symbols": frozenset({"GGAL"})},
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=None,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "unsupported_currency_no_fx_rate"
        assert result["intrinsic_value_unavailable_reason"] == "unsupported_currency_no_fx_rate"
        assert result["margin_of_safety_unavailable_reason"] == "unsupported_currency_no_fx_rate"
