"""Regression test: peg_ratio_reason_from_eps_history() must distinguish "PEG not meaningful
because earnings declined/turned negative" from a genuine SEC data gap.

Bug (found 2026-08-18, live audit): when pe_ratio was present but peg_ratio was NULL, the
reason was always hardcoded "missing_sec_data" - identical to what an actual SEC extraction
gap gets. load_sec_valuations.py only computes peg_ratio when
growth_rate = (ttm_eps - prior_year_eps) / |prior_year_eps| is > 0; a real, profitable company
whose earnings declined year-over-year (or that just turned profitable after a prior-year
loss) legitimately has no meaningful PEG, same "not applicable" class as unprofitable_stock/
non_dividend_paying_stock elsewhere in this file. Live audit: 1273 of 1282 universe rows in
this exact state have declining or newly-positive EPS - only 8 are genuine
missing-prior-year-EPS gaps.
"""

from loaders.load_value_quality_growth_metrics import peg_ratio_reason_from_eps_history


def test_declining_earnings_reports_negative_earnings_growth() -> None:
    # FY2025 EPS 3.00, down from FY2024's 5.00 - a real decline, not a data gap.
    eps_rows = [(2025, 3.00), (2024, 5.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "negative_earnings_growth"


def test_newly_profitable_after_prior_year_loss_reports_negative_earnings_growth() -> None:
    # FY2025 EPS 1.00 (profitable), FY2024 EPS -2.00 (loss) - growth_rate is undefined in the
    # usual sense against a negative base, same "not applicable" case.
    eps_rows = [(2025, 1.00), (2024, -2.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "negative_earnings_growth"


def test_flat_earnings_reports_negative_earnings_growth() -> None:
    # ttm_eps == prior_eps: growth_rate == 0, not > 0, so PEG still isn't computed.
    eps_rows = [(2025, 4.00), (2024, 4.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "negative_earnings_growth"


def test_genuine_growth_reports_missing_sec_data() -> None:
    # Real positive growth (5.00 -> 3.00 reversed: 3.00 -> 5.00) - PEG should have been
    # computable from this history, so if it's still NULL something else blocked it (e.g. the
    # 10000 bounds rejection) - stays the generic reason, not misattributed to growth.
    eps_rows = [(2025, 5.00), (2024, 3.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "missing_sec_data"


def test_only_one_year_of_eps_history_reports_missing_sec_data() -> None:
    # Can't compute a growth rate without a prior year at all - genuine gap.
    eps_rows = [(2025, 5.00)]
    assert peg_ratio_reason_from_eps_history(eps_rows) == "missing_sec_data"


def test_no_eps_history_reports_missing_sec_data() -> None:
    assert peg_ratio_reason_from_eps_history([]) == "missing_sec_data"
