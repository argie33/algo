"""MSCI's real Quality Index "Earnings Variability" fundamental variable, added 2026-09-16
(factor-purity /goal session: "we do what the industry does only").

Source: MSCI Quality Indexes Methodology, May 2022 (msci.com/eqb/methodology/meth_docs/
MSCI_Quality_Indexes_Methodology_May2022.pdf), Appendix I "Calculation of Fundamental
Variables": "Earnings Variability is defined as the standard deviation of y-o-y earnings per
share growth over the last five fiscal years." This is Quality's third fundamental variable
alongside ROE and Debt-to-Equity (Section 2.2) - MSCI's Quality Score is a composite Z-Score
average of exactly these three, nothing else (Appendix II: ROE missing -> not scored; D/E or
Earnings Variability missing alone -> composite uses the other two).

Reuses the same (fiscal_year, value) pair shape as loaders/helpers/growth_trend.py's
ols_growth_trend - same underlying annual diluted_eps history, different transform (YoY growth
rate dispersion here, not an OLS trend slope) - kept in its own module rather than added to
growth_trend.py since it's sourced from a different MSCI methodology document (Quality, not
Growth/Value) and scores a different pillar.
"""

import statistics
from itertools import pairwise
from typing import Any

from utils.type_conversion import safe_float

MAX_YEARS_FOR_VARIABILITY = 5
# MSCI's own text doesn't state an explicit minimum (unlike the Growth trend formula's stated
# "a minimum of the last four... are needed") - 3 fiscal years is this module's own floor,
# the smallest window that yields 2 YoY growth observations, the minimum for a population
# stdev to be a real (not trivially zero) dispersion measure.
MIN_YEARS_FOR_VARIABILITY = 3


def earnings_variability(fiscal_year_values: list[tuple[int, float]]) -> float | None:
    """MSCI's Earnings Variability: standard deviation of year-over-year EPS growth rates over
    the most recent MAX_YEARS_FOR_VARIABILITY (5) fiscal years of diluted EPS.

    `fiscal_year_values`: (fiscal_year, diluted_eps) pairs, any order, one row per fiscal year
    (caller-side dedupe/latest-restatement-wins already applied, same convention as
    growth_trend.ols_growth_trend). Returns None when fewer than MIN_YEARS_FOR_VARIABILITY
    years are available, or when every year-over-year pair has a zero prior-year base (growth
    undefined) - a distinct "cannot compute" state, never a fabricated 0.0.

    Growth rate between consecutive fiscal years uses an absolute-value denominator
    ((curr - prior) / abs(prior)) - the standard sign-safe growth convention, consistent with
    this codebase's other period-growth helpers - and is population standard deviation
    (statistics.pstdev), matching this codebase's own established z-score convention elsewhere
    (loaders/helpers/factor_normalization.py).
    """
    if len(fiscal_year_values) < MIN_YEARS_FOR_VARIABILITY:
        return None

    recent = sorted(fiscal_year_values, key=lambda fy_v: fy_v[0])[-MAX_YEARS_FOR_VARIABILITY:]
    growth_rates: list[float] = []
    for (_, prior_eps), (_, curr_eps) in pairwise(recent):
        if prior_eps == 0:
            continue
        growth_rates.append((curr_eps - prior_eps) / abs(prior_eps))

    if len(growth_rates) < 2:
        return None
    return statistics.pstdev(growth_rates) * 100.0


def earnings_variability_from_income_rows(income_rows: list[Any]) -> tuple[float | None, str | None]:
    """Adapter over `earnings_variability()` for load_value_quality_growth_metrics.py's
    already-fetched multi-year `income_rows` (ordered fiscal_year DESC; row[0]=fiscal_year,
    row[8]=diluted_eps - same columns loaders/helpers/vqg_growth.py's diluted_eps_values already
    reads for eps_growth_trend_5y, not duplicated here since that assembly lives in a different
    function with its own split-guard logic this simpler metric doesn't need). Extracted into
    this module (rather than a method on the loader itself) purely to keep
    load_value_quality_growth_metrics.py under this repo's file-size ratchet.

    Returns (value, unavailable_reason) - reason only meaningful when value is None.
    """
    diluted_eps_values: list[tuple[int, float]] = []
    for row in income_rows:
        fiscal_year = int(row[0]) if row[0] is not None else None
        diluted_eps = safe_float(row[8], "earnings_variability.diluted_eps", allow_none=True) if len(row) > 8 else None
        if fiscal_year is not None and diluted_eps is not None:
            diluted_eps_values.append((fiscal_year, diluted_eps))
    value = earnings_variability(diluted_eps_values)
    if value is None:
        return None, "insufficient_history"
    return value, None
