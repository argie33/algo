"""Regression test for the 2026-08-19 fix ("no SEC data"/missing factor inputs audit):
/api/algo/scores/coverage's per-factor queries scanned each metrics table directly with no
active-universe filter, so a symbol delisted/failed-SPAC/dropped from stock_symbols.active but
never pruned from a metrics table counted as a live "gap in the real, scored universe."

Live-confirmed against the real DB: 6-9% of rows in quality_metrics/growth_metrics/
value_metrics/positioning_metrics/stability_metrics/dividend_data belong to inactive symbols,
and inactive symbols are disproportionately gap-heavy (delisted shells, failed SPACs) - not
proportional noise. The real user-facing /api/algo/scores query already joins
stock_scores -> stock_symbols (stock_scores itself is 99.7% clean of inactive symbols), so this
coverage report was measuring a different, larger, stale-inflated population than what real
users ever see. Re-running the fixed report against the live DB dropped total reported gaps by
tens of thousands (e.g. "Insufficient history" 34,937 -> 23,879, "Missing SEC/XBRL data"
29,739 -> 16,583) purely from this measurement correction, no data actually changed.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


class _FakeCursor:
    """Minimal cursor simulating one fake metrics table with a symbol+date reason column."""

    def __init__(self):
        self.queries: list[str] = []
        self._last_query = ""

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last_query = query
        self._last_params = params

    def fetchall(self):
        q = self._last_query
        # The reason-columns query filters on "%unavailable_reason%" via a %s parameter,
        # not a literal in the query text - match on its distinctive SELECT list instead.
        if "SELECT table_name, column_name" in q:
            return [("fake_metrics", "widget_unavailable_reason")]
        if "information_schema.columns" in q and "IN ('symbol','date'" in q:
            return [("symbol",), ("date",)]
        return []

    def fetchone(self):
        return (100,)


def test_per_table_queries_join_and_filter_to_active_symbols():
    cursor = _FakeCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200

    per_table_queries = [q for q in cursor.queries if "fake_metrics" in q]
    assert per_table_queries, "expected at least the denom-count and latest-row queries for fake_metrics"

    for q in per_table_queries:
        assert "JOIN stock_symbols" in q, f"query missing active-universe join: {q}"
        assert "active = true" in q, f"query missing active=true filter: {q}"


def test_bare_reason_allowlisted_tables_are_included():
    """FIXED 2026-08-19 (same-day follow-up): the "%unavailable_reason%" name match misses
    every table whose gap-reason column is just called "reason" - live-confirmed a real,
    separate blind spot (not overlap with the fix above): institutional_holdings_13f,
    insider_holdings_sec, analyst_earnings_estimates, sec_segment_info/metrics,
    short_interest_finra, and sec_valuations are genuine per-symbol data sources with a
    real, populated "reason" column that were 100% invisible to this report - e.g.
    sec_segment_metrics alone had 2,067 of 5,546 rows (37%) unavailable with specific real
    reasons, never surfaced anywhere in the coverage report before this fix."""

    class _BareReasonCursor(_FakeCursor):
        def fetchall(self):
            q = self._last_query
            if "SELECT table_name, column_name" in q and "'reason'" not in q:
                return []  # no *_unavailable_reason columns in this fake schema
            if "column_name = 'reason'" in q:
                return [("sec_segment_metrics", "reason")]
            if "information_schema.columns" in q and "IN ('symbol','date'" in q:
                return [("symbol",), ("updated_at",)]
            if "sec_segment_metrics" in q and "reason_val" in q:
                return [("no_segment_disclosure", 42)]
            return []

    cursor = _BareReasonCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200

    segment_queries = [q for q in cursor.queries if "sec_segment_metrics" in q]
    assert segment_queries, "sec_segment_metrics's bare 'reason' column must be scanned"
    for q in segment_queries:
        if "SELECT" in q and "COUNT" in q:
            assert "JOIN stock_symbols" in q, f"bare-reason query missing active-universe join: {q}"

    body = resp["data"]
    factor_names = [f["factor"] for f in body["factors"]]
    # A bare "reason" column doesn't match the unavailable_reason-suffix regex, so its
    # factor name must fall back to the table name, not the unhelpful literal "reason".
    assert "sec_segment_metrics" in factor_names
    assert "reason" not in factor_names


def test_self_join_against_stock_symbols_itself_does_not_error(monkeypatch):
    """stock_symbols has its own data_unavailable_reason column, so the active-universe
    join must alias the joined copy distinctly from the table being scanned (self-join) -
    a naive unqualified column reference here would be ambiguous and error at the DB."""

    class _StockSymbolsCursor(_FakeCursor):
        def fetchall(self):
            q = self._last_query
            if "SELECT table_name, column_name" in q:
                return [("stock_symbols", "data_unavailable_reason")]
            if "information_schema.columns" in q and "IN ('symbol','date'" in q:
                # stock_symbols has updated_at/created_at like most tables - the exact
                # ambiguity trap this test guards against.
                return [("symbol",), ("updated_at",), ("created_at",)]
            return []

    cursor = _StockSymbolsCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200

    per_table_queries = [q for q in cursor.queries if "stock_symbols" in q and "unavailable_reason" not in q]
    for q in per_table_queries:
        if "JOIN stock_symbols _su" in q:
            # Both the scanned table and the join target are stock_symbols - every
            # ordering/reason column reference must be qualified to the scanned table's
            # own (unaliased) name, never bare, to avoid ambiguity against `_su`.
            assert "stock_symbols.symbol" in q
