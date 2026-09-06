"""Regression test: fetch_incremental()'s primary quality_row anchor query used to filter
`WHERE abs.data_unavailable = FALSE`, requiring at least one real (non-unavailable) balance
sheet row to return ANYTHING at all for a symbol.

Found 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit) - same "invisible to
the whole query, not just one field" bug class as vqg_symbol_gates.py's never-tagged gates
(see test_never_tagged_gates_all_unavailable_history_20260905.py), just at this anchor query's
own top level, with much higher blast radius: a symbol whose ENTIRE annual_balance_sheet
history is marked data_unavailable (SUPV/TV live-confirmed: real fiscal-year rows on file,
every one explicitly unavailable, not "never filed") returned zero rows here, tripping the
blanket `_unavailable_marker` early-return for the WHOLE quality_metrics row - every one of its
~40 *_unavailable_reason columns stamped the generic "missing_sec_data" instead of reaching the
specific per-field gates (no_revenue_reported/no_recent_total_assets_reported/etc) that already
exist and already handle a None field correctly. Live-verified: SUPV/TV went from
data_unavailable=True/reason="missing_sec_data" (blanket) to a real per-field breakdown
(asset_turnover="no_revenue_reported", roa="no_recent_total_assets_reported") post-fix.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def test_primary_row_query_does_not_require_a_non_unavailable_balance_sheet_row(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("SUPV", None)

    primary_query = next(q for q in cursor.queries if "FROM annual_balance_sheet abs" in q)
    # The query has several correlated-subquery WHERE clauses before the main one - anchor on
    # the main table's own filter specifically.
    where_clause = primary_query.split("WHERE abs.symbol", 1)[1].split("ORDER BY", 1)[0]

    assert "abs.fiscal_year > 0" in where_clause, (
        "primary anchor query must filter on fiscal_year, not data_unavailable, so a symbol "
        "whose entire balance-sheet history is marked unavailable still gets a row (with NULL "
        "fields) instead of vanishing into the blanket unavailable_marker for every field."
    )
    assert "abs.data_unavailable = FALSE" not in where_clause
