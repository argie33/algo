"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up / "implausible
values" sweep): ev_ebitda_unavailable_reason never re-derived load_sec_valuations.py's own
ev_ebitda bound (sec_valuations_yield_dcf.py: `if 0 < ev_ebitda <= 10000`), same bug class
already fixed today for pe_ratio/pb_ratio/ps_ratio/ev_revenue - a real, positive ebitda combined
with a real, positive computed enterprise value can still fall outside 10000 (a near-zero-EBITDA
blowup), falling through to generic "missing_sec_data" instead of "implausible_ratio".

Live-confirmed EFTY (implied ev_ebitda~11,973), AAOI (~29,878), MHH (~55,880) - the universe's
remaining active ev_ebitda "missing_sec_data" symbols besides HRI (separately fixed as a real
EBITDA-value bug, see test_sec_valuations_ebitda_pretax_fallback_interest_addback_20260905.py).

SPY (an ETF, also in this bucket) was investigated for the same etf_symbols fallback added to
total_debt/total_cash in vqg_quality.py, but that fix does NOT apply here: SPY has no
sec_valuations row at all, so it never reaches this per-symbol reason chain in the first place
(caught by load_value_quality_growth_metrics.py's earlier whole-row unavailable-marker default
instead) - confirmed by a failing test for dead code before it was removed.
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


class _RecordingCursor:
    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def _run(monkeypatch, symbol="EFTY", **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor()

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


class TestEvEbitdaImplausibleRatioReason:
    def test_efty_shaped_near_zero_ebitda_blowup_reports_implausible_ratio(self, monkeypatch):
        # market_cap + total_debt - total_cash = 226,952,200 + 2,081,612 - 5,426,805 ~
        # 223,606,997 real, positive computed EV; ebitda=18,677 real, positive but tiny ->
        # implied ev_ebitda ~ 11,973, over load_sec_valuations.py's 10000 ceiling.
        result = _run(
            monkeypatch,
            symbol="EFTY",
            pe_ratio=None,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=5.0,
            ev_ebitda=None,
            ebitda=18_677.0,
            enterprise_value=None,
            market_cap=226_952_200.0,
            total_debt=2_081_612.0,
            total_cash=5_426_805.0,
            fcf_yield=6.0,
        )

        assert result["ev_ebitda"] is None
        assert result["ev_ebitda_unavailable_reason"] == "implausible_ratio"

    def test_real_plausible_ev_ebitda_keeps_generic_reason_when_not_extracted(self, monkeypatch):
        # Same shape as the debt/negative-EV sibling tests: a real, in-bounds ratio that came
        # back None for some other, genuinely ambiguous reason must NOT be relabeled.
        result = _run(
            monkeypatch,
            symbol="PLAUSIBLECO",
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=5.0,
            ev_ebitda=None,
            ebitda=5_000_000.0,
            enterprise_value=None,
            market_cap=20_000_000.0,
            total_debt=1_000_000.0,
            total_cash=5_000_000.0,  # computed EV = 16M, ratio = 16M/5M = 3.2, well in bounds
            fcf_yield=6.0,
        )

        assert result["ev_ebitda_unavailable_reason"] == "missing_sec_data"
