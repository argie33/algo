"""Regression test: Orchestrator._run_preflight_checks()'s top-level market-hours guard
must be early-close aware for live-trading (dry_run=False) runs.

BUG (found 2026-09-08, real-money-readiness orchestration audit; re-confirmed and fixed on
main 2026-09-14 after this guard moved from orchestrator.py into orchestrator_run_loop.py
via the 2026-09-10 file-size-ratchet split): the live-trading branch used the constant
MARKET_CLOSE_TIME (4:00 PM ET) with no early-close awareness, unlike every other
market-hours check in this codebase (phase8_guards.py's own copy of this guard,
phase1_data_freshness.py's _compute_pipeline_context, phase8_entry_execution.py's price-
freshness revalidation - all already early-close aware for NYSE/NASDAQ early-close days:
day before July 4th, day after Thanksgiving, Christmas Eve, real close 1:00 PM ET).

Per this guard's own comment, Phase 6 (portfolio-rotation force-close) and Phase 9 (broker
reconciliation/position-sync) have NO independent market-hours check of their own and rely
entirely on this one guard - so on an early-close day, the 1:00 PM and 3:00 PM scheduled
orchestrator runs would have sailed through this guard thinking the market was open until
4 PM, and Phase 6 could submit real force-close orders to the broker 2-3 hours after the
market had actually closed.

This test calls the real Orchestrator._run_preflight_checks() (not a reimplementation of the
guard's boolean logic) on a known early-close day (2026-11-27, day after Thanksgiving) with
only the clock mocked, and asserts a live-trading run at 2:00 PM ET (after the real 1:00 PM
early close but before the naive 4:00 PM cutoff) is blocked.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator
from utils.infrastructure import EASTERN_TZ

# Confirmed early close in algo/infrastructure/market_calendar.py's EARLY_CLOSES.
_EARLY_CLOSE_DAY = date(2026, 11, 27)
_TWO_PM_ET = datetime(2026, 11, 27, 14, 0, 0, tzinfo=EASTERN_TZ)


def _fake_self(dry_run: bool) -> Orchestrator:
    self = object.__new__(Orchestrator)
    self.run_id = f"test-early-close-guard-{dry_run}"
    self.run_date = _EARLY_CLOSE_DAY
    self.dry_run = dry_run
    self.execution_mode = "paper"
    self.config = {"execution_mode": "paper", "alpaca_paper_trading": True}
    self.execution_tracker = MagicMock()
    self._save_orchestrator_run_status = MagicMock()
    return self


class TestOrchestratorMarketHoursGuardEarlyClose:
    def test_live_trading_at_2pm_on_early_close_day_is_blocked(self):
        """2 PM ET is after the real 1 PM early close - the guard must skip with
        outside_market_hours, not fall through to the naive 4 PM cutoff."""
        fake_self = _fake_self(dry_run=False)

        with patch("algo.orchestration.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = _TWO_PM_ET
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = Orchestrator._run_preflight_checks(fake_self)

        assert result is not None
        assert result["skipped"] is True
        assert result["reason"] == "outside_market_hours: 14:00:00 ET"

    def test_live_trading_at_noon_on_early_close_day_is_not_blocked(self):
        """Noon ET is still within the real 9:30 AM - 1:00 PM early-close window - the
        guard must let this run proceed past the check."""
        fake_self = _fake_self(dry_run=False)
        noon_et = datetime(2026, 11, 27, 12, 0, 0, tzinfo=EASTERN_TZ)

        class _PastTheGuardError(Exception):
            pass

        with (
            patch("algo.orchestration.orchestrator.datetime") as mock_dt,
            patch("algo.orchestration.orchestrator.DatabaseContext", side_effect=_PastTheGuardError),
        ):
            mock_dt.now.return_value = noon_et
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            with pytest.raises(_PastTheGuardError):
                Orchestrator._run_preflight_checks(fake_self)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
