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


def test_cumulative_multi_year_dilution_with_no_single_year_split_jump_is_not_blocked():
    """REGRESSION for the 2026-08-31 fix: the guard used to compare shares only at the two CAGR
    endpoints, so gradual organic dilution/buybacks that happen to cross the 1.5x ratio over a
    3-5 year window (e.g. a REIT steadily issuing equity, or a mature company steadily buying
    back stock) got wrongly blocked as a "split" even though no single fiscal year shows
    anything resembling a real split - live-confirmed on TRNO/RCMT/LOPE/ARW, ~50% of the
    1,569 real (symbol, period) comparisons flagged in the live DB turned out to be this exact
    false positive. This fixture's shares grow ~60% smoothly over 5 years (no single-year jump
    above ~11%) - a real capital-structure change, not a split - so eps_growth_5y must compute.
    """
    loader = _make_loader()
    income_rows = [
        (2026, 100.0, None, None, 2.0, 160000000, None),
        (2025, 100.0, None, None, 1.8, 148000000, None),
        (2024, 100.0, None, None, 1.6, 135000000, None),
        (2023, 100.0, None, None, 1.4, 122000000, None),
        (2022, 100.0, None, None, 1.2, 110000000, None),
        (2021, 100.0, None, None, 1.0, 100000000, None),
    ]

    result = loader._compute_growth_metrics("GRADUALDILUTE", income_rows)

    assert result["eps_growth_5y"] is not None
    assert result["eps_growth_5y_unavailable_reason"] is None


def test_single_year_ma_share_issuance_near_a_clean_multiple_is_not_blocked():
    """REGRESSION for the 2026-09-11 fix: EPS_SPLIT_GUARD_CLEAN_TOLERANCE was 0.06 (6%), loose
    enough that a genuine SINGLE-YEAR share jump from ordinary M&A/capital-raise issuance could
    coincidentally land near a "clean" split multiple and get wrongly blocked. Live-confirmed on
    COF (Capital One's 2024->2025 Discover Financial acquisition issuance, real ratio 1.411x,
    5.9% off 1.5x - not remotely a split) and IRT (2016->2017 RAIT Residential merger issuance,
    same ~1.41x). A live-DB histogram of all flagged (symbol, adjacent-year-pair) deviations from
    their nearest clean multiple was essentially flat noise from 0% to 6%, with a genuine-split
    excess confined to the 0.0%-0.1% band (see NVDA's real 10:1 split two tests below, which
    reports a 1.10%-off-10x ratio from in-year buyback/issuance activity) - tolerance tightened to
    1.5% to keep detecting real splits like NVDA's with margin while excluding this class of false
    positive. This fixture mirrors COF's real ratio (1.411x, single year, no other jump nearby).
    """
    loader = _make_loader()
    income_rows = [
        (2026, 100.0, None, None, 2.0, 141100000, None),
        (2025, 100.0, None, None, 1.8, 100000000, None),
    ]

    result = loader._compute_growth_metrics("MAISSUANCE", income_rows)

    assert result["eps_growth_1y"] is not None
    assert result["eps_growth_1y_unavailable_reason"] is None


def test_real_split_confounded_by_surrounding_buybacks_is_still_caught():
    """GOOGL-shaped: a real 20:1 split concentrated in one fiscal year, with buybacks in the
    surrounding years pulling the naive 5yr ENDPOINT ratio down to ~18x (not exactly 20x) - the
    endpoint-only near-clean check the initial fix design considered would have missed this.
    Scanning adjacent-year pairs isolates the split year itself and still catches it.
    """
    loader = _make_loader()
    income_rows = [
        (2026, 100.0, None, None, 2.0, 12100000000, None),
        (2025, 100.0, None, None, 1.8, 12230000000, None),
        (2024, 100.0, None, None, 1.6, 12447000000, None),
        (2023, 100.0, None, None, 1.4, 12722000000, None),
        (2022, 100.0, None, None, 1.2, 13159000000, None),  # post-split
        (2021, 100.0, None, None, 1.0, 662121000, None),  # pre-split: ~19.9x jump vs 2022
    ]

    result = loader._compute_growth_metrics("SPLITBUYBACK", income_rows)

    assert result["eps_growth_5y"] is None
    assert result["eps_growth_5y_unavailable_reason"] == "growth_undefined_share_count_discontinuity"
