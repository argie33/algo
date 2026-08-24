"""Regression test: institutional_ownership_pct/institutional_holders_count/
top_10_institutions_pct_unavailable_reason must propagate the specific reason already
tracked by institutional_holdings_13f, not collapse it into the generic
"missing_sec_data"/"institutional_data_not_available".

Found live 2026-08-18 (goal: "no SEC data" audit): the institutional source-table query in
load_positioning_metrics.py already SELECTs a `reason` column (no_resolved_13f_holdings,
shares_outstanding_unavailable, not_found_in_institutional_holdings_13f) - a real,
already-diagnosed cause sitting one column over - but the value was fetched and never used,
so every one of these collapsed into the generic reason instead, reading as an unexplained
loader gap. Live-confirmed 1,668 of institutional_holdings_13f's rows carry one of these
specific reasons.

REMOVED 2026-08-24: the insider_ownership_pct-propagation tests that used to live here
(insider_holdings_sec's no_form345_filings_in_lookback_window/
shares_outstanding_unavailable_for_pct_calc reasons) - insider_ownership_pct was removed
entirely (static governance metric, near-zero information content for weeks-scale swing
trading, recurring source of real bugs). See loaders/DEPRECATED_LOADERS.md.
"""

from unittest.mock import patch

from loaders.load_positioning_metrics import PositioningMetricsLoader


def _make_loader():
    return PositioningMetricsLoader.__new__(PositioningMetricsLoader)


class _RoutingCursor:
    """Returns canned rows keyed by which table the query touches; empty/None for every other
    table so the surrounding short-interest/A-D-rating logic reaches "unavailable" cleanly
    without extra DB round trips to mock."""

    def __init__(self, institutional_row=None):
        self._institutional_row = institutional_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "institutional_holdings_13f" in self._last_query:
            return self._institutional_row
        return None

    def fetchall(self):
        return []


def _run(monkeypatch, institutional_row=None):
    import loaders.load_positioning_metrics as mod

    cursor = _RoutingCursor(institutional_row=institutional_row)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_compute_ad_rating", return_value=(None, "insufficient_price_history")):
        return loader.fetch_incremental("TEST", since=None)[0]


class TestPositioningReasonPropagation:
    def test_institutional_ownership_propagates_no_resolved_13f_holdings(self, monkeypatch):
        # (institutional_ownership_pct, data_unavailable, reason, holders_count, top10_pct)
        row = (None, True, "no_resolved_13f_holdings", None, None)
        result = _run(monkeypatch, institutional_row=row)

        assert result["institutional_ownership_pct_unavailable_reason"] == "no_resolved_13f_holdings"
        assert result["institutional_holders_count_unavailable_reason"] == "no_resolved_13f_holdings"
        assert result["top_10_institutions_pct_unavailable_reason"] == "no_resolved_13f_holdings"

    def test_institutional_ownership_propagates_shares_outstanding_unavailable(self, monkeypatch):
        row = (None, True, "shares_outstanding_unavailable", None, None)
        result = _run(monkeypatch, institutional_row=row)

        assert result["institutional_ownership_pct_unavailable_reason"] == "shares_outstanding_unavailable"

    def test_institutional_ownership_no_row_falls_back_to_generic_reason(self, monkeypatch):
        result = _run(monkeypatch, institutional_row=None)

        assert result["institutional_ownership_pct_unavailable_reason"] == "missing_sec_data"
        assert result["institutional_holders_count_unavailable_reason"] == "institutional_data_not_available"
        assert result["top_10_institutions_pct_unavailable_reason"] == "institutional_data_not_available"

    def test_real_values_still_populate_with_no_reason(self, monkeypatch):
        institutional_row = (42.5, False, None, 12, 30.1)
        result = _run(monkeypatch, institutional_row=institutional_row)

        assert result["institutional_ownership_pct"] == 42.5
        assert result.get("institutional_ownership_pct_unavailable_reason") is None
