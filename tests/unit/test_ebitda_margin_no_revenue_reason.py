"""Regression test: ebitda_margin_unavailable_reason must distinguish a structurally
pre-revenue company (no revenue reported in its 3 most recent fiscal years - typically a SPAC
or clinical-stage biotech) from a real SEC extraction gap.

Found live 2026-08-18 (goal: "no SEC data" audit): ebitda_margin = ebitda / revenue has no
fallback denominator (unlike operating_margin, which falls back to total_assets when revenue is
unavailable) - live-confirmed 511 universe symbols with a real, computed ebitda but
ebitda_margin "missing_sec_data". Of those, 69 have genuinely never reported revenue in their 3
most recent fiscal years (dominated by SPACs and pre-revenue biotech, e.g. ABVX/Abivax) - the
remaining ~440 have real revenue on file in a different fiscal year than quality_row's
balance-sheet anchor selected (e.g. AFYA/AIB/AKTS), a distinct fiscal-year-anchor gap
deliberately NOT covered here (still correctly reports the generic "missing_sec_data", which is
accurate for that case). Same "3 most recent years, not all-time history" windowing as the
total_debt_not_itemized / interest_expense_not_itemized fixes.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(revenue=None):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 500_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_revenue_symbols):
        self._no_recent_revenue = no_recent_revenue_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_income_statement" in self._last_query and "revenue" in self._last_query:
            return [(s,) for s in self._no_recent_revenue]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_revenue_symbols=frozenset()):
        self._no_recent_revenue = no_recent_revenue_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_revenue)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_revenue_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEbitdaMarginNoRevenueReason:
    def test_symbol_with_no_recent_revenue_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"ABVX"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("ABVX", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda"] == -5_000_000.0
        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_not_in_no_recent_set_keeps_generic_reason(self, monkeypatch):
        # revenue is None for this fiscal year, but the symbol has revenue on file in a
        # different fiscal year (anchor-selection gap) - must stay "missing_sec_data".
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"ABVX"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("AFYA", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "missing_sec_data"

    def test_real_revenue_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"ABVX"}))
        row = _quality_row(revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("ABVX", row, ev_metrics=(None, None, 20_000_000.0))

        assert metrics["ebitda_margin"] == 20.0
        assert metrics.get("ebitda_margin_unavailable_reason") is None
