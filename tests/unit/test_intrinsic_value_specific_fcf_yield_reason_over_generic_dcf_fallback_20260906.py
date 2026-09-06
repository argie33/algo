"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): when
dcf_fcf_unavailable_reason is the generic "missing_cash_flow_data" fallback AND fcf_yield is
None with a specific fcf_yield_unavailable_reason available (registered_investment_company_
no_xbrl, no_recent_free_cash_flow_reported, etc.), intrinsic_value/margin_of_safety must
surface the specific reason instead of the generic one.

Root cause: vqg_value.py's `dcf_fcf_reason or intrinsic_value_reason_from_fcf_yield(...)` let
the generic ground-truth fallback win unconditionally, even over a genuinely more specific
fcf_yield-derived reason - live-confirmed on 300+ universe symbols (CURX, SLS, BTX, CEV, and
the BlackRock CEF family) stuck on "missing_cash_flow_data" despite a real, specific cause
being computed and stored on fcf_yield_unavailable_reason for the same row.

Companion to test_dcf_fcf_ground_truth_reason_preferred_over_fcf_yield_20260905.py, which
covers the case that must NOT change: fcf_yield present (not None) with the generic dcf
fallback still wins over a wrong fcf_yield-based guess.
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


def _run(monkeypatch, symbol, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = _make_loader()
    with (
        patch.object(loader, "_get_analyst_forward_eps", return_value=None),
        patch.object(loader, "_get_registered_investment_company_symbols", return_value={symbol}),
        patch.object(loader, "_get_etf_trust_no_stockholders_equity_symbols", return_value=set()),
        patch.object(loader, "_get_no_recent_free_cash_flow_symbols", return_value=set()),
        patch.object(loader, "_get_never_tagged_free_cash_flow_symbols", return_value=set()),
        patch.object(loader, "_get_no_recent_capex_symbols", return_value=set()),
    ):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


class TestSpecificFcfYieldReasonPreferredOverGenericDcfFallback:
    def test_generic_dcf_fallback_yields_to_specific_fcf_yield_reason_when_fcf_yield_is_none(self, monkeypatch):
        result = _run(
            monkeypatch,
            "BTX",
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=None,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            dcf_fcf_unavailable_reason="missing_cash_flow_data",
            enterprise_value=1_000_000_000.0,
            market_cap=10_549_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "registered_investment_company_no_xbrl"
        assert result["margin_of_safety_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_generic_dcf_fallback_still_wins_when_fcf_yield_is_present(self, monkeypatch):
        # Companion case that must NOT change (test_dcf_fcf_ground_truth_reason_preferred_
        # over_fcf_yield_20260905.py's test_missing_cash_flow_data_reason_also_preferred): a
        # real fcf_yield value means fcf_yield_reason_str is None (no specific alternative
        # exists), so the generic ground truth must still win over a wrong sign-based guess.
        result = _run(
            monkeypatch,
            "APTV",
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=13.18,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            dcf_fcf_unavailable_reason="missing_cash_flow_data",
            enterprise_value=1_000_000_000.0,
            market_cap=10_549_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "missing_cash_flow_data"
