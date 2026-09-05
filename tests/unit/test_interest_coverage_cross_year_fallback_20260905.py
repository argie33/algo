"""Regression test (2026-09-05, "SEC/XBRL missing data to zero" goal session):
interest_coverage's |ratio| > 1000 implausible-value bound had no cross-year fallback, unlike
roe/roa/asset_turnover/roic_pct/roce_pct/operating_margin/net_margin. Live DB audit: 276 rows
stuck at implausible_ratio - the largest single residual after this session's margin fixes.

interest_coverage is a raw multiple (operating_income / interest_expense), not a percentage -
`_find_plausible_cross_year_ratio` gained an `as_percentage=False` mode so the fallback value
stays on the same scale as the anchor-year computation (which never multiplies by 100).
"""

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
        if "ais.net_income" in self._last_query and "ais.revenue" in self._last_query:
            return self._fallback_rows
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


def _quality_row(operating_income=None, interest_expense=None, pretax_income=None):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture
    # (this is the exact IKT anchor from that file's own interest_coverage test).
    return (
        100_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        interest_expense,  # 10
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        pretax_income,  # 23
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


# Same anchor as test_quality_metrics_implausible_ratio_reason.py's IKT case:
# -17,841,919 / 5.0 = -3,568,383.8x, past the |ratio|>1000 bound.
_ANCHOR_KWARGS = {"operating_income": -17_841_919.0, "interest_expense": 5.0, "pretax_income": None}

# Older fiscal year, plausible pair: operating_income=5M / interest_expense=1M = 5.0x - plausible.
# Row shape: (net_income, total_assets, stockholders_equity, revenue, operating_income, interest_expense)
_PLAUSIBLE_FALLBACK_ROW = (8_000_000.0, 100_000_000.0, 50_000_000.0, 100_000_000.0, 5_000_000.0, 1_000_000.0)


class TestInterestCoverageCrossYearFallback:
    def test_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("IKT", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 5.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

    def test_falls_through_to_implausible_when_no_fallback_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("IKT", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "implausible_ratio"

    def test_negative_fallback_interest_expense_rejected(self, monkeypatch):
        # A negative/zero interest_expense in the fallback candidate year must not be
        # accepted - matches the anchor computation's own `interest_expense > 0` requirement.
        negative_row = (8_000_000.0, 100_000_000.0, 50_000_000.0, 100_000_000.0, 5_000_000.0, -1_000_000.0)
        loader = _make_loader(monkeypatch, [negative_row])
        row = _quality_row(**_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("IKT", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "implausible_ratio"
