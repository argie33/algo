"""Regression test for the 2026-08-21 goal ("include the sources - SEC/yfinance/FRED/etc -
and the % from each, for every input tracked on the Scores Data Coverage tab, alongside the
existing issues breakdown"): /api/algo/scores/coverage now also reads each table's own
`data_source` (and, where present, `source_tracking`) column and attaches a per-factor
source breakdown, plus a table-wide rollup in `summary`.

Follows the same fake-cursor convention as test_scores_coverage_active_universe_scoping.py:
the fake `fetchall()` dispatches on distinctive substrings of the last-executed query text,
and (as documented there) a table only reaches the per-table loop via the "bare reason"
allowlist extend path here, since the fake cursor doesn't distinguish it from the initial
`%unavailable_reason%` scan - that's a fake-cursor quirk, not something this test relies on
for its actual assertions.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


class _DataSourceCursor:
    """One fake table with both a `data_source` column and *_unavailable_reason column."""

    def __init__(self):
        self.queries: list[str] = []
        self._last_query = ""

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "SELECT table_name, column_name" in q:
            return [("fake_metrics", "widget_unavailable_reason")]
        if "information_schema.columns" in q and "IN ('symbol','date'" in q:
            return [("symbol",), ("date",), ("data_source",)]
        if "data_source AS source_val" in q:
            return [("sec_audited", 80), ("yfinance_api", 20)]
        if "widget_unavailable_reason AS reason_val" in q:
            return [("missing_sec_data", 10)]
        return []

    def fetchone(self):
        return (100,)


def test_factor_gets_data_source_breakdown_and_summary_rollup():
    cursor = _DataSourceCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200
    body = resp["data"]

    factors = body["factors"]
    assert len(factors) == 1
    f = factors[0]
    assert f["sources"] == [
        {"source": "sec_audited", "label": "SEC (audited financials)", "count": 80, "pct": 80.0},
        {"source": "yfinance_api", "label": "Yahoo Finance", "count": 20, "pct": 20.0},
    ]

    # FIXED 2026-08-23: summary rollup is keyed by human label, not raw data_source string -
    # see test_summary_source_rollup_merges_same_label_across_tables below for why.
    summary = body["summary"]
    assert summary["source_totals"] == {"SEC (audited financials)": 80, "Yahoo Finance": 20}
    assert summary["source_order"] == ["SEC (audited financials)", "Yahoo Finance"]
    assert summary["source_labels"]["SEC (audited financials)"] == "SEC (audited financials)"
    assert summary["source_labels"]["Yahoo Finance"] == "Yahoo Finance"


def test_table_without_data_source_column_reports_no_sources():
    """A table with no data_source/source_tracking column at all (most of the schema) must
    not error and must report sources=None rather than fabricating a breakdown."""

    class _NoSourceColumnCursor(_DataSourceCursor):
        def fetchall(self):
            q = self._last_query
            if "information_schema.columns" in q and "IN ('symbol','date'" in q:
                return [("symbol",), ("date",)]  # no data_source, no source_tracking
            return super().fetchall()

    cursor = _NoSourceColumnCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200
    body = resp["data"]

    assert body["factors"][0]["sources"] is None
    assert body["summary"]["source_totals"] == {}
    assert body["summary"]["source_order"] == []
    for q in cursor.queries:
        assert "data_source AS source_val" not in q


def test_source_tracking_per_field_breakdown_wins_over_table_wide_data_source():
    """positioning_metrics-style table: a factor whose name matches a source_tracking key
    (e.g. short_interest_pct <-> the "short_interest" key) must get that field's own
    finra/sec_13f/unavailable split, not the row's single table-wide primary `data_source`."""

    class _SourceTrackingCursor(_DataSourceCursor):
        def fetchall(self):
            q = self._last_query
            if "SELECT table_name, column_name" in q:
                return [("fake_positioning", "short_interest_pct_unavailable_reason")]
            if "information_schema.columns" in q and "IN ('symbol','date'" in q:
                return [("symbol",), ("date",), ("data_source",), ("source_tracking",)]
            if "data_source AS source_val" in q:
                # Table-wide primary source - must NOT be what short_interest_pct shows below.
                return [("sec_13f", 100)]
            if "kv.field_key" in q:
                return [
                    ("short_interest", "finra", 70),
                    ("short_interest", "unavailable", 30),
                    ("institutional", "sec_13f", 100),
                ]
            if "short_interest_pct_unavailable_reason AS reason_val" in q:
                return [("no_resolved_13f_holdings", 5)]
            return []

    cursor = _SourceTrackingCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200
    body = resp["data"]

    factors = {f["factor"]: f for f in body["factors"]}
    assert "short_interest_pct" in factors
    assert factors["short_interest_pct"]["sources"] == [
        {"source": "finra", "label": "FINRA", "count": 70, "pct": 70.0},
        {"source": "unavailable", "label": "Unavailable", "count": 30, "pct": 30.0},
    ]


def test_summary_source_rollup_merges_same_label_across_tables():
    """FIX 2026-08-23 (goal: data-source accuracy review): two tables can write different
    literal data_source strings ("finra" vs "finra_query_api") that _prettify_source() maps
    to the identical human label "FINRA". Before this fix, the summary rollup was keyed by
    the raw string, so the KPI chart/legend showed two separate same-labeled "FINRA" entries
    instead of one merged bar - exactly what a live /api/algo/scores/coverage pull surfaced
    (two "FINRA" rows, 5,192 and 4,918, instead of one ~10,110 row)."""

    class _TwoTablesSameLabelCursor(_DataSourceCursor):
        def fetchall(self):
            q = self._last_query
            if "SELECT table_name, column_name" in q:
                return [
                    ("fake_a", "a_unavailable_reason"),
                    ("fake_b", "b_unavailable_reason"),
                ]
            if "information_schema.columns" in q and "IN ('symbol','date'" in q:
                return [("symbol",), ("date",), ("data_source",)]
            if "data_source AS source_val" in q:
                if "fake_a" in q:
                    return [("finra", 60)]
                if "fake_b" in q:
                    return [("finra_query_api", 40)]
                return []
            if "a_unavailable_reason AS reason_val" in q:
                return [("missing_sec_data", 5)]
            if "b_unavailable_reason AS reason_val" in q:
                return [("missing_sec_data", 5)]
            return []

    cursor = _TwoTablesSameLabelCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200
    summary = resp["data"]["summary"]

    assert summary["source_totals"] == {"FINRA": 100}
    assert summary["source_order"] == ["FINRA"]
    assert summary["source_labels"] == {"FINRA": "FINRA"}
