"""MSCI's real "Long-term Historical Growth Trend" formula (LT his EPS G / LT his SPS G),
added 2026-09-16 (factor-purity /goal session: "we must prove it is what the industry guys like
the Barra or the Fama or whoever would do").

Source: MSCI Global Investable Market Value and Growth Index Methodology, February 2021
(msci.com/eqb/methodology/meth_docs/MSCI_GIMIVGMethod_Feb2021.pdf), Section 2.2.1: "For the
calculation of the LT his EPS G and LT his SPS G, first a regression (ordinary least square
method) is applied to the last 5 yearly restated EPS and SPS respectively: EPSt = a*t + b" (a =
slope, b = intercept, t = year expressed in number of months). "Then an average absolute EPS or
SPS is estimated... The growth trend is finally obtained as: LT his EPS G = a / SPE-tilde" where
SPE-tilde is the mean of |EPS| over the same window. "A minimum of the last four EPS or SPS
values are needed."

This is NOT a two-point CAGR (this repo's pre-existing revenue_growth_1y/3y/5y/eps_growth_1y/3y/5y
fields all are) - it's an OLS regression slope through every available year in the window, which
is far less sensitive to a single anomalous endpoint than a two-point calculation. Confirmed
against MSCI's own worked numerical example (same document, Appendix, "Calculating Long-term
historical EPS and SPS growth trend"): 5 fiscal year-end EPS values (-1.11, -0.51, 0.29, 0.92,
1.41) at t=0,12,24,36,48 months give a monthly slope a=0.05, ANNUALIZED (a*12) to 0.60, divided
by mean(|EPS|)=0.85, giving a growth trend of 70.6% - reproduced exactly by
`test_growth_trend.py`'s `test_matches_msci_own_worked_example_eps`/`..._sps`. The "annualize by
multiplying the monthly slope by 12" step is itself confirmed by that worked example (0.05*12 =
0.60), not this module's own invention.
"""

MIN_YEARS_FOR_TREND = 4
MAX_YEARS_FOR_TREND = 5


def years_in_trend_window(fiscal_year_values: list[tuple[int, float]]) -> list[int]:
    """The exact fiscal years `ols_growth_trend` would use for this series (its most recent
    MAX_YEARS_FOR_TREND years) - exposed so a caller can run a split/share-count-discontinuity
    check (this module has no such guard itself, and shouldn't grow one - that check needs
    shares-outstanding-by-year data this module never sees) against the SAME window, not a
    window that could silently drift out of sync with what the trend calculation itself uses.
    Returns fewer than MAX_YEARS_FOR_TREND years (or an empty list) exactly when
    ols_growth_trend would also return None for insufficient history - callers should still
    treat that as "no split check needed, there's no trend to protect."
    """
    return [fy for fy, _ in sorted(fiscal_year_values, key=lambda fy_v: fy_v[0])[-MAX_YEARS_FOR_TREND:]]


def ols_growth_trend(fiscal_year_values: list[tuple[int, float]]) -> float | None:
    """MSCI's LT his EPS/SPS G, generalized to either EPS or SPS (same formula, this repo also
    reuses it for revenue-per-share as a stand-in for SPS - see growth_scoring.py's own
    GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE for why revenue-per-share rather than raw revenue: MSCI's
    descriptor is explicitly SALES PER SHARE, not total sales, so per-share normalization matters
    for the same reason EPS (not net income) is used for the earnings leg).

    `fiscal_year_values`: (fiscal_year, value) pairs, any order, one row per fiscal year (a
    caller-side dedupe/latest-restatement-wins step happens before this - this function assumes
    each fiscal_year appears at most once). Returns None (not a 0.0 - this is a distinct "cannot
    compute" state, same as _compute_period_growth's own None-on-insufficient-history) when fewer
    than MIN_YEARS_FOR_TREND years are available or the average absolute value is zero (division
    undefined - a genuinely zero-EPS-on-average company, degenerate for a growth-TREND ratio
    regardless of the raw slope's sign).

    Uses at most the MOST RECENT MAX_YEARS_FOR_TREND fiscal years - MSCI's own "last 5 yearly
    restated EPS and SPS" - not the full available history, so a long-tenured symbol's trend
    reflects its recent trajectory the same way a young symbol's does, not diluted by an
    arbitrarily longer window just because more history happens to exist.
    """
    if len(fiscal_year_values) < MIN_YEARS_FOR_TREND:
        return None

    # Most recent MAX_YEARS_FOR_TREND fiscal years, oldest-first (order doesn't affect the OLS
    # slope itself, but t below is defined relative to the window's own earliest year so the
    # numbers stay small/numerically well-behaved rather than growing with the calendar).
    recent = sorted(fiscal_year_values, key=lambda fy_v: fy_v[0])[-MAX_YEARS_FOR_TREND:]
    base_year = recent[0][0]
    t = [(fy - base_year) * 12.0 for fy, _ in recent]  # "t, the year expressed in number of months"
    y = [v for _, v in recent]
    n = len(recent)

    mean_t = sum(t) / n
    mean_y = sum(y) / n
    numerator = sum((ti - mean_t) * (yi - mean_y) for ti, yi in zip(t, y, strict=True))
    denominator = sum((ti - mean_t) ** 2 for ti in t)
    if denominator == 0:
        # All years collapsed onto the same t (shouldn't happen with real distinct fiscal_years,
        # but guarded per this codebase's standard "never divide by a value that can be exactly
        # zero" convention).
        return None
    monthly_slope = numerator / denominator

    mean_abs_y = sum(abs(yi) for yi in y) / n
    if mean_abs_y == 0:
        return None

    annualized_slope = monthly_slope * 12.0
    return (annualized_slope / mean_abs_y) * 100.0
