"""Regression test (2026-09-10, goal: "under 500" push, missing_cash_flow_data investigation):
load_sec_valuations.py's dcf_fcf_unavailable_reason chain never checked for a filer whose 3 most
recent fiscal years are ALL missing operating_cash_flow despite real historical OCF further back
- the exact same structural fact already given its own specific reason
("no_recent_operating_cash_flow_reported") for quality_metrics.accruals_ratio/ocf_to_net_income
and value_metrics.fcf_yield via _get_no_recent_operating_cash_flow_symbols() in
vqg_symbol_gates.py.

Live-confirmed via GLNG (Golar LNG, 20-F filer): real
NetCashProvidedByUsedInOperatingActivitiesContinuingOperations tagged through FY2021, absent
under every cash-flow-shaped us-gaap concept since - a genuine filer-side tagging stop, not an
extraction gap. XRTX confirmed the same shape by the same live audit that established the
sibling gate this reuses.
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


class TestSecValuationsNoRecentOcfDcfFcfReason:
    def test_no_recent_ocf_symbol_gets_specific_reason(self, monkeypatch):
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_no_recent_ocf_dcf_fcf_reason("GLNGSHAPE", result)

        assert result["dcf_fcf_unavailable_reason"] == "no_recent_operating_cash_flow_reported"

    def test_non_matching_symbol_keeps_generic_reason(self, monkeypatch):
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=False))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_no_recent_ocf_dcf_fcf_reason("REALCO", result)

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_does_not_touch_a_different_already_specific_reason(self, monkeypatch):
        # Guard against ever overriding anything other than the exact generic
        # "missing_cash_flow_data" fallback this method targets, mirroring every sibling
        # _recategorize_*_dcf_fcf_reason guard in this file.
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "negative_free_cash_flow"}

        loader._recategorize_no_recent_ocf_dcf_fcf_reason("GLNGSHAPE", result)

        assert result["dcf_fcf_unavailable_reason"] == "negative_free_cash_flow"
