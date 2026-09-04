"""Regression test (2026-09-04, goal: "Missing SEC/XBRL data" reduction, same anchor-year
fiscal mismatch bug class as test_stockholders_equity_anchor_year_fallback_20260904.py): ROA
and asset_turnover fell to "missing_sec_data" whenever the balance-sheet anchor row's own
total_assets was NULL, with no cross-year fallback. Live-confirmed 343 of 370 universe roa
"missing_sec_data" residual symbols have a real total_assets in SOME annual_balance_sheet
fiscal year. Real-value fix (a nearby year's total_assets is substituted in), not a relabel.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(total_assets=None, net_income=50_000_000.0, stockholders_equity=100_000_000.0):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, fallback_total_assets):
        self._fallback_ta = fallback_total_assets
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        q = self._last_query
        # The new single-column total_assets fallback (this fix) - every other fetchone()
        # consumer elsewhere in _compute_quality_metrics selects different columns.
        if "SELECT total_assets FROM annual_balance_sheet" in q:
            return (self._fallback_ta,) if self._fallback_ta is not None else None
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_total_assets=None):
        self._fallback_ta = fallback_total_assets

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._fallback_ta)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_total_assets=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(fallback_total_assets))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestTotalAssetsAnchorYearFallback:
    def test_anchor_row_null_assets_uses_fallback_year_for_roa(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_total_assets=500_000_000.0)
        row = _quality_row(total_assets=None, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roa"] == 10.0
        assert metrics.get("roa_unavailable_reason") is None

    def test_no_fallback_available_stays_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_total_assets=None)
        row = _quality_row(total_assets=None, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roa"] is None

    def test_real_anchor_assets_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_total_assets=999_000_000.0)
        row = _quality_row(total_assets=500_000_000.0, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roa"] == 10.0
