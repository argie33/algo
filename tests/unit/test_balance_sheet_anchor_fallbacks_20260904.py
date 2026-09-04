"""Regression tests (2026-09-04, goal: "Missing SEC/XBRL data" reduction, same anchor-year
fiscal mismatch bug class as test_stockholders_equity_anchor_year_fallback_20260904.py /
test_total_assets_anchor_year_fallback_20260904.py): debt_to_assets/current_ratio/quick_ratio
fell to "missing_sec_data" whenever the balance-sheet anchor row's own total_liabilities/
current_assets/current_liabilities were NULL, with no cross-year fallback. Live-confirmed 328
of 354 universe debt_to_assets residual symbols have a real total_liabilities elsewhere, 301 of
359 current_ratio residual symbols have a real current_assets elsewhere (300/359 for
current_liabilities). Real-value fixes (nearby-year substitution), not relabels.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    total_liabilities=None,
    current_assets=None,
    current_liabilities=None,
    stockholders_equity=100_000_000.0,
    total_assets=700_000_000.0,
    net_income=50_000_000.0,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = current_assets
    row[7] = current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, fallback_values):
        # fallback_values: dict of {column_name: value}
        self._fallback_values = fallback_values
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        q = self._last_query
        for column, value in self._fallback_values.items():
            if f"SELECT {column} FROM annual_balance_sheet" in q:
                return (value,) if value is not None else None
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_values):
        self._fallback_values = fallback_values

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._fallback_values)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_values):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(fallback_values))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestTotalLiabilitiesAnchorYearFallback:
    def test_anchor_row_null_liabilities_uses_fallback_year_for_debt_to_assets(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"total_liabilities": 350_000_000.0})
        row = _quality_row(total_liabilities=None, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_assets"] == 0.5
        assert metrics.get("debt_to_assets_unavailable_reason") is None

    def test_no_fallback_available_stays_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"total_liabilities": None})
        row = _quality_row(total_liabilities=None)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_assets"] is None


class TestCurrentAssetsCurrentLiabilitiesAnchorYearFallback:
    def test_anchor_row_null_current_fields_use_fallback_year_for_current_ratio(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            {"current_assets": 150_000_000.0, "current_liabilities": 100_000_000.0},
        )
        row = _quality_row(current_assets=None, current_liabilities=None)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["current_ratio"] == 1.5
        assert metrics.get("current_ratio_unavailable_reason") is None

    def test_no_fallback_available_stays_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"current_assets": None, "current_liabilities": None})
        row = _quality_row(current_assets=None, current_liabilities=None)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["current_ratio"] is None

    def test_real_anchor_values_unaffected(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            {"current_assets": 999_000_000.0, "current_liabilities": 999_000_000.0},
        )
        row = _quality_row(current_assets=150_000_000.0, current_liabilities=100_000_000.0)

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["current_ratio"] == 1.5
