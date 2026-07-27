#!/usr/bin/env python3
"""Regression test for a live data-integrity bug found in market_health_daily:

8 historical rows (2026-07-02 to 2026-07-14) had put_call_ratio_data_unavailable=False
while put_call_ratio_unavailable_reason='unable to fetch after retries' - a failed fetch
recorded as if it were valid data (same stale ratio value, 2.0531, repeated across many
different days). The string that produced those rows no longer exists anywhere in the
current codebase (an older PutCallRatioFetcher implementation, since rewritten), and the
bad historical flags were corrected directly in the DB. This test locks in the invariant
so the current _fetch_market_health() logic can't regress into writing the same
contradiction again: whenever put_call_ratio_unavailable_reason is set, data_unavailable
must be True, and data_unavailable=False must never carry a reason.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest


def _make_loader():
    from loaders.load_market_status_daily import MarketStatusDailyLoader

    loader = MarketStatusDailyLoader()
    loader._vix_fetcher = MagicMock()
    loader._vix_fetcher.fetch.return_value = {"2026-07-17": {"vix_close": 15.0}}
    loader._breadth_fetcher = MagicMock()
    loader._breadth_fetcher.fetch.return_value = {
        "2026-07-17": {"advance_decline_ratio": 1.2, "new_highs_count": 10, "new_lows_count": 2}
    }
    loader._breadth_fetcher.fetch_up_volume_percent.return_value = {"data_unavailable": True}
    loader._yield_curve_fetcher = MagicMock()
    loader._yield_curve_fetcher.fetch.return_value = {"data_unavailable": True, "reason": "test_unavailable"}
    return loader


def _assert_no_contradiction(result: dict) -> None:
    unavailable = result["put_call_ratio_data_unavailable"]
    reason = result["put_call_ratio_unavailable_reason"]
    if reason is not None:
        assert unavailable is True, (
            f"put_call_ratio_unavailable_reason={reason!r} set but "
            f"put_call_ratio_data_unavailable={unavailable!r} - a failed/unavailable fetch "
            "must never be recorded as available data (see module docstring)."
        )
    if unavailable is False:
        assert reason is None, (
            f"put_call_ratio_data_unavailable=False but reason={reason!r} is set - "
            "a reason implies the fetch did NOT succeed."
        )


class TestPutCallRatioAvailabilityInvariant:
    def test_fetcher_raises_exception(self):
        loader = _make_loader()
        loader._put_call_fetcher = MagicMock()
        loader._put_call_fetcher.fetch.side_effect = RuntimeError("simulated network failure")

        result = loader._fetch_market_health(date(2026, 7, 17))
        assert result["put_call_ratio"] is None
        _assert_no_contradiction(result)

    def test_fetcher_returns_unavailable_with_reason(self):
        loader = _make_loader()
        loader._put_call_fetcher = MagicMock()
        loader._put_call_fetcher.fetch.return_value = {
            "data_unavailable": True,
            "reason": "unable to fetch after retries",
        }

        result = loader._fetch_market_health(date(2026, 7, 17))
        assert result["put_call_ratio"] is None
        _assert_no_contradiction(result)

    def test_fetcher_returns_valid_ratio(self):
        loader = _make_loader()
        loader._put_call_fetcher = MagicMock()
        loader._put_call_fetcher.fetch.return_value = {
            "data_unavailable": False,
            "put_call_ratio": 0.95,
        }

        result = loader._fetch_market_health(date(2026, 7, 17))
        assert result["put_call_ratio"] == 0.95
        _assert_no_contradiction(result)
