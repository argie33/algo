"""Regression test (2026-09-04, same Decimal/float class as the fcf_margin fallback fix):
_find_plausible_cross_year_ratio (the roe/roa/asset_turnover implausible-ratio cross-year
fallback added 2026-09-04) compared raw psycopg2 Decimal rows with a bare `* 100.0` float
literal - `Decimal * float` raises TypeError on every single call (not just some), since
numerator/denominator always come straight off fetchall() with no float conversion. This
function only runs on the already-rare implausible-anchor-ratio branch, so the always-crash
bug was invisible to audits that only checked whether a usable fallback row EXISTED in the
query result, not whether this code actually returned it without crashing. The crash
propagates to the outer try/except in _compute_quality_metrics, wiping the entire
quality_metrics row (not just the one ratio) to "missing_sec_data".
"""

from decimal import Decimal

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDatabaseContext:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestCrossYearRatioFallbackDecimalFloatCrash:
    def test_decimal_rows_do_not_crash_and_return_plausible_ratio(self, monkeypatch):
        # net_income, total_assets, stockholders_equity, revenue - all real psycopg2 Decimals.
        rows = [(Decimal("5000000.00"), Decimal("20000000000.00"), Decimal("100000000.00"), Decimal("300000000.00"))]
        loader = _make_loader(monkeypatch, rows)

        result = loader._find_plausible_cross_year_ratio("SYM", "net_income", "total_assets")

        assert result == 0.025

    def test_still_skips_a_second_implausible_year_and_returns_none(self, monkeypatch):
        rows = [(Decimal("50000000000.00"), Decimal("1.00"), Decimal("100000000.00"), Decimal("300000000.00"))]
        loader = _make_loader(monkeypatch, rows)

        result = loader._find_plausible_cross_year_ratio("SYM", "net_income", "total_assets")

        assert result is None
