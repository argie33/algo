#!/usr/bin/env python3
"""Regression test for a 2026-07-27 fix in algo/orchestrator/phase7_signal_generation.py::
_check_critical_dependencies(): the zero-signal and severe-collapse anomaly checks
(CRITICAL HALT if buy_sell_daily's most recent trading day has 0, or <_SIGNAL_COUNT_ANOMALY_
THRESHOLD, real BUY signals - the guard against a silent upstream technical_data_daily/
buy_sell_daily loader failure) were gated behind `latest_buysell_date >= run_date -
timedelta(days=1)`.

By the point this code runs, an earlier check in the same function has already halted if
latest_buysell_date were genuinely too stale - so latest_buysell_date is always confirmed to
be the correct current reference day. The extra flat calendar-day gate added nothing but a
bug: on a Monday, the real latest_buysell_date (Friday) is always < Sunday (run_date - 1 day),
so the gate was always False and the anomaly check silently never fired across every weekend -
the exact opposite-direction failure mode of the Phase 7 lookback bug fixed earlier the same
session (that one silently found nothing; this one silently missed a real problem). Fixed by
removing the redundant, buggy gate - the checks now always run once reached.
"""

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase7_signal_generation import _check_critical_dependencies


def _mock_cursor(stock_scores_count, exposure_row, buysell_freshness_row, today_count, loader_status_row=("COMPLETED", None, 999999)):
    cur = MagicMock()
    cur.fetchone.side_effect = [
        (stock_scores_count,),
        exposure_row,
        loader_status_row,
        buysell_freshness_row,
        (today_count,),
    ]
    return cur


def _patched_db(cur):
    @contextmanager
    def _ctx(role):
        yield cur

    return patch("algo.orchestrator.phase7_signal_generation.DatabaseContext", side_effect=_ctx)


class TestPhase7ZeroSignalAnomalyWeekendGap:
    def test_monday_with_zero_signals_on_fridays_data_still_halts(self):
        """The core bug: Monday run_date, Friday's real latest_buysell_date has 0 BUY
        signals (a genuine upstream failure) - must halt, not silently pass through."""
        monday = date(2026, 7, 27)
        friday = date(2026, 7, 24)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, monday, False, None),
            buysell_freshness_row=(friday, 0),  # MAX(date), COUNT(*) - only 0 BUY signals ever
            today_count=0,
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(monday, MagicMock())

        assert is_ok is False, (
            f"Expected a HALT for zero BUY signals on Friday (the real most-recent trading "
            f"day), even though today is Monday, got: is_ok={is_ok}, msg={msg}"
        )
        assert "ZERO BUY signals" in (msg or "")

    def test_monday_with_severe_collapse_on_fridays_data_still_halts(self):
        """Same bug, the non-zero severe-collapse branch: 5 signals (< anomaly floor) on
        Friday must still halt on the following Monday."""
        monday = date(2026, 7, 27)
        friday = date(2026, 7, 24)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, monday, False, None),
            buysell_freshness_row=(friday, 5),
            today_count=5,
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(monday, MagicMock())

        assert is_ok is False
        assert "anomaly floor" in (msg or "")

    def test_monday_with_healthy_signal_count_does_not_halt(self):
        """Sanity check: a normal, healthy Friday signal count must NOT halt on Monday."""
        monday = date(2026, 7, 27)
        friday = date(2026, 7, 24)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, monday, False, None),
            buysell_freshness_row=(friday, 301),
            today_count=301,
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(monday, MagicMock())

        assert is_ok is True, f"Expected a healthy 301-signal Friday to pass on Monday, got: {msg}"


class TestPhase7BuySellLoaderOwnStatusGate:
    """Regression coverage for the 2026-08-10 fix: live-reproduced buy_sell_daily loader
    killed mid-run (subprocess exit 143), left status=FAILED with only 121/4623 signals
    written. The count-based anomaly floor happened to catch that specific case, but a
    milder partial write could land above the floor while the loader itself is still
    FAILED or actively RUNNING (mid-write race). Phase 7 now checks the loader's own
    status directly instead of trusting the raw signal count alone."""

    def test_failed_loader_status_halts_regardless_of_healthy_count(self):
        today = date(2026, 8, 10)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, today, False, None),
            buysell_freshness_row=(today, 500),  # count alone looks healthy
            today_count=500,
            loader_status_row=("FAILED", "failsafe retry subprocess exited with code 143", 60),
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(today, MagicMock())

        assert is_ok is False, f"Expected a HALT when the loader's own status is FAILED, got: is_ok={is_ok}"
        assert "FAILED" in (msg or "")

    def test_live_running_status_halts_as_mid_write_race(self):
        today = date(2026, 8, 10)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, today, False, None),
            buysell_freshness_row=(today, 500),
            today_count=500,
            loader_status_row=("RUNNING", None, 60),  # started 60s ago - live write in progress
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(today, MagicMock())

        assert is_ok is False, f"Expected a HALT for a live RUNNING loader (mid-write race), got: is_ok={is_ok}"
        assert "RUNNING" in (msg or "")

    def test_stale_running_status_falls_through_to_count_check(self):
        """A RUNNING row that's hours old is more likely an orphaned status from a past
        crash than a real live write - should not block forever until reaped."""
        today = date(2026, 8, 10)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, today, False, None),
            buysell_freshness_row=(today, 500),
            today_count=500,
            loader_status_row=("RUNNING", None, 20000),  # started ~5.5h ago - stale/orphaned
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(today, MagicMock())

        assert is_ok is True, f"Expected a stale RUNNING row to fall through to the healthy count check, got: {msg}"

    def test_completed_loader_status_does_not_block_healthy_count(self):
        today = date(2026, 8, 10)
        cur = _mock_cursor(
            stock_scores_count=5000,
            exposure_row=(58.0, today, False, None),
            buysell_freshness_row=(today, 500),
            today_count=500,
            loader_status_row=("COMPLETED", None, 300),
        )

        with _patched_db(cur):
            is_ok, msg = _check_critical_dependencies(today, MagicMock())

        assert is_ok is True, f"Expected COMPLETED loader status with a healthy count to pass, got: {msg}"
