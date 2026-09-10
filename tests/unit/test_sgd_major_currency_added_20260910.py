"""Regression test for the 2026-09-10 fix (goal session: SEC/XBRL missing-data count under
500, dcf_fcf_unavailable_reason='missing_cash_flow_data' investigation): SGD (Singapore
Dollar) added to MAJOR_CURRENCIES.

Live-confirmed via BLIV (BeLive Holdings, CIK 0001982448): real ifrs-full:
CashFlowsFromUsedInOperatingActivities and capex-alias facts tagged every fiscal year
2022-2024, exclusively under unit="SGD", no USD-tagged alternative - the blanket
non-USD currency guard was silently blocking dcf_fcf/operating_cash_flow/free_cash_flow.
SGD/USD year-end moves stayed within a ~4% band 2019-2024 (live-verified against
Frankfurter), tighter than every currency on this list except HKD's currency-board peg.
"""

from utils.external.fx_rates import MAJOR_CURRENCIES


def test_sgd_is_a_major_currency() -> None:
    assert "SGD" in MAJOR_CURRENCIES
