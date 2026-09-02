"""Regression test: ValueQualityGrowthMetricsLoader._compute_growth_metrics()/_compute_period_
growth() labeled a REAL, computed CAGR that exceeds MAX_PLAUSIBLE_GROWTH_PCT (2000%) the same
"insufficient_history" as genuinely too few fiscal-year data points, indistinguishable from each
other downstream - misleading users into thinking the company lacked historical data it actually
had, when the real story is a small-base ramp-up (e.g. a company going from $22.72M to $829.45M
revenue in a year, a real 3652% CAGR) that's simply too extreme a ratio to be meaningful.

Found live 2026-09-02 (same /goal session as the ev_revenue/ev_ebitda negative-EV and
zero-revenue-anchor fixes): live-confirmed 79 rows across the 6 revenue_growth_*/eps_growth_*
periods (ARWR revenue_growth_1y among them) have >= the required number of real fiscal-year
data points yet still show "insufficient_history" - the bound-rejection branch in
_compute_period_growth() didn't distinguish itself from the too-few-datapoints branch. Fixed by
reusing "garbage_metric_value_implausible_growth_rate" - the same label this file's
earnings_growth_4q_avg/eps_growth_stability/quarterly_growth_momentum blocks already use for the
identical MAX_PLAUSIBLE_GROWTH_PCT bound rejection - instead of a fourth name for the same fact.
Already mapped in lambda/api/routes/scores.py's "Implausible / rejected value" coverage
category, so no categorization change needed.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_implausible_revenue_growth_reports_distinct_reason_not_insufficient_history():
    loader = _make_loader()
    # ARWR-shaped: 2 real positive-revenue fiscal years, ratio 829.45M/22.72M ~ 36.5x
    # (3652% CAGR) - way past the 2000% bound, but NOT a data-history gap.
    income_rows = [
        (2025, 829_448_000.0, None, None, None),
        (2024, 22_720_000.0, None, None, None),
    ]

    result = loader._compute_growth_metrics("ARWR", income_rows)

    assert result["revenue_growth_1y"] is None
    assert result["revenue_growth_1y_unavailable_reason"] == "garbage_metric_value_implausible_growth_rate"


def test_too_few_datapoints_still_reports_insufficient_history():
    loader = _make_loader()
    income_rows = [(2026, 100.0, None, None, None)]  # only 1 fiscal year - genuinely not enough

    result = loader._compute_growth_metrics("SOLO", income_rows)

    assert result["revenue_growth_1y"] is None
    assert result["revenue_growth_1y_unavailable_reason"] == "insufficient_history"


def test_plausible_growth_still_computes_normally():
    loader = _make_loader()
    income_rows = [
        (2025, 120.0, None, None, None),
        (2024, 100.0, None, None, None),
    ]

    result = loader._compute_growth_metrics("NORM", income_rows)

    assert result["revenue_growth_1y"] is not None
    assert result["revenue_growth_1y_unavailable_reason"] is None


def test_implausible_eps_growth_reports_distinct_reason(monkeypatch):
    loader = _make_loader()
    # Same shape for EPS - real 2 years of positive EPS history, ratio well past the bound
    # and past min_abs_target so it isn't caught by the immaterial-base guard instead.
    income_rows = [
        (2025, None, None, None, 45.0),
        (2024, None, None, None, 1.0),
    ]

    result = loader._compute_growth_metrics("EPSJUMP", income_rows)

    assert result["eps_growth_1y"] is None
    assert result["eps_growth_1y_unavailable_reason"] == "garbage_metric_value_implausible_growth_rate"
