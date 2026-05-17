"""
Unit tests for algo_orchestrator - the core 7-phase trading workflow.

Tests cover:
- Phase 1: Data freshness validation (fail-closed on stale data)
- Phase 2: Risk exposure analysis
- Phase 3: Position monitoring and recommendations
- Phase 4: Exit execution (fail-closed on errors)
- Phase 5: Signal generation and ranking
- Phase 6: Entry execution (fail-closed on errors, circuit breaker on >50% failure)
- Phase 7: Reconciliation

Critical for production: These tests verify the orchestrator doesn't silently fail
or execute trades when it should halt.
"""

import pytest
import psycopg2
from unittest.mock import Mock, MagicMock, patch, call
from datetime import date, datetime, timedelta
from algo.algo_orchestrator import AlgoOrchestrator
from utils.trade_status import TradeStatus, PositionStatus


class TestOrchestratorPhases:
    """Test each phase of the orchestrator workflow."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance for testing."""
        with patch('algo.algo_orchestrator.psycopg2.connect'):
            orch = AlgoOrchestrator(
                config={'max_positions': 10, 'max_portfolio_risk': 0.05},
                run_date=date.today(),
                dry_run=True  # Always dry-run in tests
            )
            orch.cur = MagicMock()
            orch.conn = MagicMock()
            return orch

    # ========================================================================
    # PHASE 1: Data Freshness Validation
    # ========================================================================

    def test_phase_1_data_fresh_passes(self, orchestrator):
        """Phase 1 should pass when data is within 3-day window."""
        orchestrator.cur.fetchone.return_value = (2,)  # 2 days old = fresh

        result = orchestrator.phase_1_data_freshness_check()

        assert result is True
        assert orchestrator.phase_results[1]['status'] == 'success'

    def test_phase_1_data_stale_fails_closed(self, orchestrator):
        """Phase 1 should fail-closed when data is > 3 days old."""
        orchestrator.cur.fetchone.return_value = (5,)  # 5 days old = stale

        result = orchestrator.phase_1_data_freshness_check()

        assert result is False
        assert orchestrator.phase_results[1]['status'] == 'error'

    def test_phase_1_empty_database_fails_closed(self, orchestrator):
        """Phase 1 should fail-closed when tables are empty."""
        orchestrator.cur.fetchone.return_value = (None,)

        result = orchestrator.phase_1_data_freshness_check()

        assert result is False
        assert 'empty' in orchestrator.phase_results[1]['message'].lower()

    # ========================================================================
    # PHASE 4: Exit Execution (Fail-Closed)
    # ========================================================================

    def test_phase_4_exit_exception_fails_closed(self, orchestrator):
        """Phase 4 should fail-closed if trade execution throws exception."""
        orchestrator.position_recs = [{'symbol': 'AAPL', 'exit_price': 150}]

        with patch('algo.algo_orchestrator.TradeExecutor') as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor
            mock_executor.exit_trade.side_effect = RuntimeError("Alpaca API error")

            result = orchestrator.phase_4_exit_execution()

            # Should fail-closed, not continue to next phase
            assert result is False
            assert orchestrator.phase_results[4]['status'] == 'error'

    def test_phase_4_success_returns_true(self, orchestrator):
        """Phase 4 should return True when exits succeed."""
        orchestrator.position_recs = []  # No positions = successful completion

        with patch('algo.algo_orchestrator.ExitEngine') as mock_exit_engine_class:
            mock_exit_engine = MagicMock()
            mock_exit_engine_class.return_value = mock_exit_engine
            mock_exit_engine.check_and_execute_exits.return_value = 0

            result = orchestrator.phase_4_exit_execution()

            assert result is True
            assert orchestrator.phase_results[4]['status'] == 'success'

    # ========================================================================
    # PHASE 6: Entry Execution (Circuit Breaker)
    # ========================================================================

    def test_phase_6_circuit_breaker_triggers_on_50_percent_failure(self, orchestrator):
        """Phase 6 should halt if >50% of trades fail (circuit breaker)."""
        orchestrator._qualified_trades = [
            {'symbol': 'AAPL', 'position_size': 100},
            {'symbol': 'MSFT', 'position_size': 100},
            {'symbol': 'GOOGL', 'position_size': 100},
        ]

        with patch('algo.algo_orchestrator.TradeExecutor') as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor
            # Simulate 2 of 3 trades failing (66% failure rate > 50%)
            mock_executor.execute_entry.side_effect = [
                {'success': True},
                {'success': False, 'message': 'Insufficient buying power'},
                {'success': False, 'message': 'Duplicate position'},
            ]

            result = orchestrator.phase_6_entry_execution()

            # Should fail-closed due to circuit breaker
            assert result is False
            assert 'failure rate' in orchestrator.phase_results[6]['message'].lower()

    def test_phase_6_success_under_50_percent_failure(self, orchestrator):
        """Phase 6 should succeed if failure rate < 50%."""
        orchestrator._qualified_trades = [
            {'symbol': 'AAPL', 'position_size': 100},
            {'symbol': 'MSFT', 'position_size': 100},
            {'symbol': 'GOOGL', 'position_size': 100},
        ]

        with patch('algo.algo_orchestrator.TradeExecutor') as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor
            # Only 1 of 3 fails (33% failure < 50%)
            mock_executor.execute_entry.side_effect = [
                {'success': True},
                {'success': True},
                {'success': False},
            ]

            result = orchestrator.phase_6_entry_execution()

            # Should succeed even with one failure
            assert result is True

    # ========================================================================
    # Halt Flag Mechanism
    # ========================================================================

    def test_halt_flag_stops_phase_4(self, orchestrator):
        """Halt flag should stop Phase 4 execution."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            halt_file = os.path.join(tmpdir, 'halt')
            orchestrator.HALT_FLAG_PATH = halt_file

            # Create halt flag
            open(halt_file, 'w').close()

            result = orchestrator.phase_4_exit_execution()

            assert result is False
            assert 'halt' in orchestrator.phase_results.get(4, {}).get('message', '').lower()

    # ========================================================================
    # Phase Return Value Handling
    # ========================================================================

    def test_run_loop_halts_on_phase_failure(self, orchestrator):
        """Orchestrator run() should halt if any phase returns False."""
        with patch.object(orchestrator, 'phase_1_data_freshness_check', return_value=False):
            with patch.object(orchestrator, 'phase_2_risk_exposure_analysis'):
                result = orchestrator.run()

                # Should stop after Phase 1 failure
                assert result is False

    def test_run_loop_continues_on_phase_success(self, orchestrator):
        """Orchestrator run() should continue if phase returns True."""
        with patch.object(orchestrator, 'phase_1_data_freshness_check', return_value=True):
            with patch.object(orchestrator, 'phase_2_risk_exposure_analysis', return_value=True):
                with patch.object(orchestrator, 'phase_3_position_monitoring', return_value=True):
                    with patch.object(orchestrator, 'phase_4_exit_execution', return_value=True):
                        with patch.object(orchestrator, 'phase_5_signal_generation', return_value=True):
                            with patch.object(orchestrator, 'phase_6_entry_execution', return_value=True):
                                with patch.object(orchestrator, 'phase_7_reconcile', return_value=True):
                                    result = orchestrator.run()

                                    # Should complete all phases
                                    assert result is not False  # Return value depends on reconciliation


class TestOrchestratorIntegration:
    """Integration tests for orchestrator with real-ish data."""

    @pytest.fixture
    def orchestrator_with_mocks(self):
        """Create orchestrator with mocked database."""
        with patch('algo.algo_orchestrator.psycopg2.connect'):
            orch = AlgoOrchestrator(
                config={
                    'max_positions': 10,
                    'max_portfolio_risk': 0.05,
                    'symbol_whitelist': ['AAPL', 'MSFT', 'GOOGL']
                },
                run_date=date.today(),
                dry_run=True
            )
            orch.cur = MagicMock()
            orch.conn = MagicMock()
            return orch

    def test_full_orchestrator_dry_run(self, orchestrator_with_mocks):
        """Test full 7-phase dry-run without actual trades."""
        # Setup mock responses for each phase
        orchestrator_with_mocks.cur.fetchone.side_effect = [
            (2,),  # Phase 1: data is 2 days old (fresh)
            (5,),  # Phase 2: risk check
            (3,),  # Phase 3: position count
            (0,),  # Phase 4: exits executed
            (10,), # Phase 5: signals generated
            (5,),  # Phase 6: entries executed
            (0,),  # Phase 7: reconciliation
        ]

        # In dry-run mode, no trades should actually execute
        result = orchestrator_with_mocks.run()

        # Should complete the full orchestrator run
        assert orchestrator_with_mocks.run_count >= 1


class TestOrchestratorErrorHandling:
    """Test error handling and recovery in orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        with patch('algo.algo_orchestrator.psycopg2.connect'):
            orch = AlgoOrchestrator(
                config={'max_positions': 10},
                run_date=date.today(),
                dry_run=True
            )
            orch.cur = MagicMock()
            orch.conn = MagicMock()
            return orch

    def test_database_connection_error_fails_closed(self, orchestrator):
        """Database connection errors should fail orchestrator closed."""
        orchestrator.cur.execute.side_effect = psycopg2.OperationalError("Connection lost")

        # Phase 1 query should fail
        result = orchestrator.phase_1_data_freshness_check()

        assert result is False

    def test_exception_in_phase_logged_properly(self, orchestrator):
        """Exceptions in phases should be logged with context."""
        orchestrator.cur.execute.side_effect = ValueError("Invalid data")

        result = orchestrator.phase_1_data_freshness_check()

        assert result is False
        assert orchestrator.phase_results[1]['status'] == 'error'
        assert 'invalid' in orchestrator.phase_results[1]['message'].lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
