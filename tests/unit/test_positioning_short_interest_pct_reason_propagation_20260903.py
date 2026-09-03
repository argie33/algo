"""Regression test: positioning_metrics.short_interest_pct_unavailable_reason must
propagate the specific reason already tracked by short_interest_finra, not collapse it
into the generic "missing_finra_data".

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction sweep): the short-interest
source-table query in load_positioning_metrics.py fetched short_pct/short_shares/
settlement_date/days_to_cover/avg_daily_volume but never the sibling `reason` column, even
though load_short_interest_finra.py's own fetch_incremental already diagnoses WHY short_pct
is None whenever short_shares is real (foreign_private_issuer_shares_unavailable/
shares_outstanding_unavailable - both permanent/structural, mapped by scores.py to
"Legitimate / not applicable"/"Ownership data unresolved" respectively) vs genuinely no
settlement report at all (finra_data_unavailable/finra_api_unreachable, correctly "Missing
SEC/XBRL data"). Live-confirmed 43 of 88 universe "has a real short_interest_finra row but
short_pct NULL" symbols (e.g. ERIC/GGAL/TEO/STNE/AFYA) carry one of the two specific
structural reasons - same reason-propagation-gap shape as
test_positioning_reason_propagation.py's institutional_ownership_pct fix, just for the
FINRA source instead of 13F.
"""

from unittest.mock import patch

from loaders.load_positioning_metrics import PositioningMetricsLoader


def _make_loader():
    return PositioningMetricsLoader.__new__(PositioningMetricsLoader)


class _RoutingCursor:
    """Returns canned rows keyed by which table the query touches; empty/None for every
    other table so the surrounding institutional/A-D-rating logic reaches "unavailable"
    cleanly without extra DB round trips to mock."""

    def __init__(self, short_interest_rows=None):
        self._short_interest_rows = short_interest_rows or []
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        if "short_interest_finra" in self._last_query:
            return self._short_interest_rows
        return []


def _run(monkeypatch, short_interest_rows=None):
    import loaders.load_positioning_metrics as mod

    cursor = _RoutingCursor(short_interest_rows=short_interest_rows)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_compute_ad_rating", return_value=(None, "insufficient_price_history")):
        return loader.fetch_incremental("TEST", since=None)[0]


class TestShortInterestPctReasonPropagation:
    def test_propagates_foreign_private_issuer_shares_unavailable(self, monkeypatch):
        # (short_pct, short_shares, settlement_date, days_to_cover, avg_daily_volume, reason)
        row = (None, 70050779, "2026-07-31", None, None, "foreign_private_issuer_shares_unavailable")
        result = _run(monkeypatch, short_interest_rows=[row])

        assert result["short_interest_pct_unavailable_reason"] == "foreign_private_issuer_shares_unavailable"

    def test_propagates_shares_outstanding_unavailable(self, monkeypatch):
        row = (None, 12345, "2026-07-31", None, None, "shares_outstanding_unavailable")
        result = _run(monkeypatch, short_interest_rows=[row])

        assert result["short_interest_pct_unavailable_reason"] == "shares_outstanding_unavailable"

    def test_no_rows_falls_back_to_generic_reason(self, monkeypatch):
        result = _run(monkeypatch, short_interest_rows=[])

        assert result["short_interest_pct_unavailable_reason"] == "missing_finra_data"

    def test_genuine_no_settlement_report_keeps_generic_reason(self, monkeypatch):
        row = (None, None, "2026-07-31", None, None, "finra_data_unavailable")
        result = _run(monkeypatch, short_interest_rows=[row])

        # finra_data_unavailable already maps to the same "Missing SEC/XBRL data" category
        # as missing_finra_data - propagating it is harmless either way, but the marker
        # itself has no real short_shares/reason to distinguish from a genuine gap.
        assert result["short_interest_pct_unavailable_reason"] == "finra_data_unavailable"

    def test_real_value_still_populates_with_no_reason(self, monkeypatch):
        row = (4.2, 1000000, "2026-07-31", 1.5, 500000, None)
        result = _run(monkeypatch, short_interest_rows=[row])

        assert result["short_interest_pct"] == 4.2
        assert result.get("short_interest_pct_unavailable_reason") is None
