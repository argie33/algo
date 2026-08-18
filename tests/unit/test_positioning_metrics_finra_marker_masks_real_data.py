"""Regression test (2026-08-18, "which factor inputs are missing the most" audit): plain
"ORDER BY settlement_date DESC" in load_positioning_metrics.py's short-interest fetch picked a
data_unavailable marker row over real historical data whenever the most recent FINRA settlement
period simply wasn't reported for a symbol (FINRA short-interest coverage is intermittent for
lower-liquidity issues). Live-confirmed on GV: the 2026-07-31 row is a bare
finra_data_unavailable marker, but 2026-07-15 and 2026-06-30 both have real short_pct on file -
positioning_metrics still reported "missing_finra_data" for it. 162 of 690 universe symbols
showing that reason have exactly this masking.

Fixed by ordering real rows (short_pct IS NOT NULL) ahead of marker rows before applying the
existing settlement_date DESC recency tiebreak, so the query surfaces the 2 most recent REAL
rows instead of a fresher marker plus whatever real row happens to be right behind it.
"""

from loaders.load_positioning_metrics import PositioningMetricsLoader


class _FakeCursor:
    def __init__(self, short_interest_rows):
        self._short_interest_rows = short_interest_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "short_interest_finra" in self._last_query:
            return self._short_interest_rows
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, short_interest_rows):
        self._short_interest_rows = short_interest_rows

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._short_interest_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, short_interest_rows):
    import loaders.load_positioning_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(short_interest_rows))
    loader = PositioningMetricsLoader.__new__(PositioningMetricsLoader)
    monkeypatch.setattr(loader, "_compute_ad_rating", lambda symbol: (None, "insufficient_history"))
    return loader


class TestPositioningMetricsFinraMarkerMasksRealData:
    def test_marker_row_does_not_mask_real_rows_behind_it(self, monkeypatch):
        # Simulates what the fixed ORDER BY returns from postgres: real rows first
        # (settlement_date DESC among themselves), marker row excluded from the top 2 even
        # though its settlement_date is the most recent.
        rows = [
            (0.23, 12823, "2026-07-15", 1.00, 91930),
            (0.73, 40968, "2026-06-30", 1.00, 668475),
        ]
        loader = _make_loader(monkeypatch, rows)

        result = loader.fetch_incremental("GV", since=None)[0]

        assert result["short_interest_pct"] == 0.23
        assert result["short_interest_pct_unavailable_reason"] is None
        assert result["shares_short_prior_month"] == 40968
        assert result["short_interest_pct_change"] is not None

    def test_symbol_with_only_a_marker_row_still_reports_missing(self, monkeypatch):
        # Control: a symbol with genuinely no real data ever must still report missing -
        # the fix must not fabricate data for symbols that truly have none.
        rows = [(None, None, "2026-07-31", None, None)]
        loader = _make_loader(monkeypatch, rows)

        result = loader.fetch_incremental("NEVERSHORTED", since=None)[0]

        assert result["short_interest_pct"] is None
        assert result["short_interest_pct_unavailable_reason"] == "missing_finra_data"
