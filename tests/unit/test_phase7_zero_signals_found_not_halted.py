#!/usr/bin/env python3
"""Regression test for a 2026-08-10 fix in algo/orchestrator/phase7_signal_generation.py.

Live-confirmed on today's real morning run (LOCAL-MORNING-20260810-120000-000000):
Phase 1 halted on stale price data, but Phase 7's always_run architecture still executed and
found zero BUY signals in buy_sell_daily within its lookback window - a legitimate, non-error
condition the `no_signals_found` branch's own comment says "Phase 8 handles gracefully". But
the subsequent symbols_processed==0 guard only exempted `lock_contention` and
`already_computed_today`, not `no_signals_found` - so it fell through to a CRITICAL halt
message claiming "the loader failed to acquire the processing lock (likely held by stale
process)", which is misleading (no lock was involved) and cascaded into Phase 8/9 errors on
what should have been a benign zero-signal morning.

Fixed by extracting the halt decision into `_should_halt_on_zero_scored_symbols()` and adding
the missing `no_signals_found` exemption.
"""

from algo.orchestrator.phase7_signal_generation import _should_halt_on_zero_scored_symbols


class TestPhase7ZeroSignalsFoundNotHalted:
    def test_no_signals_found_does_not_halt(self):
        """The core bug: a legitimately-empty BUY-signal lookback must not halt Phase 7."""
        score_result = {"symbols_processed": 0, "symbols_failed": 0, "no_signals_found": True}
        assert _should_halt_on_zero_scored_symbols(score_result) is False

    def test_already_computed_today_does_not_halt(self):
        score_result = {"symbols_processed": 0, "symbols_failed": 0, "already_computed_today": True}
        assert _should_halt_on_zero_scored_symbols(score_result) is False

    def test_lock_contention_does_not_halt(self):
        score_result = {"symbols_processed": 0, "symbols_failed": 0, "lock_contention": True}
        assert _should_halt_on_zero_scored_symbols(score_result) is False

    def test_unexplained_zero_symbols_still_halts(self):
        """Sanity check: a genuinely unexplained empty result (no flag set at all) must still
        halt - this is the real "stale lock / infrastructure failure" case the guard exists
        for, and the fix must not have accidentally disabled it."""
        score_result = {"symbols_processed": 0, "symbols_failed": 0}
        assert _should_halt_on_zero_scored_symbols(score_result) is True
