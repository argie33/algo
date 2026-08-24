"""Regression test: Orchestrator._check_loader_health()'s reference_day computation
(`now_et.hour >= 16`) is the same early-close-blind pattern already found and fixed in
phase1_data_freshness.py and phase8_entry_execution.py this session.

2026-07-02 (day before Independence Day) is a NYSE/NASDAQ early close - real close 1:00 PM
ET, not 4:00 PM. At 2:00 PM ET on that day, today's close has already posted and a loader
whose last real run was still yesterday's (2026-07-01) close is missing today's data and
should be flagged STALE. Under the old hardcoded `hour >= 16` check, reference_day stayed
"yesterday" until 4 PM, anchoring the staleness threshold one full trading day too early and
letting yesterday's data pass as fresh for the 3 hours between the real close and the old
hardcoded cutoff.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    self = object.__new__(Orchestrator)
    self.alerts = MagicMock()
    return self


def _run_check(rows, fake_utc_now):
    cur = MagicMock()
    cur.fetchall.return_value = rows

    @contextmanager
    def _ctx(role, timeout=5):
        yield cur

    with (
        patch("algo.orchestration.orchestrator.DatabaseContext", side_effect=_ctx),
        patch("algo.orchestration.orchestrator.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = fake_utc_now
        mock_dt.combine = datetime.combine  # delegate to the real implementation
        Orchestrator._check_loader_health(_fake_self())


def test_yesterdays_close_flagged_stale_after_early_close_at_2pm():
    """The core bug: on an early-close day, by 2 PM the real trading day has already ended -
    only having yesterday's close on file is missing today's data and must be flagged STALE,
    not silently treated as still-current INTRADAY data."""
    wednesday_close_naive = datetime(2026, 7, 1, 17, 0, 0)  # naive ET, matches DB convention
    thursday_2pm_utc = datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc)  # 2:00 PM ET on the early-close day

    with patch("logging.Logger.warning") as mock_warn:
        _run_check(
            rows=[("price_daily", "completed", wednesday_close_naive, 100.0, 5000, 5000)],
            fake_utc_now=thursday_2pm_utc,
        )

    stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
    assert stale_warnings, "Yesterday's close must be flagged stale by 2 PM on an early-close day"


def test_yesterdays_close_still_fresh_before_the_early_close():
    """Sanity check: before the real 1 PM close, yesterday's data is still the correct
    INTRADAY-context baseline and must not be flagged stale."""
    wednesday_close_naive = datetime(2026, 7, 1, 17, 0, 0)
    thursday_11am_utc = datetime(2026, 7, 2, 15, 0, tzinfo=timezone.utc)  # 11:00 AM ET, still open

    with patch("logging.Logger.warning") as mock_warn:
        _run_check(
            rows=[("price_daily", "completed", wednesday_close_naive, 100.0, 5000, 5000)],
            fake_utc_now=thursday_11am_utc,
        )

    stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
    assert not stale_warnings, "Yesterday's close must not be flagged stale before the early close"
