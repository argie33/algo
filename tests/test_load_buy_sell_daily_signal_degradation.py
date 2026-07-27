#!/usr/bin/env python3
"""Regression test for load_buy_sell_daily.py's post-run signal degradation sanity check.

The original check averaged total_signals over COUNT(DISTINCT date) across the table's
ENTIRE history. With enough accumulated history, that all-time average can never fall
below the 150/day threshold again no matter how many consecutive days produce zero new
signals - it's diluted by every healthy historical day. This masked buy_sell_daily
sitting frozen at a stale date for 9+ consecutive days (2026-07-17 through 2026-07-24)
while the loader kept reporting status=success the whole time. Fixed to check only the
most recent date's signal count and to raise instead of just logging critical.
"""

from unittest.mock import MagicMock

import pytest

from loaders.load_buy_sell_daily import _check_signal_degradation


def _make_cursor(latest_date, latest_day_count):
    cur = MagicMock()
    cur.fetchone.side_effect = [(latest_date,), (latest_day_count,)]
    return cur


def test_frozen_table_with_healthy_historical_average_still_raises():
    """Reproduces the exact masked scenario: MAX(date) is stale and today's (i.e. the
    most recent persisted date's) count is 0, even though the table has plenty of
    historical data that would have kept an all-time average comfortably above 150/day."""
    cur = _make_cursor(latest_date="2026-07-17", latest_day_count=0)

    with pytest.raises(RuntimeError, match="SIGNAL_DEGRADATION_DETECTED"):
        _check_signal_degradation(cur)


def test_low_but_nonzero_recent_day_count_raises():
    cur = _make_cursor(latest_date="2026-07-24", latest_day_count=17)

    with pytest.raises(RuntimeError, match="SIGNAL_DEGRADATION_DETECTED"):
        _check_signal_degradation(cur)


def test_healthy_recent_day_count_does_not_raise():
    cur = _make_cursor(latest_date="2026-07-24", latest_day_count=1144)

    _check_signal_degradation(cur)  # must not raise


def test_empty_table_does_not_raise():
    """No rows at all is a different failure mode (handled elsewhere) - this check
    only concerns itself with degradation once there's at least one date to compare."""
    cur = MagicMock()
    cur.fetchone.side_effect = [(None,)]

    _check_signal_degradation(cur)  # must not raise
