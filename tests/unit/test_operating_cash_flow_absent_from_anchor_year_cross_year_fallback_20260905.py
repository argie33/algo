"""Regression test (2026-09-05, same fix as
test_free_cash_flow_absent_from_anchor_year_cross_year_fallback_20260905.py): the standalone
quality_metrics.operating_cash_flow field never used a cross-year fallback either - same
shape as free_cash_flow, a standalone dollar figure with no same-year pairing requirement of
its own (unlike ocf_to_net_income/accruals_ratio, which need it aligned to net_income's/
total_assets' anchor year).
"""

from decimal import Decimal

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 500_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = 400_000_000.0  # revenue (anchor)
    row[8] = 2025  # fiscal_year
    row[13] = None  # operating_cash_flow (anchor) - missing
    row[14] = None  # free_cash_flow (anchor) - also missing, irrelevant here
    return row


class _FakeCursor:
    def __init__(self, fallback_row):
        self._last_query = ""
        self._fallback_row = fallback_row

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT operating_cash_flow FROM annual_cash_flow" in self._last_query:
            return self._fallback_row
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_row):
        self._fallback_row = fallback_row

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._fallback_row)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_row):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(fallback_row))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestOperatingCashFlowAbsentFromAnchorYearCrossYearFallback:
    def test_missing_anchor_falls_back_to_older_real_value(self, monkeypatch):
        loader = _make_loader(monkeypatch, (Decimal("90000000.00"),))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["operating_cash_flow"] == 90_000_000.0
        assert metrics.get("operating_cash_flow_unavailable_reason") is None

    def test_missing_anchor_with_no_older_value_stays_absent(self, monkeypatch):
        loader = _make_loader(monkeypatch, None)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics.get("operating_cash_flow") is None

    def test_ocf_to_net_income_still_uses_anchor_only_unaffected_by_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, (Decimal("90000000.00"),))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics.get("ocf_to_net_income") is None
