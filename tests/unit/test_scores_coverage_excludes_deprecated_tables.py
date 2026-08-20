"""Regression test for the 2026-08-19 fix (goal session continuation - "which factor inputs
are missing the most" audit): /api/algo/scores/coverage reported yfinance_snapshot's
unavailable_reason gaps (2,146 active-symbol rows, 45.8% of the table) as if they were a real,
actionable loader gap. They aren't: yfinance_snapshot has had no active loader since Session
275 (see load_value_quality_growth_metrics.py's and load_positioning_metrics.py's own
"yfinance_snapshot is deprecated" comments) - nothing writes to it anymore, so no loader fix can
ever change this number. The report now excludes any table with no entry in
loaders/loader_registry.py's LOADER_TABLES/PSEUDO_LOADER_TABLES (the canonical active-loader-
output mapping), so a deprecated table's frozen gaps can't masquerade as a live one again.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


class _FakeCursor:
    """Minimal cursor returning one deprecated table (yfinance_snapshot, no active loader)
    and one real, currently-loaded table (dividend_data, IS in the registry) - both match
    the "%unavailable_reason%" column-name scan, so only the registry check should tell
    them apart."""

    def __init__(self):
        self.queries: list[str] = []
        self._last_query = ""

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "SELECT table_name, column_name" in q and "'reason'" not in q:
            return [
                ("yfinance_snapshot", "unavailable_reason"),
                ("dividend_data", "data_unavailable_reason"),
            ]
        if "column_name = 'reason'" in q:
            return []  # no bare-"reason" tables in this fake scan
        if "information_schema.columns" in q and "IN ('symbol','date'" in q:
            return [("symbol",), ("updated_at",)]
        if "dividend_data" in q and "reason_val" in q:
            return [("no_dividend_xbrl_concepts", 42)]
        return []

    def fetchone(self):
        return (100,)


def test_deprecated_table_with_no_active_loader_is_excluded():
    cursor = _FakeCursor()
    resp = scores_mod._get_scores_coverage(cursor)
    assert resp["statusCode"] == 200

    body = resp["data"]
    factor_names = [f["factor"] for f in body["factors"]]
    assert "dividend_data" in factor_names
    assert "yfinance_snapshot" not in factor_names

    # Confirms exclusion happens before any per-table query is even issued, not just
    # filtered out of the final response.
    assert not any("yfinance_snapshot" in q for q in cursor.queries[1:])
