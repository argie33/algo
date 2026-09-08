"""Regression test for the 2026-08-10 fix: fetch_incremental()'s primary quality_row query
picked the fiscal year purely by balance-sheet recency (with an FCF-availability tiebreaker),
with zero regard for whether that same year's income statement was actually usable.

Live-confirmed on BFS: annual_balance_sheet has a real FY2026 row (data_unavailable=FALSE),
but annual_income_statement's FY2026 row is data_unavailable=TRUE
('incomplete_sec_filing_income'). Since the LEFT JOIN to annual_income_statement requires
`ais.data_unavailable = FALSE` in its ON clause, picking FY2026 as the anchor year silently
nulled out net_income/operating_income/revenue for the whole row - even though FY2023-FY2025
all have complete, real income statements. roe/roa/operating_margin/net_margin/
revenue_growth_yoy/earnings_growth_yoy all came back "missing_sec_data" as a result, despite
the data existing one query away. A universe-wide DB audit found 347 symbols hit this exact
pattern (latest usable balance-sheet fiscal year has no matching usable income statement, but
an earlier year does).

Fixed by adding a higher-priority ORDER BY tier that prefers fiscal years where the
annual_income_statement join actually matched (ais.symbol IS NOT NULL), ahead of the existing
FCF-recency tiebreaker.

NOTE (2026-09-07): the FCF-recency tiebreaker referenced above has since been removed entirely -
see [[anchor_year_fcf_tiebreak_masked_profit_loss_flips_20260907]] in memory. It let a year with
FCF tagged win anchor selection over a more recent year without FCF tagged yet, regardless of
actual recency (live-confirmed PHOE: masked a genuine profit-to-loss flip). This test now checks
that fiscal_year DESC, not an FCF check, is the tiebreak after income-statement usability.
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


def test_primary_row_query_prioritizes_usable_income_statement_over_bare_recency(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    loader.fetch_incremental("BFS", None)

    primary_query = next(q for q in cursor.queries if "FROM annual_balance_sheet abs" in q)

    # The income-statement-usability tier must be checked, and it must be the FIRST ORDER BY
    # key - ahead of the bare fiscal_year DESC fallback - so a year with no usable income
    # statement is never preferred over one that has it.
    order_by_clause = primary_query.split("ORDER BY", 1)[1]
    usability_pos = order_by_clause.find("ais.symbol IS NOT NULL")
    fiscal_year_pos = order_by_clause.find("abs.fiscal_year DESC")
    assert usability_pos != -1, "ORDER BY must prefer years where the income statement join matched"
    assert fiscal_year_pos != -1, "fiscal_year recency must remain the final tiebreak"
    assert usability_pos < fiscal_year_pos, "income-statement usability must outrank plain recency"
    assert "acf.free_cash_flow IS NOT NULL" not in order_by_clause, (
        "the FCF-recency tiebreaker must be GONE, not reordered - it let FCF-tagged-but-older "
        "years win over fresher, FCF-untagged years, masking real profit/loss flips (see "
        "anchor_year_fcf_tiebreak_masked_profit_loss_flips_20260907 in memory)"
    )
