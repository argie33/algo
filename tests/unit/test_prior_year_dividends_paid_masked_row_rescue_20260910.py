"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): fetch_incremental()'s
prior_year_dividends_paid subquery filtered `annual_cash_flow.data_unavailable = FALSE`, unlike
vqg_quality_inputs.py's same-year dividends_paid rescue (2026-08-18 fix) which already
recognizes that a whole-row `data_unavailable` flag (e.g. "incomplete_sec_filing_cashflow" from
a missing operating_cash_flow) doesn't mean dividends_paid itself is bad - it filters on
`dividends_paid IS NOT NULL` instead.

Live-confirmed DB (Deutsche Bank): FY-1's annual_cash_flow row is data_unavailable=TRUE
(incomplete_sec_filing_cashflow) but carries a real dividends_paid figure. Because the prior-
year subquery filtered on data_unavailable=FALSE, that real, one-year-old value was discarded
even though net_income was real and current, so payout_ratio/sustainable_growth_rate fell to
"missing_sec_data" instead of using it - same "masked-but-present" bug class as the same-year
rescue, just never applied to the prior-year lookup.
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


def test_prior_year_dividends_paid_subquery_ignores_whole_row_data_unavailable_flag(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("DB", None)

    primary_query = next(q for q in cursor.queries if "FROM annual_balance_sheet abs" in q)
    prior_year_dividends_subquery = primary_query.split("as prior_year_dividends_paid")[0].rsplit(
        "WHERE symbol = %s AND fiscal_year = abs.fiscal_year - 1", 1
    )[1]

    assert "data_unavailable" not in prior_year_dividends_subquery, (
        "prior_year_dividends_paid must not filter on the whole annual_cash_flow row's "
        "data_unavailable flag - a masked-but-present dividends_paid value must still be usable"
    )
    assert "dividends_paid IS NOT NULL" in prior_year_dividends_subquery
