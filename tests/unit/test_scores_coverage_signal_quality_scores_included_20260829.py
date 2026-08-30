"""Regression test (2026-08-29, "full data" audit continuation): signal_quality_scores was
entirely missing from _get_scores_coverage's bare_reason_tables allowlist despite having a
real, populated `reason` column - live-confirmed 964,110 total reason rows (899K+ in the
active universe), invisible to the "Scores Data Coverage" dashboard the whole time. Its two
largest reason families ("[SIGNAL_QUALITY] ... No buy/sell signals found" /
"[VCP_NO_DATA] ... No VCP patterns found") embed the symbol/date range inline, so
_categorize_reason's `base = reason.split(":")[0]` is unique per symbol and never matches a
set literal - both mean "the underlying event genuinely hasn't occurred for this symbol yet"
(see buy_sell_daily's deliberately sparse/event-driven design,
[[buy_sell_daily_intermittent_71pct_shortfall_unresolved_20260821]]), the same
"Insufficient history" class as the table's other members, not a loader bug.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_signal_quality_no_buy_sell_signals_categorizes_as_insufficient_history():
    reason = (
        "[SIGNAL_QUALITY] Signal quality scoring failed for AVIR [2021-06-09 to 2026-07-20]: "
        "No buy/sell signals found. Signal quality assessment is REQUIRED for validating trades."
    )
    assert scores_mod._categorize_reason(reason) == "Insufficient history"


def test_vcp_no_data_categorizes_as_insufficient_history():
    reason = (
        "[VCP_NO_DATA] No VCP patterns found for DTST in date range 2026-03-04 to 2026-07-21. "
        "VCP pattern data unavailable."
    )
    assert scores_mod._categorize_reason(reason) == "Insufficient history"


def test_historical_row_predates_reason_tracking_categorizes_as_legitimate():
    assert scores_mod._categorize_reason("historical_row_predates_reason_tracking") == "Legitimate / not applicable"


def test_signal_quality_scores_in_bare_reason_tables():
    import inspect

    source = inspect.getsource(scores_mod._get_scores_coverage)
    assert "signal_quality_scores" in source
