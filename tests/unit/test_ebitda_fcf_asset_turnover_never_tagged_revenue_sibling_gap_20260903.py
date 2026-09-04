"""Regression test: ebitda_margin/fcf_margin/asset_turnover_unavailable_reason must also treat
a thin-filing-history symbol (fewer than 3 real fiscal years, never real revenue in any of them)
as "no_revenue_reported" - not just a symbol caught by the windowed 3-year
_get_no_recent_revenue_symbols() gate.

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction, sibling-left-behind bug class -
same shape as bf82fc6d0's total_debt fix): ps_ratio_unavailable_reason and
ev_revenue_unavailable_reason already OR in _get_never_tagged_revenue_symbols() (the full-history
sibling of _get_no_recent_revenue_symbols(), added 2026-09-02 specifically for this thin-history
blind spot) alongside the windowed gate, but ebitda_margin/fcf_margin/asset_turnover were left
off that OR when it was added to their siblings - live-confirmed 73 universe rows per field
(ebitda_margin, fcf_margin) fell through to generic "missing_sec_data" for symbols with a real,
short filing history that has genuinely never reported nonzero revenue.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(revenue=None, total_assets=700_000_000.0, free_cash_flow=None):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    """Distinguishes the windowed (ROW_NUMBER/rn<=3) query from the full-history
    (never-tagged) query - both hit annual_income_statement.revenue, but only the windowed
    one uses ROW_NUMBER."""

    def __init__(self, no_recent_revenue_symbols, never_tagged_revenue_symbols):
        self._no_recent_revenue = no_recent_revenue_symbols
        self._never_tagged_revenue = never_tagged_revenue_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "free_cash_flow" in q:
            # fcf_margin's own cross-year (free_cash_flow, revenue) fallback query - not the
            # symbol-list revenue gates below, which never select free_cash_flow.
            return []
        if "annual_income_statement" in q and "revenue" in q:
            if "ROW_NUMBER" in q:
                return [(s,) for s in self._no_recent_revenue]
            return [(s,) for s in self._never_tagged_revenue]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_revenue_symbols=frozenset(), never_tagged_revenue_symbols=frozenset()):
        self._no_recent_revenue = no_recent_revenue_symbols
        self._never_tagged_revenue = never_tagged_revenue_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_revenue, self._never_tagged_revenue)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset(), never_tagged_revenue_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(no_recent_revenue_symbols, never_tagged_revenue_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestNeverTaggedOnlySymbolGetsNoRevenueReason:
    """A symbol NOT in the windowed 3-year set but IS in the full-history never-tagged set
    (thin filing history) must still get "no_revenue_reported", not "missing_sec_data"."""

    def test_ebitda_margin(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("THIN", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "no_revenue_reported"

    def test_fcf_margin(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=None, free_cash_flow=None)

        metrics = loader._compute_quality_metrics("THIN", row, ev_metrics=(None, None, None))

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "no_revenue_reported"

    def test_asset_turnover(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=None, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("THIN", row, ev_metrics=(None, None, None))

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_in_neither_set_keeps_generic_reason(self, monkeypatch):
        # Sanity check: a symbol in neither the windowed nor never-tagged set (an
        # anchor-year-selection gap, not a genuine no-revenue case) stays "missing_sec_data".
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("OTHER", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda_margin_unavailable_reason"] == "missing_sec_data"
