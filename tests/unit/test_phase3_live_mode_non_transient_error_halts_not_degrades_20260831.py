#!/usr/bin/env python3
"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix: Phase 3's LIVE-mode
retry loop around monitor.review_positions() used to enter silent "completed_degraded" mode
(recommendations=[], halted=False) for ANY exception type once the retry loop reached its final
attempt - unlike the paper-mode retry loop just above it, which only enters degraded mode on the
final attempt if the error is actually the transient "cursor already closed"/"current
transaction is aborted" type; any other error there correctly raises and halts.

A genuinely non-transient bug in review_positions() (a real KeyError/logic bug, not a DB cursor
hiccup) that happened to still be failing on the 3rd attempt was silently absorbed into degraded
mode in LIVE mode specifically - the one mode where a cycle of unmonitored open positions matters
most. Fixed to require the same transient-error-type check live mode's twin already had.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase3_position_monitor import run as phase3_run


def _live_config():
    return {"execution_mode": "auto", "is_paper_trading": False}


def _run_with_review_positions_side_effect(side_effect):
    with (
        patch("algo.monitoring.PositionMonitor") as MockMonitor,
        patch("algo.infrastructure.MarketEventHandler") as MockMEH,
        patch("time.sleep"),
    ):
        monitor = MockMonitor.return_value
        monitor.get_open_positions.return_value = [{"symbol": "AAPL"}]
        monitor.check_stale_orders.return_value = {"status": "OK"}
        monitor.review_positions.side_effect = side_effect
        meh = MagicMock()
        meh.check_single_stock_halt.return_value = {"halted": False}
        MockMEH.return_value = meh

        return phase3_run(
            config=_live_config(),
            run_date=date(2026, 8, 31),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=MagicMock(),
        )


class TestPhase3LiveModeDegradedModeRequiresTransientError:
    def test_non_transient_error_on_final_attempt_halts_not_degrades(self):
        """The actual bug scenario: attempts 1-2 fail with a genuinely transient cursor error
        (correctly retried), but attempt 3 (the final one) fails with an UNRELATED, non-transient
        error. This must halt the phase, not silently return completed_degraded with zero
        recommendations - a real bug surfacing on the last attempt was previously indistinguishable
        from cursor-retry exhaustion in live mode, unlike paper mode's identical check. A single
        repeated exception across all 3 attempts does NOT exercise this - both old and new code
        already raise immediately on a non-transient error at attempt 1, since neither ever
        retries a non-transient error in the first place."""
        result = _run_with_review_positions_side_effect(
            [
                RuntimeError("cursor already closed"),
                RuntimeError("cursor already closed"),
                KeyError("unrelated_bug_on_final_attempt"),
            ]
        )

        assert result.halted is True, (
            "A non-transient error on the final retry attempt must halt Phase 3 in live mode, "
            "matching paper mode's identical check"
        )
        assert result.status != "completed_degraded"

    def test_transient_cursor_error_exhausting_retries_still_degrades(self):
        """Sanity check: a genuinely transient cursor/transaction error exhausting all 3
        retries must still enter degraded mode (preserves the original intended behavior -
        guards against an overcorrection that halts on every retry exhaustion)."""
        result = _run_with_review_positions_side_effect(RuntimeError("cursor already closed"))

        assert result.status == "completed_degraded"
        assert result.halted is False
        assert result.data["recommendations"] == []

    def test_non_transient_error_on_first_attempt_halts_immediately(self):
        """A non-transient error must halt on the very first attempt too, not just after
        retries are exhausted - it should never be retried in the first place."""
        result = _run_with_review_positions_side_effect(ValueError("bad data shape"))

        assert result.halted is True
        assert result.status != "completed_degraded"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
