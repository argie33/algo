"""Regression test (2026-09-05, goal: "Missing SEC/XBRL data"/implausible-ratio reduction):
fcf_margin's cross-year fallback in _compute_quality_metrics only fired when the anchor
free_cash_flow/revenue pair was MISSING, not when it was present but implausible (|margin|>1000
from a near-zero-revenue extraction artifact). operating_margin/net_margin already handle this
correctly via _find_plausible_cross_year_ratio when the anchor ratio is implausible - fcf_margin
has its own inline cross-table (cash_flow+income_statement) query instead of reusing that helper
(needs a join those single-table lookups don't support), but had the same present-but-implausible
gap that roic_pct/roce_pct/operating_margin/net_margin/interest_coverage/gross_margin/
ebitda_margin were fixed for on 2026-09-05 - this closes the same gap for fcf_margin.
"""

from decimal import Decimal

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 500_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = 1_000.0  # revenue (anchor) - deliberately tiny to force an implausible margin
    row[8] = 2025  # fiscal_year
    row[14] = 50_000.0  # free_cash_flow (anchor) - 50_000/1_000*100 = 5000% > 1000 bound
    return row


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._last_query = ""
        self._fallback_rows = fallback_rows

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM annual_cash_flow acf" in self._last_query:
            return self._fallback_rows
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._fallback_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(fallback_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestFcfMarginImplausibleAnchorCrossYearFallback:
    def test_implausible_anchor_falls_back_to_plausible_older_year(self, monkeypatch):
        # An older fiscal year has a real, plausible (free_cash_flow, revenue) pair.
        loader = _make_loader(monkeypatch, [(Decimal("15000000.00"), Decimal("300000000.00"))])
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        # Before the fix: anchor (50_000/1_000*100=5000%) was implausible and NO fallback query
        # ran at all (anchor values were both non-None), so this landed as implausible_ratio.
        assert metrics["fcf_margin"] == 5.0
        assert metrics.get("fcf_margin_unavailable_reason") is None

    def test_implausible_anchor_with_no_plausible_fallback_stays_implausible(self, monkeypatch):
        # No older year has a plausible pair either - must still report implausible_ratio, not
        # silently pick an equally-bad fallback value.
        loader = _make_loader(monkeypatch, [(Decimal("50000.00"), Decimal("1000.00"))])
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["fcf_margin"] is None
        assert metrics.get("fcf_margin_unavailable_reason") == "implausible_ratio"
