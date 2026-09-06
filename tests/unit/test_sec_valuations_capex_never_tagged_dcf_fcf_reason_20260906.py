"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
load_sec_valuations.py's dcf_fcf_unavailable_reason chain (RIC/currency/royalty-trust
recategorizations) never checked for a filer with real, recent operating cash flow but capex
never itemized in its 3 most recent real fiscal years - the exact same structural fact already
given its own specific reason ("capex_never_tagged_in_recent_filings") for quality_metrics.
fcf_margin/value_metrics.fcf_yield via _get_no_recent_capex_symbols() in vqg_quality.py/
vqg_value.py.

Live-confirmed via CWH (Camping World Holdings): real, growing OCF every year, a real capex
figure ("PaymentsToAcquireProductiveAssets") through FY2022, then nothing under any capex-shaped
concept in its companyfacts JSON since - an ordinary filing-presentation gap, not a currency/
entity-type structural fact. 177 of 210 (84%) of the current "missing_cash_flow_data" population
share this exact profile.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, matches: bool) -> None:
        self._matches = matches

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (1,) if self._matches else None

    def fetchall(self):
        return []


class _FakeDatabaseContext:
    def __init__(self, matches: bool) -> None:
        self._matches = matches

    def __enter__(self):
        return _FakeCursor(self._matches)

    def __exit__(self, *exc):
        return False


class TestSecValuationsCapexNeverTaggedDcfFcfReason:
    def test_capex_never_tagged_symbol_gets_specific_reason(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_capex_never_tagged_dcf_fcf_reason("CWHSHAPE", result)

        assert result["dcf_fcf_unavailable_reason"] == "capex_never_tagged_in_recent_filings"

    def test_non_matching_symbol_keeps_generic_reason(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=False))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_capex_never_tagged_dcf_fcf_reason("REALCO", result)

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_does_not_touch_a_different_already_specific_reason(self, monkeypatch):
        # Guard against ever overriding anything other than the exact generic
        # "missing_cash_flow_data" fallback this method targets, even for a matching symbol -
        # mirrors _recategorize_ric_dcf_fcf_reason's identical guard.
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "negative_free_cash_flow"}

        loader._recategorize_capex_never_tagged_dcf_fcf_reason("CWHSHAPE", result)

        assert result["dcf_fcf_unavailable_reason"] == "negative_free_cash_flow"
