"""Regression test for the 2026-08-24 fix: ValueQualityGrowthMetricsLoader._compute_period_growth()
compared raw as-reported EPS across a stock-split boundary with no guard, silently producing a
plausible-looking but badly wrong CAGR.

Live-confirmed on NVDA (10-for-1 split, June 2024): annual_income_statement has FY2023-FY2026
correctly restated post-split (EPS 0.18/1.21/2.97/4.93, shares_outstanding_diluted ~25B) because
SEC 10-Ks only restate the comparative years shown in the filing, but FY2021/FY2022 are still
pre-split (EPS 1.76/3.91, shares_outstanding_diluted ~2.5B). eps_growth_5y compared FY2026 (4.93,
post-split) against FY2021 (1.76, pre-split) and computed 22.88% CAGR - the true split-adjusted
FY2021 EPS is 1.76/10=0.176, giving a real CAGR of ~95%, roughly 4x higher. Fixed by comparing
shares_outstanding at the two CAGR endpoints: a >=1.5x ratio (far beyond any real 5-year
buyback/dilution drift) means the two EPS values are on different per-share bases and the metric
now fails closed with "growth_undefined_share_count_discontinuity" instead of returning the wrong
number.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_eps_growth_5y_across_split_boundary_reports_discontinuity_not_a_number():
    loader = _make_loader()
    # NVDA-shaped: FY2023-2026 restated post-10:1-split (~25B diluted shares), FY2021-2022
    # still pre-split (~2.5B diluted shares) - real fiscal_year/revenue/opinc/net_income values
    # aren't load-bearing for this test, only fiscal_year/eps/shares columns are.
    income_rows = [
        (2026, 215938000000.0, None, None, 4.93, 24514000000, None),
        (2025, 130497000000.0, None, None, 2.97, 24804000000, None),
        (2024, 60922000000.0, None, None, 1.21, 24940000000, None),
        (2023, 26974000000.0, None, None, 0.18, 25070000000, None),
        (2022, 26914000000.0, None, None, 3.91, 2535000000, None),
        (2021, 16675000000.0, None, None, 1.76, 2510000000, None),
    ]

    result = loader._compute_growth_metrics("NVDA", income_rows)

    assert result["eps_growth_5y"] is None
    assert result["eps_growth_5y_unavailable_reason"] == "growth_undefined_share_count_discontinuity"
    # eps_growth_3y's endpoints (FY2026 vs FY2023) are both post-split - unaffected by the guard.
    assert result["eps_growth_3y"] is not None
    assert result["eps_growth_3y_unavailable_reason"] is None
    # Revenue isn't per-share, so it's never affected by a split discontinuity.
    assert result["revenue_growth_5y"] is not None
    assert result["revenue_growth_5y_unavailable_reason"] is None


def test_eps_growth_without_share_data_falls_back_to_computing_normally():
    loader = _make_loader()
    # 5-tuple rows (no shares columns) - must behave exactly as before this fix.
    income_rows = [
        (2026, 100.0, None, None, 2.0),
        (2025, 100.0, None, None, 1.8),
        (2024, 100.0, None, None, 1.6),
        (2023, 100.0, None, None, 1.4),
        (2022, 100.0, None, None, 1.2),
        (2021, 100.0, None, None, 1.0),
    ]

    result = loader._compute_growth_metrics("NOSHARES", income_rows)

    assert result["eps_growth_5y"] is not None
    assert result["eps_growth_5y_unavailable_reason"] is None


def test_modest_buyback_driven_share_change_does_not_trip_the_guard():
    loader = _make_loader()
    # Real 5-year buyback drift (~20% share reduction over 5 years, endpoints only need to be
    # populated) must NOT be misread as a split.
    income_rows = [
        (2026, 100.0, None, None, 2.0, 800000000, None),
        (2025, 100.0, None, None, 1.8, 850000000, None),
        (2024, 100.0, None, None, 1.6, 900000000, None),
        (2023, 100.0, None, None, 1.4, 930000000, None),
        (2022, 100.0, None, None, 1.2, 960000000, None),
        (2021, 100.0, None, None, 1.0, 1000000000, None),
    ]

    result = loader._compute_growth_metrics("BUYBACK", income_rows)

    assert result["eps_growth_5y"] is not None
    assert result["eps_growth_5y_unavailable_reason"] is None
