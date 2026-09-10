"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
peg_ratio_reason_from_eps_history() now mirrors sec_valuations_ratios.py's
_compute_peg_ratio() own low-base-year rejection - a real, positive prior_year_eps that's a
one-off litigation/impairment trough relative to the filer's own EPS history produces an
artificially huge growth_rate, which _compute_peg_ratio() correctly rejects (returns None
instead of a deflated near-zero PEG) but this reason function didn't know about, so every
affected symbol fell through to the generic "missing_sec_data" instead of the correct
"peg_ratio_low_base_effect" (see peg_ratio_low_base_effect in memory for the GILD/AA live
evidence that established this bug class on the value side).
"""

from loaders.load_value_quality_growth_metrics import peg_ratio_reason_from_eps_history


def test_trough_year_reports_low_base_effect() -> None:
    # GILD-shaped: FY2024 (prior) EPS=0.38 (real litigation-charge trough), FY2025 (ttm)
    # EPS=6.84 - growth_rate = (6.84-0.38)/0.38*100 = 1700%, median of other real years
    # (4.96, 3.66, 4.54) = 4.54, 0.38 < 0.25*4.54=1.135 - trough confirmed.
    eps_rows = [(2025, 6.84), (2024, 0.38)]
    other_positive_eps = [4.96, 3.66, 4.54]
    assert peg_ratio_reason_from_eps_history(eps_rows, other_positive_eps) == "peg_ratio_low_base_effect"


def test_growth_under_300_pct_does_not_trigger_low_base_check() -> None:
    # Real, plausible 50% growth - even with a thin other_positive_eps history, the growth_rate
    # pre-filter (>300%) never fires, so this stays the generic reason.
    eps_rows = [(2025, 4.50), (2024, 3.00)]
    other_positive_eps = [0.10, 0.20]
    assert peg_ratio_reason_from_eps_history(eps_rows, other_positive_eps) == "missing_sec_data"


def test_high_growth_without_enough_other_history_stays_generic() -> None:
    # growth_rate is explosive (>300%) but fewer than 2 other real positive EPS years on file -
    # _compute_peg_ratio()'s own median calc can't run either, so no trough verdict is possible.
    eps_rows = [(2025, 5.00), (2024, 0.50)]
    other_positive_eps: list[float] = [4.00]
    assert peg_ratio_reason_from_eps_history(eps_rows, other_positive_eps) == "missing_sec_data"


def test_high_growth_not_actually_a_trough_stays_generic() -> None:
    # growth_rate > 300% but prior_year_eps is NOT anomalously low relative to its own history
    # (0.50 is not < 25% of the median of 0.40/0.60/0.55=0.55 -> threshold 0.1375) - real
    # explosive growth, not a low-base artifact.
    eps_rows = [(2025, 3.00), (2024, 0.50)]
    other_positive_eps = [0.40, 0.60, 0.55]
    assert peg_ratio_reason_from_eps_history(eps_rows, other_positive_eps) == "missing_sec_data"


def test_no_other_positive_eps_passed_keeps_prior_behavior() -> None:
    # Existing callers/tests that don't pass other_positive_eps at all must be unaffected.
    eps_rows = [(2025, 5.00), (2024, 3.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "missing_sec_data"
