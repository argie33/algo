"""Regression test (2026-09-04, goal: "Missing SEC/XBRL data" reduction): the fcf_margin
cross-year fallback in _compute_quality_metrics compared raw psycopg2 Decimal rows with a bare
`* 100.0` float literal (`abs(row[0] / row[1] * 100.0)`), raising `TypeError: unsupported
operand type(s) for *: 'decimal.Decimal' and 'float'` whenever the fallback query actually had
candidate rows (Decimal is psycopg2's native NUMERIC type - every other numeric read in this
function goes through safe_float() first, this one didn't). The whole computation is wrapped in
one outer try/except that falls back to _unavailable_marker() on ANY exception, so this crash
silently wiped out EVERY quality_metrics field for the symbol (roa/roe/debt_to_equity/
gross_profitability/quality_score/...) as generic "missing_sec_data" - not just fcf_margin.
Live-confirmed via AIG (real net_income/total_assets present, would have produced a real
roa=1.92%/roe=7.53%/debt_to_equity=0.24, but crashed to all-None before the fix).
"""

from decimal import Decimal

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 500_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = 300_000_000.0  # revenue
    row[8] = 2025  # fiscal_year
    row[14] = None  # free_cash_flow (anchor row) - forces the fcf_margin fallback path
    return row


class _FakeCursor:
    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM annual_cash_flow acf" in self._last_query:
            # Real psycopg2 NUMERIC columns come back as Decimal, not float/int.
            return [(Decimal("15000000.00"), Decimal("300000000.00"))]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestFcfMarginFallbackDecimalFloatCrash:
    def test_decimal_fallback_rows_do_not_crash_whole_computation(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        # Before the fix, the Decimal * float TypeError propagated out of
        # _compute_quality_metrics's own try/except and wiped every field to None via
        # _unavailable_marker - roa/roe/debt_to_equity have real inputs above and must compute.
        assert metrics["roa"] == 10.0
        assert metrics["roe"] == 50.0
        assert metrics.get("roa_unavailable_reason") is None
        assert metrics.get("roe_unavailable_reason") is None

    def test_fallback_fcf_margin_computes_real_value(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        # 15,000,000 / 300,000,000 * 100 = 5.0
        assert metrics["fcf_margin"] == 5.0
        assert metrics.get("fcf_margin_unavailable_reason") is None
