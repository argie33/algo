"""Regression test (2026-09-04, goal: "Missing SEC/XBRL data" reduction, same anchor-year fiscal
mismatch bug class as test_net_income_absent_from_anchor_year_reason_20260902.py/
test_revenue_absent_from_anchor_year_quality_metrics_20260902.py): ROE and
sustainable_growth_rate fell to "missing_sec_data" whenever the balance-sheet anchor row's own
stockholders_equity was NULL, even though roic_pct/roce_pct/debt_to_equity already had a
fallback search for the equivalent case (roic_stockholders_equity, further down in
_compute_quality_metrics). Live-confirmed 345 of 371 universe roe "missing_sec_data" residual
symbols have a real stockholders_equity in SOME annual_balance_sheet fiscal year. This is a
real-value fix (a nearby year's stockholders_equity is substituted in), not a relabel.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=None, net_income=50_000_000.0, total_assets=700_000_000.0):
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
    def __init__(self, fallback_stockholders_equity):
        self._fallback_se = fallback_stockholders_equity
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        q = self._last_query
        # The new single-column early fallback (this fix) vs. the pre-existing paired
        # roic_stockholders_equity/cash_and_equivalents fallback further below - distinguish by
        # whether cash_and_equivalents is also selected.
        if "stockholders_equity" in q and "cash_and_equivalents" not in q:
            return (self._fallback_se,) if self._fallback_se is not None else None
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_stockholders_equity=None):
        self._fallback_se = fallback_stockholders_equity

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._fallback_se)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_stockholders_equity=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(fallback_stockholders_equity))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestStockholdersEquityAnchorYearFallback:
    def test_anchor_row_null_equity_uses_fallback_year_for_roe(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_stockholders_equity=100_000_000.0)
        row = _quality_row(stockholders_equity=None, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roe"] == 50.0
        assert metrics.get("roe_unavailable_reason") is None

    def test_no_fallback_available_stays_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_stockholders_equity=None)
        row = _quality_row(stockholders_equity=None, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roe"] is None

    def test_real_anchor_equity_unaffected(self, monkeypatch):
        # Fallback DB value differs from the anchor row's real value - must not be consulted at
        # all since stockholders_equity is already non-None from the anchor row itself.
        loader = _make_loader(monkeypatch, fallback_stockholders_equity=999_000_000.0)
        row = _quality_row(stockholders_equity=100_000_000.0, net_income=50_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["roe"] == 50.0
