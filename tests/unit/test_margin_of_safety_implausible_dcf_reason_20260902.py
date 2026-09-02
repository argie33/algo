"""Regression test: margin_of_safety_unavailable_reason must say "implausible_dcf_result" (not
generic "missing_sec_data") when intrinsic_value_per_share is present but margin_of_safety_pct
is None.

Found live 2026-09-02: load_sec_valuations.py's _compute_dcf_intrinsic_value computes
intrinsic_per_share and margin_of_safety_pct together and returns them as a pair - the ONLY
code path that returns a real intrinsic_per_share alongside a None margin_of_safety_pct is the
explicit `-1000 <= margin_of_safety_pct <= 1000` bounds rejection (see that function's final
`if`/`return round(intrinsic_per_share, 2), None` branch) - a 100%-precise signal, not a
probabilistic gate, since there is no other way to reach this exact combination. Live-confirmed
this covers every universe row in this state (VRNS/SLNG/SMTC and more).
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

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


def _run(monkeypatch, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("VRNS", _FakeSecValRow(sec_val_fields))


class TestMarginOfSafetyImplausibleDcfReason:
    def test_intrinsic_value_present_margin_of_safety_none_reports_implausible_dcf(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=6.0,
            intrinsic_value_per_share=0.36,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=4_845_393_769.0,
        )

        assert result["intrinsic_value_per_share"] == 0.36
        assert result.get("intrinsic_value_unavailable_reason") is None
        assert result["margin_of_safety_unavailable_reason"] == "implausible_dcf_result"

    def test_both_none_still_uses_fcf_yield_derived_reason(self, monkeypatch):
        # Unaffected control: intrinsic_value_per_share also None must keep using
        # intrinsic_value_reason_from_fcf_yield(), not the new branch.
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=-5.0,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["margin_of_safety_unavailable_reason"] == "negative_free_cash_flow"

    def test_real_margin_of_safety_still_populates_with_no_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=6.0,
            intrinsic_value_per_share=25.0,
            margin_of_safety_pct=12.5,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["margin_of_safety_pct"] == 12.5
        assert result.get("margin_of_safety_unavailable_reason") is None
