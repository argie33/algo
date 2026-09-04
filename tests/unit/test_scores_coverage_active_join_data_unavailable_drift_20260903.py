"""Regression test: the coverage report's active-universe join must also exclude symbols
flagged stock_symbols.data_unavailable = TRUE, matching utils/loaders/helpers.py's canonical
get_active_symbols(exclude_etfs=True) filter (the real population every scoring loader uses).

Found live 2026-09-03 (SEC/XBRL missing-data sweep, drift check against the canonical filter
after the 2026-09-03 CEF/BDC/ETN entity-type fix landed): the canonical filter requires BOTH
`active = true` AND `data_unavailable IS NOT TRUE` as sibling conditions - a symbol can be
active=true in the roster yet separately, permanently flagged data_unavailable (e.g. after a
confirmed-dead-data investigation) - but this report's `active_join` only ever carried
`active = true`, never the second condition. Live-confirmed 3 universe symbols (ISSC/BNRG/AVB)
currently match active=true+data_unavailable=true and none currently contribute a live
missing_sec_data row (zero headline impact today), but it's the same "measuring a population
nobody actually scores" bug class as the listing-status and entity-type fixes already landed
for this exact join, and would silently reopen the moment any such symbol picks up a real gap.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


class _FakeCursor:
    def __init__(self):
        self.queries: list[str] = []
        self._last_query = ""

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last_query = query
        self._last_params = params

    def fetchall(self):
        q = self._last_query
        if "SELECT table_name, column_name" in q:
            return [("fake_metrics", "widget_unavailable_reason")]
        if "information_schema.columns" in q and "IN ('symbol','date'" in q:
            return [("symbol",), ("date",)]
        return []

    def fetchone(self):
        return (100,)


def test_active_join_also_excludes_data_unavailable_symbols():
    cursor = _FakeCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200

    per_table_queries = [q for q in cursor.queries if "fake_metrics" in q and not q.strip().startswith("SELECT count(")]
    assert per_table_queries, "expected at least the denom-count and latest-row queries for fake_metrics"

    for q in per_table_queries:
        assert "JOIN stock_symbols" in q, f"query missing active-universe join: {q}"
        assert "active = true" in q, f"query missing active=true filter: {q}"
        assert "data_unavailable IS NOT TRUE" in q, (
            f"query joins on active=true but not the sibling data_unavailable exclusion "
            f"the canonical get_active_symbols(exclude_etfs=True) filter also requires: {q}"
        )
