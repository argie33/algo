#!/usr/bin/env python3
"""Regression test for a real, live display bug in dashboard/panels/trades.py's
_resolve_exit_reason: found while continuing the dashboard test-coverage sweep.

algo_trades has no separate exit_stage column - exit_reason is always exit_engine.py's full
human-readable sentence (e.g. "T1 exit: $115.00 >= $115.00 (1.5R)"), never the exact short
strings in _EXIT_REASON_SHORT (those keys - "t1_target"/"t1_hit"/"stop_loss" - match nothing
real). Only the substring fallback checks ever had a chance of matching real data, and most
exit_engine.py reason formats had no matching branch at all.

Live-measured against all 96 real closed trades in the local dev DB before this fix: 50/96
(52%) fell through to the unresolved "--" display code, including every T1/T2/T3 target hit,
every TIME exit, the "STOP hit:" format (as opposed to "STOP LOSS HIT:", the only stop variant
that matched), "Trailing stop hit:", earnings-blackout exits, and POSITION_SIZE_CONCENTRATION
force-exits. After the fix: 0/96 unresolved.
"""

import pytest

from dashboard.panels.trades import _compute_trade_grade, _resolve_exit_reason


class TestResolveExitReasonRealFormats:
    """Each case is a REAL exit_engine.py/position_monitor.py reason string format,
    verified against real historical algo_trades.exit_reason data or exit_engine.py's own
    f-string reason templates."""

    @pytest.mark.parametrize(
        "reason,expected_code",
        [
            ("T1 exit: $115.00 >= $115.00 (1.5R)", "T1"),
            ("T2 exit: $130.00 >= $130.00 (3R)", "T2"),
            ("T3 target hit: $140.00 >= $140.00 (4R) - FINAL EXIT", "T3"),
            ("TD Combo 13-count exhaustion (FULL EXIT, R=3.50)", "td13"),
            ("TD Sequential 9-count exhaustion (R=1.20)", "td9"),
            ("First Red Day: down 2.34% on heavy volume (R=2.50)", "1rd"),
            ("Climax run exhaustion: gained 25.0% in last 10d (R=5.20)", "clmx"),
            (
                "Market distribution: 4 dist days > 3  - reducing 50% of profitable position, stop raised to breakeven",
                "dist",
            ),
            ("TIME exit: 60 days >= 60 max", "time"),
            (
                "STOP hit: $100.20 <= $100.52 (hard capital preservation - not subject to min_hold_days)",
                "stop",
            ),
            (
                "Trailing stop hit: $150.00 <= $140.00 (locked-in gain, stop raised above entry $100.00)",
                "stop",
            ),
            ("STOP LOSS HIT: price $102.99 <= stop $103.04", "stop"),
            ("Earnings in 1 day(s) - flatten before report", "erng"),
            ("Earnings in 0 day(s) - flatten before report", "erng"),
            ("POSITION_SIZE_CONCENTRATION: 6.1% > 5% limit", "conc"),
            ("portfolio_rotation_safety_check", "rot"),
            ("RS line broke below 50-DMA (loser: R=0.16)", "rs"),
            ("2 health flags: RS_WEAKENING, EARNINGS_IN_3D", "hlth"),
        ],
    )
    def test_real_reason_format_resolves_correctly(self, reason, expected_code):
        assert _resolve_exit_reason(reason) == expected_code

    def test_none_returns_placeholder(self):
        assert _resolve_exit_reason(None) == "--"

    def test_truly_unrecognized_reason_falls_back_to_placeholder(self):
        assert _resolve_exit_reason("some brand new reason format never seen before") == "--"

    def test_case_insensitive_matching(self):
        assert _resolve_exit_reason("t1 EXIT: $1 >= $1 (1.5R)") == "T1"


class TestComputeTradeGrade:
    def test_boundaries(self):
        assert _compute_trade_grade(2.0) == "A"
        assert _compute_trade_grade(1.999) == "B"
        assert _compute_trade_grade(1.0) == "B"
        assert _compute_trade_grade(0.999) == "C"
        assert _compute_trade_grade(0.0) == "C"
        assert _compute_trade_grade(-0.001) == "D"
        assert _compute_trade_grade(-5.0) == "D"

    def test_none_returns_placeholder(self):
        assert _compute_trade_grade(None) == "--"
