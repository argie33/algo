"""Regression test for the 2026-08-17 fix ("no SEC data"/loader audit goal): the primary
quality_row anchor query's usability tier only checked ais.symbol IS NOT NULL (the join
matched), not whether the matched row actually had revenue.

Live-confirmed on AMZN: annual_income_statement's FY2026 row has data_unavailable=FALSE and
a real net_income ($135.281B) but NULL revenue/operating_income/cost_of_revenue/gross_profit
(a partial/interim fact set - passes load_financial_statements.py's transform() because its
required-metrics check only demands ONE of {revenue, net_income}). This row ranked ahead of
the complete FY2025 row under the old 2-tier CASE (both satisfy "ais.symbol IS NOT NULL"),
so operating_margin failed outright (no revenue) and net_margin silently fell into the
bank/no-revenue fallback (net_income / total_assets), returning a real-looking but WRONG
percentage instead of the correct revenue-based one - worse than "missing_sec_data", a
plausible wrong number with no unavailable_reason to flag it.

Fixed by adding a higher-priority ORDER BY tier that prefers fiscal years where the matched
annual_income_statement row also has real revenue, ahead of the mere-join-matched tier.
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


def test_primary_row_query_prioritizes_real_revenue_over_bare_join_match(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("AMZN", None)

    primary_query = next(q for q in cursor.queries if "FROM annual_balance_sheet abs" in q)
    order_by_clause = primary_query.split("ORDER BY", 1)[1]

    revenue_pos = order_by_clause.find("ais.revenue IS NOT NULL")
    usability_pos = order_by_clause.find("ais.symbol IS NOT NULL")
    fcf_pos = order_by_clause.find("acf.free_cash_flow IS NOT NULL")

    assert revenue_pos != -1, "ORDER BY must prefer years where the matched income statement has real revenue"
    assert usability_pos != -1
    assert fcf_pos != -1
    assert revenue_pos < usability_pos, (
        "a fiscal year with real revenue must outrank a merely-joined (possibly partial) one"
    )
    assert usability_pos < fcf_pos, "income-statement usability must still outrank the FCF-recency tiebreaker"
