"""Regression test: ALLOW_OUTSIDE_MARKET_HOURS must never bypass the orchestrator-level
market-hours guard (Orchestrator._run_preflight_checks()) when execution_mode="auto" (live
trading with a real broker).

Same bug class as [[phase8_market_hours_bypass_hardened_against_auto_mode_20260823]], found
by checking whether the fix there needed to be applied anywhere else: this guard is a
SEPARATE, earlier check (runs before Phase 1, gates the entire run) with its own independent
read of the same env var. It is MORE severe than the Phase 8 gap was - Phase 6 (portfolio-
rotation force-close) and Phase 9 (broker reconciliation/position-sync) have no market-hours
check of their own at all, so bypassing this one guard in execution_mode="auto" would let them
run outside market hours with zero remaining safety net (Phase 8's own hardened guard would
still catch new entries, but not exits/reconciliation).

Neither ALLOW_OUTSIDE_MARKET_HOURS nor PHASE_8_TEST_MODE is set by any deployed terraform/infra
config (confirmed via full-repo grep, 2026-08-23) - this is a local-testing-only mechanism, not
an active exploit. Fixed by forcing the flag off whenever self.execution_mode == "auto",
regardless of the env var, with a loud CRITICAL log if it would have mattered.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator
from utils.infrastructure import EASTERN_TZ

_TRADING_DAY = date(2026, 8, 17)
_OUTSIDE_HOURS = datetime(2026, 8, 17, 20, 0, 0, tzinfo=EASTERN_TZ)  # 8 PM ET


def _fake_self(execution_mode: str) -> Orchestrator:
    self = object.__new__(Orchestrator)
    self.run_id = f"test-auto-guard-{execution_mode}"
    self.run_date = _TRADING_DAY
    self.dry_run = execution_mode != "auto"
    self.execution_mode = execution_mode
    self.config = {"execution_mode": execution_mode, "alpaca_paper_trading": execution_mode != "auto"}
    self.execution_tracker = MagicMock()
    self._save_orchestrator_run_status = MagicMock()
    return self


class TestOrchestratorMarketHoursBypassNeverAppliesInAutoMode:
    def test_allow_outside_market_hours_does_not_bypass_guard_in_auto_mode(self, monkeypatch):
        monkeypatch.setenv("ALLOW_OUTSIDE_MARKET_HOURS", "true")
        fake_self = _fake_self("auto")

        with patch("algo.orchestration.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = _OUTSIDE_HOURS
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = Orchestrator._run_preflight_checks(fake_self)

        assert result is not None
        assert result["skipped"] is True
        assert "outside_market_hours" in result["reason"]

    def test_allow_outside_market_hours_still_works_normally_in_paper_mode(self, monkeypatch):
        """Sanity check: the override must still function for its intended purpose (local
        testing in paper/dry/review mode) - only auto mode is hardened against it."""
        monkeypatch.setenv("ALLOW_OUTSIDE_MARKET_HOURS", "true")
        fake_self = _fake_self("paper")

        class _PastTheGuardError(Exception):
            pass

        with (
            patch("algo.orchestration.orchestrator.datetime") as mock_dt,
            patch("algo.orchestration.orchestrator.DatabaseContext", side_effect=_PastTheGuardError),
        ):
            mock_dt.now.return_value = _OUTSIDE_HOURS
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            with pytest.raises(_PastTheGuardError):
                Orchestrator._run_preflight_checks(fake_self)

        fake_self.execution_tracker.save_execution_log.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
