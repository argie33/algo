"""Regression test for the 2026-08-19 fix ("no SEC data"/missing factor inputs audit): the
income_rows query backing _compute_growth_metrics() was capped at LIMIT 10, silently assuming
a company's 10 most recent annual_income_statement rows always contain enough usable (non-NULL,
non-zero revenue / nonzero EPS) data points for a 5-year CAGR - _compute_period_growth needs 6
(offset=5) for revenue_growth_5y/eps_growth_5y.

Live-confirmed via the real DB: OGEN has 8 real positive-revenue fiscal years across 2010-2023,
but 5 of its most recent 10 raw annual_income_statement rows are unusable (2025/2024/2020/2019/
2018 NULL revenue, 2017/2016/2015 = real $0 revenue) - only 3 usable points survive in a
LIMIT-10 window, wrongly reporting "insufficient_history" despite 8 real years on record two
rows away. A DB-wide check found 2,942 symbols (over half the universe) have MORE than 10 total
annual_income_statement rows, so this wasn't an edge case. Raised to 30 (real DB-wide max is 26
rows for any single symbol).
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


def test_income_rows_query_fetches_more_than_ten_years(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("OGEN", None)

    income_query = next(q for q in cursor.queries if "FROM annual_income_statement" in q and "abs.fiscal_year" not in q)
    limit_line = next(line for line in income_query.splitlines() if "LIMIT" in line)
    limit_value = int(limit_line.strip().split()[-1])

    assert limit_value >= 26, (
        "the income_rows fetch must cover the real DB-wide max annual-history length (26 rows) "
        "so gap-heavy filers (NULL/zero-revenue years mixed into recent history) aren't starved "
        "of real older data a tighter LIMIT would silently exclude"
    )
