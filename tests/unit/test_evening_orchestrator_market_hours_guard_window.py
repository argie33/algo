"""Regression test for the evening-run market-hours guard fix (commit 2ce111722).

Orchestrator._run_preflight_checks()'s top-level market-hours guard used
MARKET_OPEN_TIME <= now_et < MARKET_CLOSE_TIME (9:30 AM - 4:00 PM ET) as the allowed
window for every run type, including `evening` (dry_run=True, monitor-only - see
MONITOR_ONLY_RUN_IDENTIFIERS in lambda_function.py, which can never place real orders).
Evening is intentionally scheduled at 5:30 PM ET (terraform/modules/services/
2x-daily-orchestrator.tf, both local dev and production) for post-close "final position
management". Every time it fired at its real scheduled time it hit
"outside_market_hours: 17:30:00 ET" and skipped before Phase 1 - live-confirmed via
orchestrator_execution_log 2026-08-17 (no ALLOW_OUTSIDE_MARKET_HOURS override exists
anywhere in terraform/lambda config, so this was never local-only).

Fixed by widening the upper bound to MONITOR_WINDOW_CLOSE_TIME (6 PM ET) for dry_run
runs only; the lower bound (MARKET_OPEN_TIME) is unchanged for every run type, so the
original pre-market incident protection (2026-08-07, 05:03 ET) is untouched.

This test calls the real Orchestrator._run_preflight_checks() (not a reimplementation of
the guard's boolean logic) with only the clock mocked to 5:45 PM ET, and asserts the
dry_run and live-trading branches diverge exactly as the fix intends.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator
from utils.infrastructure import EASTERN_TZ

# A real trading Monday, matching the live incident's own run_date.
_TRADING_DAY = date(2026, 8, 17)
_FIVE_45_PM_ET = datetime(2026, 8, 17, 17, 45, 0, tzinfo=EASTERN_TZ)


def _fake_self(dry_run: bool) -> Orchestrator:
    self = object.__new__(Orchestrator)
    self.run_id = f"test-evening-guard-{dry_run}"
    self.run_date = _TRADING_DAY
    self.dry_run = dry_run
    self.config = {"execution_mode": "paper", "alpaca_paper_trading": True}
    self.execution_tracker = MagicMock()
    self._save_orchestrator_run_status = MagicMock()
    return self


class TestEveningMarketHoursGuardWindow:
    def test_dry_run_at_545pm_et_is_not_blocked_by_the_guard(self):
        """5:45 PM ET is within MONITOR_WINDOW_CLOSE_TIME (6 PM) for dry_run runs -
        the guard must not return the outside_market_hours skip dict.

        Reaching the real `with DatabaseContext(...)` call right after the guard is
        deterministic, DB-independent proof the guard let execution through: patching
        DatabaseContext to raise a sentinel on entry means the ONLY way this sentinel
        can surface is if nothing before it (the guard) returned early first.
        """
        fake_self = _fake_self(dry_run=True)

        class _PastTheGuardError(Exception):
            pass

        with (
            patch("algo.orchestration.orchestrator.datetime") as mock_dt,
            patch("algo.orchestration.orchestrator.DatabaseContext", side_effect=_PastTheGuardError),
        ):
            mock_dt.now.return_value = _FIVE_45_PM_ET
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            with pytest.raises(_PastTheGuardError):
                Orchestrator._run_preflight_checks(fake_self)

        # The guard's own early-return path never touches execution_tracker directly on
        # success, but it DOES on a block - confirm that path was never taken.
        fake_self.execution_tracker.save_execution_log.assert_not_called()

    def test_live_trading_at_545pm_et_is_still_blocked_by_the_guard(self):
        """5:45 PM ET is outside MARKET_CLOSE_TIME (4 PM) for live-trading (dry_run=False)
        runs - unchanged behavior, the guard must still skip with outside_market_hours."""
        fake_self = _fake_self(dry_run=False)

        with patch("algo.orchestration.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = _FIVE_45_PM_ET
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = Orchestrator._run_preflight_checks(fake_self)

        assert result is not None
        assert result["skipped"] is True
        assert result["reason"] == "outside_market_hours: 17:45:00 ET"
        fake_self.execution_tracker.save_execution_log.assert_called_once_with(
            "degraded", "outside_market_hours: 17:45:00 ET"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
