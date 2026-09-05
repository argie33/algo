"""Regression test (2026-09-05, "SEC/XBRL missing data to zero" goal session): gross_margin
and ebitda_margin's |ratio| > 1000 implausible-value bound had no cross-year fallback, unlike
roe/roa/asset_turnover/roic_pct/roce_pct/operating_margin/net_margin/interest_coverage.

gross_margin (11 rows live) reuses `_find_plausible_cross_year_ratio` with a new
`gross_profit` field. ebitda_margin (228 rows live - the largest remaining bucket after this
session's other fixes) needed a dedicated helper,
`_find_plausible_cross_year_ebitda_margin_ratio`, because the anchor's `ebitda_ev` comes from
`sec_valuations` (single latest-snapshot row, no fiscal-year dimension) - the fallback instead
reconstructs EBITDA per candidate year as operating_income + depreciation_expense +
amortization_expense from `annual_income_statement` alone.
"""

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        # Other DB calls made during _compute_quality_metrics (symbol-gate lookups, etc.)
        # share this same fake DatabaseContext - only the cross-year fallback's own query
        # should see the crafted fallback row.
        if "ais.net_income" in self._last_query and "ais.gross_profit" in self._last_query:
            return self._fallback_rows["gross_margin"]
        if "depreciation_expense" in self._last_query:
            return self._fallback_rows["ebitda_margin"]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows

    def __enter__(self):
        return _FakeCursor(self._fallback_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fallback_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(revenue=None, gross_profit=None):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        100_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


# Same anchor as test_quality_metrics_implausible_ratio_reason.py's CRML gross_margin case:
# gross_profit=125M / revenue=540 -> way past the |ratio|>1000 bound.
_GROSS_MARGIN_ANCHOR_KWARGS = {"gross_profit": 125_000_000.0, "revenue": 540.0}

# Older fiscal year, plausible pair: gross_profit=40M / revenue=100M = 40% - plausible.
# Row shape: (net_income, total_assets, stockholders_equity, revenue, operating_income,
# interest_expense, gross_profit)
_GROSS_MARGIN_PLAUSIBLE_ROW = (
    8_000_000.0,
    100_000_000.0,
    50_000_000.0,
    100_000_000.0,
    12_000_000.0,
    1_000_000.0,
    40_000_000.0,
)

# Same anchor as test_quality_metrics_implausible_ratio_reason.py's CLBT ebitda_margin case:
# ebitda_ev=155,771,000 / revenue=2,454,000 -> way past the |ratio|>1000 bound.
_EBITDA_MARGIN_ANCHOR_KWARGS = {"revenue": 2_454_000.0}
_EBITDA_MARGIN_EV_METRICS = (None, None, 155_771_000.0)

# Older fiscal year, plausible EBITDA: operating_income=10M + D&A(3M+1M) = 14M / revenue=100M
# = 14% - plausible. Row shape: (operating_income, depreciation_expense, amortization_expense,
# revenue).
_EBITDA_MARGIN_PLAUSIBLE_ROW = (10_000_000.0, 3_000_000.0, 1_000_000.0, 100_000_000.0)


class TestGrossMarginCrossYearFallback:
    def test_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"gross_margin": [_GROSS_MARGIN_PLAUSIBLE_ROW], "ebitda_margin": []})
        row = _quality_row(**_GROSS_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("CRML", row, ev_metrics=None)

        assert metrics["gross_margin"] == 40.0
        assert metrics.get("gross_margin_unavailable_reason") is None

    def test_falls_through_to_implausible_when_no_fallback_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"gross_margin": [], "ebitda_margin": []})
        row = _quality_row(**_GROSS_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("CRML", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "implausible_ratio"


class TestEbitdaMarginCrossYearFallback:
    def test_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"gross_margin": [], "ebitda_margin": [_EBITDA_MARGIN_PLAUSIBLE_ROW]})
        row = _quality_row(**_EBITDA_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("CLBT", row, ev_metrics=_EBITDA_MARGIN_EV_METRICS)

        assert metrics["ebitda_margin"] == pytest.approx(14.0)
        assert metrics.get("ebitda_margin_unavailable_reason") is None

    def test_falls_through_to_implausible_when_no_fallback_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, {"gross_margin": [], "ebitda_margin": []})
        row = _quality_row(**_EBITDA_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("CLBT", row, ev_metrics=_EBITDA_MARGIN_EV_METRICS)

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "implausible_ratio"
