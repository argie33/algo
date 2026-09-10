"""Regression test (2026-09-10, goal: "under 300" missing-XBRL push): value_metrics.
pb_ratio_unavailable_reason must report "reit_special_entity" for a pure oil/gas grantor
royalty trust with no StockholdersEquity concept at all, not the generic
"stockholders_equity_never_tagged_in_filings".

vqg_value.py's pb_ratio_reason chain already special-cases preferred/debt securities
(preferred_or_debt_security_no_common_equity_ratio) but never checked royalty-trust
membership before falling to the generic reason - the sibling fcf_yield/quality_metrics
reason chains (test_fcf_yield_trust_reason_wired_20260905.py,
test_royalty_trust_no_balance_sheet_reason_20260904.py) already cover this same structural
fact for their own fields. Live-confirmed NRT (the one member of
_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS with genuinely no equity concept tagged) stuck on
the generic reason for pb_ratio despite total_debt/roa/roe/current_ratio/fcf_yield all
already correctly resolving to "reit_special_entity".
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
        # No annual_balance_sheet row at all - the "never tagged" shape this reason chain
        # is meant to distinguish from a real negative/positive book value.
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _run(monkeypatch, symbol, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


class TestPbRatioRoyaltyTrustReason:
    def test_royalty_trust_symbol_gets_reit_special_entity_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "NRT",
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=2.0,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["pb_ratio_unavailable_reason"] == "reit_special_entity"

    def test_non_trust_symbol_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "NORMALCO",
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=2.0,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["pb_ratio_unavailable_reason"] != "reit_special_entity"
