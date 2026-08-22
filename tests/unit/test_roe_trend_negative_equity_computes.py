"""Regression test for the 2026-08-22 fix (goal session - coverage-bucket root-cause audit):
_compute_quality_metrics()'s roe_trend calculation required stockholders_equity > 0 on BOTH
years, unlike the base `roe` field in this same file (its own precedent) which only requires
`!= 0` plus the same MAX_MARGIN_ABS_PCT sanity bound.

Live-confirmed against this DB: YUM (Yum! Brands) has had negative stockholders_equity every
year 2021-2026 (real, well-known debt-funded buyback structure, not a data gap) with 5-6 years
of real net_income on file every year; IRM (Iron Mountain) went negative starting FY2024; COKE
(Coca-Cola Consolidated) went negative in FY2025-2026. All three were silently excluded from
roe_trend and mislabeled "insufficient_prior_year_data" - a label that implies missing data,
when the real data was present and simply negative. A DB-wide check found 388 of 798 (49%) of
the current "insufficient_prior_year_data" roe_trend population has real, present, negative
equity data.

sustainable_growth_rate has the identical `stockholders_equity > 0` gate, but its
"growth financeable from retained earnings relative to the equity base" interpretation doesn't
translate cleanly to a negative base, so it deliberately still does NOT compute a value for
negative equity - only the misleading "missing_sec_data" label was fixed, reusing this file's
own pre-existing "negative_book_value" reason (already used for pb_ratio's identical condition,
already correctly bucketed as "Legitimate / not applicable" in lambda/api/routes/scores.py).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=500_000_000.0,
    net_income=50_000_000.0,
    prior_year_stockholders_equity=None,
    prior_year_net_income=None,
    dividends_paid=None,
):
    # 34-column shape, same layout as tests/unit/test_gross_margin_trend_reason_mislabel.py.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        net_income,  # 3
        1_000_000_000.0,  # 4 revenue
        30_000_000.0,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        dividends_paid,  # 15
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        900_000_000.0,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        prior_year_net_income,  # 24
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        prior_year_stockholders_equity,  # 30
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
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


def test_negative_equity_both_years_computes_real_roe_trend(monkeypatch):
    """YUM-shaped: negative equity both years, real net_income both years - a real, computable
    trend, not a data gap."""
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        stockholders_equity=-7_283_000_000.0,
        net_income=1_559_000_000.0,
        prior_year_stockholders_equity=-7_325_000_000.0,
        prior_year_net_income=1_486_000_000.0,
    )

    metrics = loader._compute_quality_metrics("YUM", row, ev_metrics=None)

    assert metrics["roe_trend"] is not None
    assert metrics.get("roe_trend_unavailable_reason") is None


def test_negative_equity_transition_year_computes_real_roe_trend(monkeypatch):
    """IRM-shaped: equity crosses from positive to negative between the two years - still two
    real, non-zero data points, still a real (if sign-crossing) trend."""
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        stockholders_equity=-503_122_000.0,
        net_income=183_666_000.0,
        prior_year_stockholders_equity=211_648_000.0,
        prior_year_net_income=187_263_000.0,
    )

    metrics = loader._compute_quality_metrics("IRM", row, ev_metrics=None)

    assert metrics["roe_trend"] is not None
    assert metrics.get("roe_trend_unavailable_reason") is None


def test_zero_equity_still_falls_back_to_insufficient_reason(monkeypatch):
    """Exactly-zero equity (not merely negative) must still be excluded - `!= 0` deliberately
    stays a division-by-zero guard, not a data-completeness relaxation."""
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        stockholders_equity=0.0,
        net_income=50_000_000.0,
        prior_year_stockholders_equity=100_000_000.0,
        prior_year_net_income=40_000_000.0,
    )

    metrics = loader._compute_quality_metrics("ZEROEQ", row, ev_metrics=None)

    assert metrics["roe_trend"] is None
    assert metrics.get("roe_trend_unavailable_reason") == "insufficient_prior_year_data"


def test_missing_prior_year_data_still_gets_insufficient_reason(monkeypatch):
    """Genuinely absent prior-year data (not merely negative) must keep the real
    "insufficient_prior_year_data" label - this fix narrows a mislabel, it doesn't remove the
    label entirely."""
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        stockholders_equity=500_000_000.0,
        net_income=50_000_000.0,
        prior_year_stockholders_equity=None,
        prior_year_net_income=None,
    )

    metrics = loader._compute_quality_metrics("NOPRIOR", row, ev_metrics=None)

    assert metrics["roe_trend"] is None
    assert metrics.get("roe_trend_unavailable_reason") == "insufficient_prior_year_data"


def test_negative_equity_sustainable_growth_rate_gets_negative_book_value_reason(monkeypatch):
    """sustainable_growth_rate deliberately still does NOT compute for negative equity (unlike
    roe_trend), but the label must say why: real, present, negative equity data - reusing this
    file's pre-existing "negative_book_value" reason - not the misleading "missing_sec_data"."""
    loader = _make_loader(monkeypatch)
    row = _quality_row(
        stockholders_equity=-7_283_000_000.0,
        net_income=1_559_000_000.0,
        dividends_paid=500_000_000.0,
    )

    metrics = loader._compute_quality_metrics("YUM", row, ev_metrics=None)

    assert metrics.get("sustainable_growth_rate") is None
    assert metrics.get("sustainable_growth_rate_unavailable_reason") == "negative_book_value"
