#!/usr/bin/env python3
"""Regression test for the 2026-08-19 recalibration of Phase 7's buy_sell_daily signal-count
floors in algo/orchestrator/phase7_signal_generation.py and validation_thresholds.py.

Commit bc0047231 (2026-08-18) fixed buy_sell_daily generation to be edge-triggered (fires only
on the crossover bar) instead of re-firing the same BUY/SELL every day a stock stayed beyond
its pivot - live-audited at 73%/64% of a day's BUY/SELL rows being re-fires, not fresh signals.
True daily counts dropped from the old "300-1000+/day" baseline to a correct ~80-250/day
(2026-08-18 post-fix: 105 BUY / 210 total). The pre-fix hardcoded floors (200 in
_check_per_day_signal_counts, the 100 floor in _calculate_dynamic_anomaly_threshold, and
BUY_SELL_DAILY_ANOMALY_THRESHOLD=250) would have halted the orchestrator on every normal
post-fix day. Lowered all three to 40.
"""

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase7_signal_generation import (
    _calculate_dynamic_anomaly_threshold,
    _check_per_day_signal_counts,
)
from algo.orchestrator.validation_thresholds import BUY_SELL_DAILY_ANOMALY_THRESHOLD


def _patched_db(cur):
    @contextmanager
    def _ctx(role):
        yield cur

    return patch("algo.orchestrator.phase7_signal_generation.DatabaseContext", side_effect=_ctx)


class TestPerDaySignalFloorRecalibration:
    def test_correct_post_fix_day_no_longer_halts(self):
        """105 BUY signals (real 2026-08-18 post-fix count) must NOT halt under the new floor -
        the old 200 floor would have halted on this genuinely healthy day."""
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 18), 105)]

        with _patched_db(cur):
            is_ok, msg = _check_per_day_signal_counts(date(2026, 8, 19), MagicMock())

        assert is_ok is True, f"Expected a healthy 105-signal post-fix day to pass, got: {msg}"

    def test_genuine_collapse_still_halts(self):
        """A real data-quality collapse (e.g. today's 42-signal technical_data_daily gap)
        must still halt under the lowered floor."""
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 18), 20)]

        with _patched_db(cur):
            is_ok, msg = _check_per_day_signal_counts(date(2026, 8, 19), MagicMock())

        assert is_ok is False
        assert "per-day threshold of 40" in (msg or "")


class TestDynamicAnomalyThresholdFloor:
    def test_low_but_correct_median_no_longer_forced_to_100(self):
        """A post-fix 30-day median of 120 (typical of the new ~80-250/day baseline) should
        yield threshold=40 (max(40, 120//3)), not the old max(100, ...) floor which would
        have forced 100 even though 40 correctly reflects 1/3 of true current signal volume."""
        cur = MagicMock()
        cur.fetchone.return_value = (120.0,)

        with _patched_db(cur):
            threshold = _calculate_dynamic_anomaly_threshold()

        assert threshold == 40, f"Expected max(40, 120/3)=40, got {threshold}"


def test_fallback_constant_lowered_to_match_post_fix_baseline():
    assert BUY_SELL_DAILY_ANOMALY_THRESHOLD == 40
