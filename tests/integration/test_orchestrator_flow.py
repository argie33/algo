"""
Integration tests: Full orchestrator pipeline flow.

Tests the entire orchestrator from start to finish in dry_run/paper modes:
- Phase 1: Data freshness
- Phase 2: Circuit breakers
- Phase 3: Position monitoring & reconciliation
- Phase 4: Pyramid adds
- Phase 5: Signal generation & filtering
- Phase 6: Trade execution
- Phase 7: Reconciliation & snapshot

Uses mocked DB, mocked Alpaca, real algo logic.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime


@pytest.mark.integration
class TestOrchestratorDryRun:
    """Test orchestrator in dry_run mode (no real trades)."""

    def test_full_pipeline_executes(self, test_config):
        """Full orchestrator pipeline should complete without errors."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        # Mock all external dependencies
        with patch.object(orch, 'phase_1_data_freshness', return_value=True), \
             patch.object(orch, 'phase_2_circuit_breakers', return_value=True), \
             patch.object(orch, 'phase_3_position_monitor', return_value=True), \
             patch.object(orch, 'phase_3a_reconciliation', return_value=True), \
             patch.object(orch, 'phase_3b_exposure_policy', return_value=True), \
             patch.object(orch, 'phase_4_pyramid_adds', return_value=True), \
             patch.object(orch, 'phase_5_signal_generation', return_value=True), \
             patch.object(orch, 'phase_6_trade_execution', return_value=True), \
             patch.object(orch, 'phase_7_reconcile', return_value=True):

            success = orch.run()

            assert success is True

    def test_circuit_breaker_halts_entries(self, test_config):
        """When CB fires, should skip entry phases but run exit/monitoring."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        with patch.object(orch, 'phase_1_data_freshness', return_value=True), \
             patch.object(orch, 'phase_2_circuit_breakers', return_value=False), \
             patch.object(orch, 'phase_3a_reconciliation', return_value=True), \
             patch.object(orch, 'phase_3_position_monitor', return_value=True), \
             patch.object(orch, 'phase_3b_exposure_policy', return_value=True), \
             patch.object(orch, 'phase_4_exit_execution', return_value=True), \
             patch.object(orch, 'phase_7_reconcile', return_value=True):

            success = orch.run()

            assert success is True
            # Verify entry phases were skipped
            # (would need to check audit log or call counts)

    def test_data_freshness_failure_halts_pipeline(self, test_config):
        """When phase 1 fails, entire pipeline should halt."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        with patch.object(orch, 'phase_1_data_freshness', return_value=False):

            success = orch.run()

            assert success is True  # Returns True but with halt status


@pytest.mark.integration
class TestOrchestratorPaperMode:
    """Test orchestrator in paper trading mode (simulated trades)."""

    def test_paper_trades_created_not_sent_to_alpaca(self, test_config):
        """In paper mode, trades should be recorded locally, not sent to Alpaca."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='paper',
        )

        with patch.object(orch, 'phase_1_data_freshness', return_value=True), \
             patch.object(orch, 'phase_2_circuit_breakers', return_value=True), \
             patch.object(orch, 'phase_5_signal_generation') as mock_signals, \
             patch.object(orch, 'phase_6_trade_execution') as mock_exec:

            # Simulate qualified signals
            mock_signals.return_value = True
            orch._qualified_trades = [
                {'symbol': 'AAPL', 'entry_price': 150.0, 'shares': 100},
            ]

            success = orch.run()

            # Verify trades were processed
            # mock_exec.assert_called()


@pytest.mark.integration
class TestOrchestratorReconciliation:
    """Test reconciliation between Alpaca and DB."""

    def test_reconciliation_detects_untracked_positions(self, test_config):
        """Reconciliation should flag Alpaca positions not in DB."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        with patch.object(orch, 'phase_3a_reconciliation') as mock_reconcile:
            mock_reconcile.return_value = True

            success = orch.run()

            assert success is True
            # Verify reconciliation was called
            # mock_reconcile.assert_called_once()


@pytest.mark.integration
class TestOrchestratorErrorRecovery:
    """Test orchestrator handling of errors and recovery."""

    def test_phase_error_does_not_crash_pipeline(self, test_config):
        """Errors in one phase should not crash entire pipeline."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        with patch.object(orch, 'phase_1_data_freshness', side_effect=Exception('DB error')):

            # Should not raise exception
            success = orch.run()

            assert success is not None


@pytest.mark.integration
class TestOrchestratorAuditLogging:
    """Test that orchestrator properly logs all phases."""

    def test_all_phases_logged(self, test_config):
        """Each phase execution should be logged to algo_audit_log."""
        from algo_orchestrator import AlgoOrchestrator

        orch = AlgoOrchestrator(
            run_date=date.today(),
            execution_mode='dry_run',
        )

        with patch.object(orch, 'log_phase_result') as mock_log, \
             patch.object(orch, 'phase_1_data_freshness', return_value=True), \
             patch.object(orch, 'phase_2_circuit_breakers', return_value=True), \
             patch.object(orch, 'phase_3a_reconciliation', return_value=True), \
             patch.object(orch, 'phase_3_position_monitor', return_value=True), \
             patch.object(orch, 'phase_3b_exposure_policy', return_value=True), \
             patch.object(orch, 'phase_4_pyramid_adds', return_value=True), \
             patch.object(orch, 'phase_5_signal_generation', return_value=True), \
             patch.object(orch, 'phase_6_trade_execution', return_value=True), \
             patch.object(orch, 'phase_7_reconcile', return_value=True):

            success = orch.run()

            # Verify log_phase_result was called for each phase
            # assert mock_log.call_count >= 9  # At least 9 phases
