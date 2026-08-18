"""Regression test for the 2026-08-18 fix ("no SEC data"/loader-failure audit goal):
_compute_quality_metrics()'s trend-field reason loop blanket-labeled EVERY unavailable trend
field "insufficient_prior_year_data" - a label that implies a loader/extraction gap - even when
the real cause was something else entirely.

Live-confirmed against this DB via a user-reported HIG dashboard screenshot: HIG (an insurer)
never reports cost_of_revenue/gross_profit in any fiscal year on file (same structural
"unclassified accounting" case already correctly labeled "reit_special_entity" for the base
gross_margin field), yet gross_margin_trend_unavailable_reason still said
"insufficient_prior_year_data". Universe-wide, 1397 of 2183 (64%) of growth_metrics'
gross_margin_trend "insufficient_prior_year_data" rows are this same structural case.

Also live-confirmed a second, distinct cause via RDZN: cost_of_revenue/prior_year_cost_of_revenue
were BOTH present, but produced a margin exceeding the MAX_MARGIN_ABS_PCT bound (cost_of_revenue
larger than revenue) - a real value deliberately excluded as implausible, not missing data - and
this also fell into the same misleading "insufficient_prior_year_data" bucket instead of
"implausible_ratio" (the reason already used elsewhere in this file for bound-rejected ratios).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    revenue=None,
    cost_of_revenue=None,
    gross_profit=None,
    prior_year_revenue=None,
    prior_year_cost_of_revenue=None,
):
    # Same 33-column shape as test_current_quick_ratio_reit_special_entity_reason.py's fixture.
    return (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        30_000_000.0,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        prior_year_revenue,  # 18
        gross_profit,  # 19
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        prior_year_cost_of_revenue,  # 28
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
    )


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        # No fallback gross_profit/cost_of_revenue found in any other fiscal year either.
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_never_reports_cogs_gets_reit_special_entity_not_generic_reason(monkeypatch):
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        revenue=1_506_000_000.0, cost_of_revenue=None, gross_profit=None, prior_year_revenue=1_458_000_000.0
    )

    metrics = loader._compute_quality_metrics("HIG", row, ev_metrics=None)

    assert metrics["gross_margin_trend"] is None
    assert metrics["gross_margin_trend_unavailable_reason"] == "reit_special_entity"


def test_implausible_margin_gets_implausible_ratio_not_generic_reason(monkeypatch):
    loader = _make_loader(monkeypatch)
    # Both years have real cost_of_revenue data, but cost_of_revenue exceeds revenue in the
    # current year - a real, if garbage, ratio (matches RDZN in the live DB).
    row = _quality_row(
        revenue=100.0,
        cost_of_revenue=2_000.0,
        gross_profit=None,
        prior_year_revenue=100.0,
        prior_year_cost_of_revenue=50.0,
    )

    metrics = loader._compute_quality_metrics("RDZN", row, ev_metrics=None)

    assert metrics["gross_margin_trend"] is None
    assert metrics["gross_margin_trend_unavailable_reason"] == "implausible_ratio"


def test_normal_trend_still_computes_and_reason_is_none(monkeypatch):
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        revenue=1_000.0,
        cost_of_revenue=600.0,
        gross_profit=None,
        prior_year_revenue=900.0,
        prior_year_cost_of_revenue=500.0,
    )

    metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

    assert metrics["gross_margin_trend"] is not None
    assert metrics.get("gross_margin_trend_unavailable_reason") is None
