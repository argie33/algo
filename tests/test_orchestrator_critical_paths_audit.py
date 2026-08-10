#!/usr/bin/env python3
"""Test critical orchestrator paths verifying load-bearing rules are implemented.

Key findings from comprehensive audit:
- Phase 5 UnboundLocalError: MarketDataUnavailableError imported inside try block but referenced in except clause
- All critical path tests PASS after fixes
"""

import inspect
from datetime import date

import pytest


class TestPhase5HaltBehavior:
    """Verify Phase 5 halt blocks ALL entries (regression for 2026-08-02 fix)."""

    def test_phase5_halt_constraints_block_all_entries(self):
        """Phase 5 halt MUST have zero-risk constraints."""
        from unittest.mock import MagicMock, patch

        from algo.orchestration.halt_flag_manager import HaltFlagManager
        from algo.orchestrator.phase5_exposure_policy import run as run_phase5

        with patch.object(HaltFlagManager, 'check_halt_flag', return_value=True):
            result = run_phase5(
                config={},
                run_date=date.today(),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted
        constraints = result.data["constraints"]
        assert constraints["halt_new_entries"] is True
        assert constraints["max_new_positions_today"] == 0
        assert constraints["risk_multiplier"] == 0.0
        assert constraints["max_concentration_pct"] == 0.0


class TestPositionSyncPhase1:
    """Verify position sync is called before data freshness (2026-08-01 fix)."""

    def test_position_sync_called_before_data_freshness(self):
        """Phase 1 MUST call sync BEFORE freshness check."""
        from algo.orchestration.orchestrator import Orchestrator

        source = inspect.getsource(Orchestrator._executor_phase_1)
        assert "sync_positions_from_trades" in source
        assert "phase_1_data_freshness" in source
        assert source.find("sync_positions_from_trades") < source.find("phase_1_data_freshness")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
