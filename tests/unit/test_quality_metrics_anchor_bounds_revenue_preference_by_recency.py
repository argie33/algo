"""Regression test for the 2026-08-19 fix ("no SEC data"/missing factor inputs audit): the
primary quality_row anchor query's revenue/matched-income tiers (added 2026-08-17 and
2026-08-10 respectively - see test_quality_metrics_anchor_prefers_revenue_over_partial_income_
statement.py and test_quality_metrics_year_selection_prefers_usable_income_statement.py) had
no recency floor, the same bug class the FCF tier was bounded against on 2026-08-03 (see that
fix's comment in the loader). "Has revenue" or "income join matched" outranked "is recent"
with zero limit, so a technically non-NULL revenue value from years ago (often literally $0
for a pre-revenue clinical-stage biotech) could beat a fresh, complete balance sheet.

Live-confirmed against the real DB: 98 of the 100 symbols hitting quality_metrics'
stale_fiscal_data gate actually have a real, complete balance sheet within
MAX_FISCAL_YEAR_AGE_YEARS (e.g. ACHV has real FY2026 stockholders_equity/total_assets), but
the anchor query picked FY2019 instead purely because FY2019's income statement had
revenue=$0.00 (not NULL) while FY2020-FY2026 have NULL revenue (a real, non-buggy fact for a
pre-revenue biotech) - "has revenue" won with no floor, wrongly discarding 7 years of fresher
balance-sheet data and tripping stale_fiscal_data despite fresh data sitting right there.

Fixed by making "is this fiscal year within the staleness window" the PRIMARY sort key, with
the existing revenue/matched-income preference applied only as a tiebreak within the fresh
tier and, separately, within the stale tier (preserved unchanged as a fallback for genuinely-
stale filers with no fresh balance sheet at all).
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


def test_primary_row_query_bounds_revenue_and_usability_tiers_by_recency(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("ACHV", None)

    primary_query = next(q for q in cursor.queries if "FROM annual_balance_sheet abs" in q)
    order_by_clause = primary_query.split("ORDER BY", 1)[1]
    first_case = order_by_clause.split("(CASE", 2)[1]  # the tiering CASE, not the FCF one

    fresh_bound = "EXTRACT(YEAR FROM CURRENT_DATE)::int -"
    revenue_pos = first_case.find("ais.revenue IS NOT NULL")
    usability_pos = first_case.find("ais.symbol IS NOT NULL")
    unbounded_revenue_pos = first_case.find("ais.revenue IS NOT NULL", usability_pos + 1)
    unbounded_usability_pos = first_case.find("ais.symbol IS NOT NULL", unbounded_revenue_pos + 1)

    assert revenue_pos != -1 and usability_pos != -1
    # A bounded (recency-checked) revenue/usability tier must exist ahead of any unbounded one.
    assert fresh_bound in first_case[: usability_pos + 1], (
        "the revenue/usability tiers must be bounded by the same staleness window as the "
        "stale_fiscal_data gate, not preferred unconditionally regardless of recency"
    )
    # An unbounded fallback tier (no recency check) must still exist, ranked AFTER the bounded
    # ones, so a genuinely-stale filer with no fresh balance sheet at all still gets a sensible
    # anchor (prefer real revenue among its old years) rather than picking nothing.
    assert unbounded_revenue_pos != -1 and unbounded_usability_pos != -1
    assert revenue_pos < usability_pos < unbounded_revenue_pos < unbounded_usability_pos
