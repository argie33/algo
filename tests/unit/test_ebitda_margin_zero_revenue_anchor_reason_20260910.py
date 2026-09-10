"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): ebitda_margin's reason
chain already checks _get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols() (a
NULL/never-tagged revenue), but never checked _get_zero_revenue_anchor_symbols() - the sibling
gate ev_revenue/ps_ratio already use (vqg_value.py, fixed 2026-09-02) for a real, REPORTED
$0.00 anchor-year revenue. A real $0 makes ebitda_margin's revenue denominator mathematically
undefined the same way, but since revenue isn't NULL, the no_revenue_reported gate above never
matches and it fell all the way to the generic "missing_sec_data".

Live-confirmed 11/16 ebitda_margin "missing_sec_data" rows (VTVT/BRNS/AMLX/ZNTL/FULC/NGNE/
MOLN/AZTR/CMPX/ALLO/SABS - all pre-revenue-in-that-year biotech) are this exact shape.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(revenue=None):
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
    def __init__(self, zero_revenue_anchor_symbols):
        self._zero_revenue_anchor = zero_revenue_anchor_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "free_cash_flow" in q:
            return []
        if "DISTINCT ON" in q and "annual_income_statement" in q:
            return [(s,) for s in self._zero_revenue_anchor]
        if "annual_income_statement" in q and "revenue" in q:
            # The windowed no-recent-revenue gate - always empty in this test, so only the
            # zero-revenue-anchor sibling can fire.
            return []
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, zero_revenue_anchor_symbols=frozenset()):
        self._zero_revenue_anchor = zero_revenue_anchor_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._zero_revenue_anchor)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, zero_revenue_anchor_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(zero_revenue_anchor_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEbitdaMarginZeroRevenueAnchorReason:
    def test_zero_revenue_anchor_symbol_gets_zero_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, zero_revenue_anchor_symbols=frozenset({"ZNTL"}))
        row = _quality_row(revenue=0.0)

        metrics = loader._compute_quality_metrics("ZNTL", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "zero_revenue_reported_this_period"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, zero_revenue_anchor_symbols=frozenset({"ZNTL"}))
        row = _quality_row(revenue=0.0)

        metrics = loader._compute_quality_metrics("OTHER", row, ev_metrics=(None, None, -5_000_000.0))

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "missing_sec_data"

    def test_real_revenue_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, zero_revenue_anchor_symbols=frozenset({"ZNTL"}))
        row = _quality_row(revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("ZNTL", row, ev_metrics=(None, None, 20_000_000.0))

        assert metrics["ebitda_margin"] == 20.0
        assert metrics.get("ebitda_margin_unavailable_reason") is None
