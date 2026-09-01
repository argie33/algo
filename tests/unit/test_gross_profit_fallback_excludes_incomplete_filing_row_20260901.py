"""Regression test (2026-09-01, /goal data-gap audit): the gross_profit/cost_of_revenue
fallback query in `_compute_quality_metrics` (feeds both gross_margin and, via
gross_profit_used, gross_profitability) was missing the `data_unavailable IS NOT TRUE` filter -
a different, more serious variant of the same root pattern already found in
pe/peg/pb_ratio_unavailable_reason (see memory/peg_pb_ratio_unavailable_reason_same_bug_class_
fixed_20260901.md): here it's the VALUE itself that was wrong, not just a reason label, because
this fallback query IS the primary computation path (no separate authoritative source exists to
disagree with).

Live-confirmed 2026-09-01: 258 symbols have their most-recent usable
gross_profit/cost_of_revenue row flagged data_unavailable=True with a stray non-NULL figure -
and that stub figure is systematically much smaller than the real complete fiscal year's
figure (a partial/incomplete filing naturally under-reports vs a full year), e.g. ABNB $2.097B
(incomplete FY2026 stub) vs real FY2025 $10.155B, AOS $753.5M vs real $1.4874B, ANGI $228.457M
vs real $983.099M - gross_margin/gross_profitability was materially UNDERSTATED for all of them.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _RecordingCursor:
    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row
        self.gross_profit_queries = []
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        if "SELECT gross_profit, cost_of_revenue, revenue" in query:
            self.gross_profit_queries.append(query)

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT gross_profit, cost_of_revenue, revenue" in self._last_query:
            return self._fallback_row
        return None


class _RecordingDatabaseContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, cursor):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _RecordingDatabaseContext(cursor))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(gross_profit=None, cost_of_revenue=None, revenue=None):
    # Same 34-column shape as test_gross_profitability_fallback_and_reason_20260831.py's fixture.
    return (
        None,
        200_000_000.0,
        700_000_000.0,
        50_000_000.0,
        revenue,
        None,
        150_000_000.0,
        100_000_000.0,
        2025,
        None,
        None,
        None,
        cost_of_revenue,
        None,
        None,
        None,
        None,
        None,
        None,
        gross_profit,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


class TestGrossProfitFallbackQueryFiltersDataUnavailable:
    def test_both_fallback_queries_filter_on_data_unavailable(self, monkeypatch):
        """The fix itself: both the 3-year-window and full-history fallback queries must
        exclude incomplete filing rows, not just rely on a mock returning the "right" row."""
        cursor = _RecordingCursor(fallback_row=None)  # forces both queries to run
        loader = _make_loader(monkeypatch, cursor)
        row = _quality_row()

        loader._compute_quality_metrics("NOFALLBACK", row, ev_metrics=None)

        assert len(cursor.gross_profit_queries) == 2
        for query in cursor.gross_profit_queries:
            assert "data_unavailable IS NOT TRUE" in query

    def test_incomplete_recent_stub_no_longer_understates_gross_profitability(self, monkeypatch):
        """ABNB-shaped case (proportionally scaled to this fixture's $700M total_assets to
        stay within the plausible-ratio bound): a correctly-filtered query skips an incomplete
        current-FY stub and returns the real, complete prior year's larger gross_profit
        instead - here 5x the stub's magnitude, same ratio as the real ABNB stub-vs-real gap
        ($2.097B incomplete stub vs $10.155B real complete year)."""
        # Simulates what the DB returns AFTER the filter: the real complete-year figure.
        cursor = _RecordingCursor(fallback_row=(350_000_000.0, None, None))
        loader = _make_loader(monkeypatch, cursor)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("ABNB", row, ev_metrics=None)

        assert metrics["gross_profitability"] == 350_000_000.0 / 700_000_000.0 * 100.0
