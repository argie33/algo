"""Regression test (2026-09-05, goal: "Missing SEC/XBRL data" reduction): the standalone
quality_metrics.free_cash_flow field never used a cross-year fallback at all - when the anchor
fiscal year's free_cash_flow was NULL, the metric failed outright and only got a diagnostic
`free_cash_flow_absent_from_anchor_year` label (see [[eps_and_fcf_absent_from_anchor_year_fixes_
20260905]] - that fix was explicitly label-only, not a value recompute). Unlike fcf_margin/
fcf_to_net_income, this field is a standalone dollar figure with no same-year pairing
requirement, so an older real value is a safe substitution - same reasoning as the roic_pct/
roce_pct cross-year fallback fixed the same day. Uses a fresh, local `standalone_free_cash_flow`
variable so fcf_to_net_income/fcf_margin (which need anchor-year-aligned free_cash_flow) are
untouched.
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
    row[14] = None  # free_cash_flow (anchor) - missing
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
        # Only the standalone free_cash_flow fallback issues a single-table (no JOIN)
        # SELECT free_cash_flow FROM annual_cash_flow query via fetchone().
        if "FROM annual_cash_flow" in self._last_query and "JOIN" not in self._last_query:
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


class TestFreeCashFlowAbsentFromAnchorYearCrossYearFallback:
    def test_missing_anchor_falls_back_to_older_real_value(self, monkeypatch):
        loader = _make_loader(monkeypatch, (Decimal("75000000.00"),))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics["free_cash_flow"] == 75_000_000.0
        assert metrics.get("free_cash_flow_unavailable_reason") is None

    def test_missing_anchor_with_no_older_value_stays_absent(self, monkeypatch):
        loader = _make_loader(monkeypatch, None)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics.get("free_cash_flow") is None

    def test_fcf_to_net_income_still_uses_anchor_only_unaffected_by_fallback(self, monkeypatch):
        # fcf_to_net_income must NOT pick up the cross-year fallback value - it needs
        # free_cash_flow aligned to the SAME fiscal year as net_income, unlike the standalone
        # free_cash_flow field.
        loader = _make_loader(monkeypatch, (Decimal("75000000.00"),))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics.get("fcf_to_net_income") is None
