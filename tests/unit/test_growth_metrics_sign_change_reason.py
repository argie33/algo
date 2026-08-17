"""Regression test for the 2026-08-17 fix: ValueQualityGrowthMetricsLoader._compute_growth_metrics()
labeled EVERY failed growth computation "insufficient_history", including cases where a company
had ample fiscal-year EPS history but CAGR is mathematically undefined because EPS crossed
between a loss and a profit (e.g. -5.95 -> 0.35) between the two comparison points.

Live-confirmed against the local DB: 796 of 1,493 symbols flagged eps_growth_1y
"insufficient_history" actually had >=2 years of real EPS data (BMBL, CMCL, AMBR, ANDG, ALTO,
etc.) - the CAGR sign-flip guard in _cagr() was working correctly, but _compute_period_growth()
couldn't distinguish "too few data points" from "CAGR undefined due to sign change" and reported
both identically, misleading users into thinking the company lacked historical data it actually
had. Fixed by detecting the sign flip explicitly and reporting "growth_undefined_sign_change"
instead of "insufficient_history" for that specific case.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_eps_sign_flip_reports_distinct_reason_not_insufficient_history():
    loader = _make_loader()
    # 7 years of real EPS history (BMBL-shaped), most recent two years cross loss -> profit.
    income_rows = [
        (2026, 212383000.0, None, None, 0.35),
        (2025, 965658000.0, None, None, -5.95),
        (2024, 1071643000.0, None, None, -4.61),
        (2023, 1051830000.0, None, None, -0.03),
        (2022, 903503000.0, None, None, -0.62),
        (2021, 760910000.0, None, None, 1.50),
        (2020, 539546000.0, None, None, -0.04),
    ]

    result = loader._compute_growth_metrics("BMBL", income_rows)

    assert result["eps_growth_1y"] is None
    assert result["eps_growth_1y_unavailable_reason"] == "growth_undefined_sign_change"
    # Revenue never goes negative (filtered to rev > 0), so it's unaffected by this bug class.
    assert result["revenue_growth_1y"] is not None
    assert result["revenue_growth_1y_unavailable_reason"] is None


def test_too_few_datapoints_still_reports_insufficient_history():
    loader = _make_loader()
    income_rows = [(2026, 100.0, None, None, 1.0)]  # only 1 fiscal year - genuinely not enough

    result = loader._compute_growth_metrics("SOLO", income_rows)

    assert result["eps_growth_1y"] is None
    assert result["eps_growth_1y_unavailable_reason"] == "insufficient_history"


def test_same_sign_negative_to_negative_computes_normally():
    loader = _make_loader()
    # Both negative (loss narrowing) - CAGR is well-defined here, must not be flagged as a sign change.
    income_rows = [
        (2026, 100.0, None, None, -1.0),
        (2025, 100.0, None, None, -2.0),
    ]

    result = loader._compute_growth_metrics("NARROW", income_rows)

    assert result["eps_growth_1y"] is not None
    assert result["eps_growth_1y_unavailable_reason"] is None
