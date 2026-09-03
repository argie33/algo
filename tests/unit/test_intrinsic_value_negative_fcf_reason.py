"""Regression test: intrinsic_value_reason_from_fcf_yield() must distinguish "DCF not
meaningful because the company burned cash" from a genuine implausible-result rejection.

Bug (found 2026-08-18, goal session value_metrics audit): when fcf_yield was present but
intrinsic_value_per_share was NULL, the reason was always "implausible_dcf_result" - the old
comment assumed fcf_yield being present implied FCF was positive, but fcf_yield only requires
being within [-1000%, 1000%] of market cap, not being positive, and
load_sec_valuations.py's _compute_dcf_intrinsic_value's very first gate is `fcf <= 0`. Live
audit: 100% of the 2184 universe rows in this exact state (2177 negative + 7 zero fcf_yield)
were the negative/zero-FCF case, not a genuinely implausible computed result.
"""

from loaders.load_value_quality_growth_metrics import intrinsic_value_reason_from_fcf_yield


def test_negative_fcf_yield_reports_negative_free_cash_flow() -> None:
    assert intrinsic_value_reason_from_fcf_yield(-12.5) == "negative_free_cash_flow"


def test_zero_fcf_yield_reports_negative_free_cash_flow() -> None:
    # fcf <= 0 in _compute_dcf_intrinsic_value rejects zero too, not just negative.
    assert intrinsic_value_reason_from_fcf_yield(0.0) == "negative_free_cash_flow"


def test_positive_fcf_yield_reports_implausible_dcf_result() -> None:
    # FCF was usable and positive - if intrinsic_value_per_share is still NULL, something else
    # (e.g. the MAX_INTRINSIC_VALUE_PER_SHARE bounds rejection) is the real cause.
    assert intrinsic_value_reason_from_fcf_yield(4.2) == "implausible_dcf_result"


def test_missing_fcf_yield_reports_missing_cash_flow_data() -> None:
    assert intrinsic_value_reason_from_fcf_yield(None) == "missing_cash_flow_data"


# Regression (found 2026-09-03, SEC/XBRL sweep): fcf_yield is None used to always collapse to
# the generic "missing_cash_flow_data" label, discarding fcf_yield_unavailable_reason's own
# already-specific cause (same "sibling reason propagation" bug class as total_debt's
# sec_valuations-reason fix, bf82fc6d0) - 388 live universe rows split across 3 real reasons
# that were all being reported identically.
def test_missing_fcf_yield_propagates_specific_reason_when_given() -> None:
    assert (
        intrinsic_value_reason_from_fcf_yield(None, "capex_never_tagged_in_recent_filings")
        == "capex_never_tagged_in_recent_filings"
    )
    assert (
        intrinsic_value_reason_from_fcf_yield(None, "no_recent_free_cash_flow_reported")
        == "no_recent_free_cash_flow_reported"
    )
    assert intrinsic_value_reason_from_fcf_yield(None, "missing_sec_data") == "missing_sec_data"


def test_missing_fcf_yield_falls_back_to_generic_label_when_no_reason_given() -> None:
    # Direct callers that don't have fcf_yield_unavailable_reason on hand (e.g. tests, or a
    # future caller with no adjacent reason field) still get a real string, not None.
    assert intrinsic_value_reason_from_fcf_yield(None, None) == "missing_cash_flow_data"
