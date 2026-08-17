"""Regression test for the 2026-08-17 fix: market.py's reap-vs-genuine split (see
test_freshness_panel_reaped_errors_not_alarming.py for the panel-rendering half) used to call
every "[REAPED]"/"[MANUAL REAP" loader "self-healing" with no time bound.

Live-confirmed the same day: a mass-reap at 05:32:23 UTC hit ~30 tables across all 4 local
pipelines. Watchers got queued to retry morning/metrics/reference, but nobody queued one for
"signals" (stock_scores, stability_metrics, buy_sell_daily, signal_quality_scores) - those 4
tables sat FAILED for 8+ hours while the dashboard kept labeling them "self-healing" the whole
time. There is no cron/scheduled-pass guarantee locally, so "self-healing" was an assumption,
not a fact the code could back up past some grace window.

_reaped_recently now requires the reap to be within REAPED_SELF_HEAL_GRACE (2h) of `now_utc` to
still count as "reaped_only" (dim, non-alarming); older reaps fall back to counting as genuine.
"""

import importlib
from datetime import datetime, timedelta, timezone

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")
REAPED_SELF_HEAL_GRACE = market_module.REAPED_SELF_HEAL_GRACE
_reaped_recently = market_module._reaped_recently

NOW = datetime(2026, 8, 17, 13, 41, 0, tzinfo=timezone.utc)


def test_recent_reap_still_counts_as_self_healing():
    row = {"error_message": "[REAPED] Stuck in RUNNING since ...", "execution_started": NOW - timedelta(minutes=30)}
    assert _reaped_recently(row, NOW) is True


def test_reap_past_grace_window_no_longer_counts_as_self_healing():
    """The exact bug: signals pipeline's reap sat 8h old with zero active retry - must read
    as genuine, not self-healing, once it's past the grace window."""
    row = {"error_message": "[REAPED] Stuck in RUNNING since ...", "execution_started": NOW - timedelta(hours=8)}
    assert _reaped_recently(row, NOW) is False


def test_manual_reap_marker_also_respects_grace_window():
    row = {"error_message": "[MANUAL REAP] Stuck RUNNING ...", "execution_started": NOW - timedelta(hours=8)}
    assert _reaped_recently(row, NOW) is False


def test_boundary_exactly_at_grace_window_still_counts():
    row = {"error_message": "[REAPED] Stuck in RUNNING since ...", "execution_started": NOW - REAPED_SELF_HEAL_GRACE}
    assert _reaped_recently(row, NOW) is True


def test_genuine_error_never_counts_regardless_of_recency():
    row = {"error_message": "HTTPError: 500 Internal Server Error", "execution_started": NOW - timedelta(minutes=1)}
    assert _reaped_recently(row, NOW) is False


def test_missing_execution_started_does_not_assume_still_healing():
    row = {"error_message": "[REAPED] Stuck in RUNNING since ...", "execution_started": None}
    assert _reaped_recently(row, NOW) is False


def test_naive_datetime_treated_as_utc_not_crash():
    """execution_started comes back tz-naive from some code paths - must not raise."""
    row = {
        "error_message": "[REAPED] Stuck in RUNNING since ...",
        "execution_started": datetime(2026, 8, 17, 13, 30, 0),
    }
    assert _reaped_recently(row, NOW) is True
