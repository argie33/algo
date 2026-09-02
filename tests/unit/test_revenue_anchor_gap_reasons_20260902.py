"""Regression test: ps_ratio/ev_revenue_unavailable_reason must distinguish two more genuine
revenue-anchor-selection cases from generic "missing_sec_data", found live while tracing the
residual left after the negative_enterprise_value/zero_revenue_reported_this_period fixes:

1. _get_never_tagged_revenue_symbols() - full-history sibling of the windowed
   _get_no_recent_revenue_symbols() gate (same recent-IPO/thin-history blind spot fixed
   elsewhere in this file) - reuses the existing "no_revenue_reported" reason since it's the
   identical underlying fact, just a broader detection window. 44/98 residual rows.
2. _get_revenue_absent_from_anchor_year_symbols() - the anchor fiscal year's revenue is NULL
   (never tagged that year) even though a real, nonzero revenue exists in an earlier year -
   new reason "revenue_absent_from_anchor_year". Deliberately does NOT compute ev_revenue/
   ps_ratio from that older figure (would be a misleading value, not just a label fix).
   54/98 residual rows.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RecordingCursor:
    """Distinguishes the 4 revenue-gate queries by their distinctive SQL shape:
    - windowed no_recent_revenue: has ROW_NUMBER()
    - never_tagged_revenue: plain GROUP BY/HAVING, no ROW_NUMBER()/DISTINCT ON
    - zero_revenue_anchor: DISTINCT ON ... WHERE revenue = 0
    - revenue_absent_from_anchor_year: DISTINCT ON ... WHERE anchor.revenue IS NULL
    """

    def __init__(self, never_tagged_revenue=frozenset(), revenue_absent_from_anchor=frozenset()):
        self._never_tagged_revenue = never_tagged_revenue
        self._revenue_absent_from_anchor = revenue_absent_from_anchor
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "DISTINCT ON" in q and "anchor.revenue IS NULL" in q:
            return [(s,) for s in self._revenue_absent_from_anchor]
        if "DISTINCT ON" in q and "revenue = 0" in q:
            return []
        if "annual_income_statement" in q and "GROUP BY symbol" in q:
            return [(s,) for s in self._never_tagged_revenue]
        return []


def _run(monkeypatch, never_tagged_revenue=frozenset(), revenue_absent_from_anchor=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor(never_tagged_revenue, revenue_absent_from_anchor)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("REVGAP", _FakeSecValRow(sec_val_fields))


_BASE_FIELDS = {
    "pe_ratio": 15.0,
    "pb_ratio": 2.0,
    "ps_ratio": None,
    "ev_revenue": None,
    "ev_ebitda": 12.0,
    "ebitda": 5_000_000.0,
    "enterprise_value": 200_000_000.0,
    "market_cap": 180_000_000.0,
    "total_debt": 30_000_000.0,
    "total_cash": 10_000_000.0,
    "fcf_yield": 6.0,
}


class TestRevenueAnchorGapReasons:
    def test_never_tagged_revenue_gets_no_revenue_reported(self, monkeypatch):
        result = _run(monkeypatch, never_tagged_revenue=frozenset({"REVGAP"}), **_BASE_FIELDS)

        assert result["ev_revenue_unavailable_reason"] == "no_revenue_reported"
        assert result["ps_ratio_unavailable_reason"] == "no_revenue_reported"

    def test_revenue_absent_from_anchor_year_gets_own_reason(self, monkeypatch):
        result = _run(monkeypatch, revenue_absent_from_anchor=frozenset({"REVGAP"}), **_BASE_FIELDS)

        assert result["ev_revenue_unavailable_reason"] == "revenue_absent_from_anchor_year"
        assert result["ps_ratio_unavailable_reason"] == "revenue_absent_from_anchor_year"
        # Label-only: no ratio was fabricated from the stale prior-year revenue.
        assert result["ev_revenue"] is None
        assert result["ps_ratio"] is None

    def test_symbol_not_in_either_gate_keeps_generic_reason(self, monkeypatch):
        result = _run(monkeypatch, **_BASE_FIELDS)

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ps_ratio_unavailable_reason"] == "missing_sec_data"
