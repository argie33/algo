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


def test_all_six_periods_failing_for_a_mix_of_reasons_keeps_nuanced_reasons():
    """FIXED 2026-08-21 (same session, follow-up to the sign-change fix above): when ALL 6
    growth periods fail - not just some - the `len(failed_metrics) == 6` shortcut used to
    `return self._unavailable_marker("growth_metrics", symbol)`, a completely fresh dict
    that hardcodes every *_unavailable_reason to "insufficient_history", silently
    overwriting the nuanced per-field reasons _growth_reason() had just computed above it
    (including a real sign-change this exact fix already exists to report correctly).

    Live-confirmed on LFT/BDTX/ENLV: each has genuinely too little revenue history (only 1
    real positive-revenue fiscal year - correctly "insufficient_history") AND a real EPS
    sign change between the CAGR endpoints (should be "growth_undefined_sign_change") - but
    because revenue and EPS both failed for every one of the 6 periods, the len==6 shortcut
    fired and silently reverted eps_growth_5y back to "insufficient_history" anyway.
    """
    loader = _make_loader()
    # LFT-shaped: only ONE usable revenue year (all 6 revenue-based periods genuinely lack
    # history), but 7 EPS years with a sign flip between the most recent (negative) and the
    # 5-years-back point (positive) - eps_growth_5y specifically must stay a sign-change.
    income_rows = [
        (2025, None, None, None, -0.14),
        (2024, None, None, None, 0.34),
        (2023, None, None, None, 0.29),
        (2022, None, None, None, 0.11),
        (2021, None, None, None, 0.30),
        (2020, None, None, None, 0.34),
        (2013, 18916975.0, None, None, 0.52),
    ]

    result = loader._compute_growth_metrics("LFT", income_rows)

    assert result["data_unavailable"] is True
    assert result["revenue_growth_1y_unavailable_reason"] == "insufficient_history"
    assert result["revenue_growth_5y_unavailable_reason"] == "insufficient_history"
    assert result["eps_growth_1y_unavailable_reason"] == "growth_undefined_sign_change"
    assert result["eps_growth_3y_unavailable_reason"] == "growth_undefined_sign_change"
    assert result["eps_growth_5y_unavailable_reason"] == "growth_undefined_sign_change"
