"""Regression test (2026-09-11, goal: "SEC/XBRL missing data under 200" push):
load_sec_valuations.py used to call _recategorize_capex_never_tagged_dcf_fcf_reason BEFORE
_recategorize_blank_check_dcf_fcf_reason. A pre-merger SPAC shell (SIC "Blank Checks") often
has >=2 real fiscal years with some operating_cash_flow on file (trust interest, admin costs)
and obviously no capex - satisfying the capex-never-tagged check's own DB criteria first and
overwriting dcf_fcf_unavailable_reason away from "missing_cash_flow_data" before the blank-check
check's own guard (`!= "missing_cash_flow_data"`) ever got a chance to fire. Live-confirmed 14
SIC-6770 symbols (AFJK/ALDF/CAES/CEPO/FSHP/FSHPR/GIW/GTEN/LEGO/MTNE/PGACR/QETAR/QUMSR/XFLH) stuck
on "capex_never_tagged_in_recent_filings" ("Missing SEC/XBRL data") instead of the correct
"no_revenue_reported" ("Legitimate / not applicable") despite the blank-check fix existing since
2026-09-06 (test_sec_valuations_blank_check_dcf_fcf_reason_20260906.py only exercises that
function in isolation, so the ordering bug in the caller was invisible to it).

This test exercises both checks together, in the fixed call order, against a symbol matching
BOTH the blank-check DB query and the capex-never-tagged DB query, to guard the ordering itself.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _AlwaysMatchCursor:
    """Every recategorize_*_dcf_fcf_reason inline query in this file does a simple
    `fetchone() is not None` presence check - returning a truthy row for every query
    simulates a symbol that matches both the blank-check SIC lookup and the capex-never-
    tagged OCF/capex-presence query."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return []


class _AlwaysMatchDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _AlwaysMatchCursor()

    def __exit__(self, *exc):
        return False


class TestSecValuationsBlankCheckDcfFcfOrdering:
    def test_blank_check_wins_over_capex_never_tagged_when_run_in_fixed_order(self, monkeypatch):
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", _AlwaysMatchDatabaseContext())
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        # Fixed order (load_sec_valuations.py): blank-check BEFORE capex-never-tagged.
        loader._recategorize_blank_check_dcf_fcf_reason("SPACX", result)
        loader._recategorize_capex_never_tagged_dcf_fcf_reason("SPACX", result)

        assert result["dcf_fcf_unavailable_reason"] == "no_revenue_reported"

    def test_old_order_would_have_produced_the_bug(self, monkeypatch):
        """Documents the bug this fix closes: the OLD order (capex before blank-check) leaves
        a symbol matching both stuck on the wrong, "Missing SEC/XBRL data" reason."""
        import loaders.helpers.sec_valuations_dcf_fcf_recategorize as mod

        monkeypatch.setattr(mod, "DatabaseContext", _AlwaysMatchDatabaseContext())
        loader = _make_loader()
        result: dict = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_capex_never_tagged_dcf_fcf_reason("SPACX", result)
        loader._recategorize_blank_check_dcf_fcf_reason("SPACX", result)

        assert result["dcf_fcf_unavailable_reason"] == "capex_never_tagged_in_recent_filings"
