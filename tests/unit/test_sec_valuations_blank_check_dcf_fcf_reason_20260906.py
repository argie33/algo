"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
load_sec_valuations.py's dcf_fcf_unavailable_reason chain (RIC/currency/royalty-trust/capex
recategorizations) never checked for a pre-merger SPAC shell (SIC "Blank Checks") - a real
recovery, unlike this file's capex-never-tagged sibling fix, since "no_revenue_reported" is in
the "Legitimate / not applicable" category, not "Missing SEC/XBRL data".

Live-confirmed 11 active-universe symbols (XFLH/PTOR/ALDF/GIX/GIW/NWAX/WENC/QETAR/QUMSR/FSHP/
FSHPR) hitting this exact gap - most too recently listed to clear the capex-never-tagged gate's
own >=2-real-fiscal-year floor, so they fell through every existing check to the generic
"missing_cash_flow_data" instead of the same "no_revenue_reported" reason the whole-row
all_valuation_metrics_null fallback already uses for this identical population.
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

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._matches)

    def __exit__(self, *exc):
        return False


class TestSecValuationsBlankCheckDcfFcfReason:
    def test_blank_check_symbol_gets_no_revenue_reported(self, monkeypatch):
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_blank_check_dcf_fcf_reason("SPACX", result)

        assert result["dcf_fcf_unavailable_reason"] == "no_revenue_reported"

    def test_non_blank_check_symbol_keeps_generic_reason(self, monkeypatch):
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(matches=False))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_blank_check_dcf_fcf_reason("REALCO", result)

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_does_not_touch_a_different_already_specific_reason(self, monkeypatch):
        # Guard against ever overriding anything other than the exact generic
        # "missing_cash_flow_data" fallback this method targets, even for a matching symbol -
        # mirrors every sibling recategorize_*_dcf_fcf_reason function's identical guard.
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "capex_never_tagged_in_recent_filings"}

        loader._recategorize_blank_check_dcf_fcf_reason("SPACX", result)

        assert result["dcf_fcf_unavailable_reason"] == "capex_never_tagged_in_recent_filings"
