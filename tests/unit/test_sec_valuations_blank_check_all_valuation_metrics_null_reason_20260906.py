"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
load_sec_valuations.py's "all_valuation_metrics_null" whole-row fallback (fires when PE/PB/PS/
FCF-yield are all None) propagates into EVERY value_metrics field at once via
_build_value_metrics's "not row_dict or row_dict.get('data_unavailable')" early return
(pe_ratio/pb_ratio/ps_ratio/peg_ratio/ev_ebitda/ev_revenue/market_cap/dividend_yield/fcf_yield/
intrinsic_value/margin_of_safety/held_percent_institutions) - but never checked whether the
symbol is a SEC-classified blank-check (SIC 6770) pre-merger SPAC shell first, the same
population `_get_blank_check_symbols()` already recategorizes to "no_revenue_reported"
("Legitimate / not applicable") elsewhere (vqg_quality.py's roic_pct/gross_margin/ebitda_margin,
vqg_value.py's ps_ratio/ev_revenue) - a SPAC has no real operating business before its merger
(trust-account interest income only), so PE/PB/PS/FCF-yield are all structurally undefined, not
a data-extraction gap.

Live-confirmed via a direct company_info_sec join: 28 of 61 active symbols hitting
"all_valuation_metrics_null" (46%, by far the largest single sic_description cluster) are SIC
"Blank Checks".
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


class TestSecValuationsBlankCheckAllValuationMetricsNullReason:
    def test_blank_check_symbol_reports_no_revenue_reported(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_blank_check_all_valuation_metrics_null_reason("SPACX", result)

        assert result["reason"] == "no_revenue_reported"

    def test_non_blank_check_symbol_keeps_generic_reason(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=False))
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_blank_check_all_valuation_metrics_null_reason("REALCO", result)

        assert result["reason"] == "all_valuation_metrics_null"

    def test_does_not_touch_a_different_already_specific_reason(self, monkeypatch):
        # Guard against ever overriding anything other than the exact generic
        # "all_valuation_metrics_null" fallback this method targets, even for a SIC-matched
        # symbol - mirrors _recategorize_ric_dcf_fcf_reason's identical guard above.
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(matches=True))
        loader = _make_loader()
        result: dict = {"reason": "shares_outstanding_scale_mismatch"}

        loader._recategorize_blank_check_all_valuation_metrics_null_reason("SPACX", result)

        assert result["reason"] == "shares_outstanding_scale_mismatch"
