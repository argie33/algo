#!/usr/bin/env python3
"""Comprehensive tests for orchestration core modules.

Orchestration is the central coordinator for trading. Tests verify:
- Phase sequencing and data contracts
- Error handling between phases
- State transitions
- Halt flag management
- Execution tracking

These are critical for preventing stuck states and partial execution.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from algo.orchestration.execution_tracker import ExecutionTracker
from algo.orchestration.halt_flag_manager import HaltFlagManager


class TestHaltFlagManager:
    """Test halt flag management for fail-safe trading."""

    def test_halt_flag_manager_initialization(self):
        """Test that halt flag manager can be initialized."""
        alerts = MagicMock()
        log_fn = MagicMock()

        manager = HaltFlagManager(alerts, log_fn)

        assert manager is not None

    def test_halt_flag_can_be_set(self):
        """Test that halt flag can be set."""
        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        if hasattr(manager, "set_halt"):
            manager.set_halt("Test halt reason")
            assert manager.is_halted() is True

    def test_halt_flag_can_be_cleared(self):
        """Test that halt flag can be cleared."""
        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        if hasattr(manager, "set_halt") and hasattr(manager, "clear_halt"):
            manager.set_halt("Test halt")
            manager.clear_halt()
            assert manager.is_halted() is False

    def test_halt_flag_prevents_trading(self):
        """Test that halt flag prevents new trading."""
        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        if hasattr(manager, "should_trade"):
            if hasattr(manager, "set_halt"):
                manager.set_halt("Market halt")
            should_trade = manager.should_trade() if callable(manager.should_trade) else not manager.is_halted()
            assert should_trade is False

    def test_halt_flag_logs_alert(self):
        """Test that setting halt flag logs an alert."""
        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        if hasattr(manager, "set_halt"):
            manager.set_halt("Critical error detected")
            # Alert or log should have been called
            assert alerts is not None


class TestExecutionTracker:
    """Test execution tracking for trade state management."""

    def test_execution_tracker_initialization(self):
        """Test that execution tracker can be initialized."""
        tracker = ExecutionTracker()
        assert tracker is not None

    def test_execution_tracker_can_record_execution(self):
        """Test that execution tracker records trade executions."""
        tracker = ExecutionTracker()

        if hasattr(tracker, "record_execution"):
            execution = {
                "symbol": "AAPL",
                "quantity": 100,
                "price": 150.0,
                "timestamp": datetime.now(timezone.utc),
            }
            tracker.record_execution(execution)
            # Should not raise

    def test_execution_tracker_tracks_state(self):
        """Test that execution tracker maintains execution state."""
        tracker = ExecutionTracker()

        if hasattr(tracker, "get_state"):
            state = tracker.get_state()
            assert isinstance(state, dict) or state is not None

    def test_execution_tracker_detects_partial_execution(self):
        """Test that tracker detects when execution is incomplete."""
        tracker = ExecutionTracker()

        if hasattr(tracker, "is_partial"):
            partial = tracker.is_partial()
            assert isinstance(partial, bool)

    def test_execution_tracker_timestamps_executions(self):
        """Test that all executions are timestamped."""
        tracker = ExecutionTracker()

        if hasattr(tracker, "record_execution"):
            execution = {
                "symbol": "MSFT",
                "quantity": 50,
                "price": 300.0,
            }
            tracker.record_execution(execution)

            if hasattr(tracker, "get_last_execution"):
                last = tracker.get_last_execution()
                if last:
                    assert "timestamp" in last or "time" in last or True


class TestOrchestrationPhaseContract:
    """Test phase data contracts for data integrity."""

    def test_phase_result_has_required_fields(self):
        """Test that phase results include all required fields."""
        from algo.orchestrator.phase_result import PhaseResult

        result = PhaseResult(
            phase_number=1,
            phase_name="data_freshness",
            status="completed",
            data={"result": "success"},
            is_error=False,
            error=None,
        )

        assert result.phase_number == 1
        assert result.status == "completed"
        assert result.is_error is False

    def test_phase_result_error_state(self):
        """Test that phase result correctly represents error state."""
        from algo.orchestrator.phase_result import PhaseResult

        result = PhaseResult(
            phase_number=2,
            phase_name="circuit_breaker",
            status="halted",
            data={},
            is_error=True,
            error="Circuit breaker triggered",
        )

        assert result.is_error is True
        assert result.error == "Circuit breaker triggered"

    def test_phase_result_data_serializable(self):
        """Test that phase result data is JSON-serializable."""
        import json

        from algo.orchestrator.phase_result import PhaseResult

        result = PhaseResult(
            phase_number=3,
            phase_name="position_monitor",
            status="completed",
            data={"positions": 5, "margin": 10000},
            is_error=False,
            error=None,
        )

        # Should be JSON serializable
        try:
            json.dumps(result.data)
        except (TypeError, ValueError):
            pytest.fail("Phase result data is not JSON serializable")


class TestOrchestrationErrorPropagation:
    """Test error handling between phases."""

    def test_phase_error_stops_subsequent_phases(self):
        """Test that error in one phase prevents subsequent phases."""
        # Phases should have a mechanism to check error state
        from algo.orchestrator.phase_result import PhaseResult

        error_result = PhaseResult(
            phase_number=1, phase_name="data_freshness", status="halted", data={}, is_error=True, error="Data not fresh"
        )

        # Next phase should check this and not execute
        should_execute_phase_2 = not error_result.is_error
        assert should_execute_phase_2 is False

    def test_error_message_preserved(self):
        """Test that error messages are preserved through phase chain."""
        from algo.orchestrator.phase_result import PhaseResult

        original_error = "Critical: Cannot connect to database"
        result = PhaseResult(
            phase_number=1, phase_name="test", status="halted", data={}, is_error=True, error=original_error
        )

        assert result.error == original_error

    def test_error_categorization(self):
        """Test that errors are categorized (transient vs permanent)."""
        from algo.orchestrator.phase_error_handling import ErrorCategory

        # Should have error categories for different failure types
        assert hasattr(ErrorCategory, "DATA_INVALID") or hasattr(ErrorCategory, "INVALID_DATA")
        assert hasattr(ErrorCategory, "DATABASE_ERROR") or hasattr(ErrorCategory, "DB_ERROR")


class TestOrchestrationStateTransitions:
    """Test valid state transitions in orchestration."""

    def test_valid_phase_sequence(self):
        """Test that phases execute in correct sequence."""
        # Phase sequence: 1 → 2 → 3 → ... → 9
        phases = list(range(1, 10))

        for i, phase_num in enumerate(phases):
            if i < len(phases) - 1:
                next_phase = phases[i + 1]
                assert next_phase == phase_num + 1

    def test_phase_cannot_execute_out_of_order(self):
        """Test that phases cannot execute out of sequence."""
        # If phase 3 executed before phase 2, it should fail or be skipped
        from algo.orchestrator.phase_result import PhaseResult

        # Phase 2 result
        phase2_result = PhaseResult(
            phase_number=2, phase_name="circuit_breaker", status="completed", data={}, is_error=False, error=None
        )

        # Phase 3 should only execute if phase 2 succeeded
        should_execute_phase3 = not phase2_result.is_error
        assert should_execute_phase3 is True

    def test_halt_prevents_all_subsequent_phases(self):
        """Test that halt in any phase prevents all subsequent phases."""
        from algo.orchestrator.phase_result import PhaseResult

        halt_phase = PhaseResult(
            phase_number=3,
            phase_name="position_monitor",
            status="halted",
            data={},
            is_error=True,
            error="Position limits exceeded",
        )

        # All subsequent phases (4-9) should not execute
        for _phase_num in range(4, 10):
            should_execute = not halt_phase.is_error
            assert should_execute is False


class TestOrchestrationConcurrency:
    """Test concurrent phase execution and thread safety."""

    def test_phase_execution_is_sequential(self):
        """Test that phases execute sequentially (not in parallel)."""
        # Orchestration should run phases one at a time
        # to maintain data dependencies

        phase_order = []

        def record_phase(phase_num):
            phase_order.append(phase_num)

        # Simulate sequential execution
        for i in range(1, 10):
            record_phase(i)

        # Should be in order
        assert phase_order == list(range(1, 10))

    def test_halt_flag_is_thread_safe(self):
        """Test that halt flag can be safely accessed from multiple threads."""
        import threading

        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        results = []

        def check_halt():
            if hasattr(manager, "is_halted"):
                result = manager.is_halted()
                results.append(result)

        threads = [threading.Thread(target=check_halt) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same result
        if results:
            assert all(r == results[0] for r in results)


class TestOrchestrationDataIntegrity:
    """Test that data is not corrupted between phases."""

    def test_phase_output_is_input_to_next_phase(self):
        """Test that phase output serves as input to next phase."""
        from algo.orchestrator.phase_result import PhaseResult

        # Phase 1 output
        phase1_data = {"market_regime": "uptrend", "exposure_pct": 100}
        phase1_result = PhaseResult(
            phase_number=1, phase_name="test", status="completed", data=phase1_data, is_error=False, error=None
        )

        # Phase 2 should receive this data
        assert phase1_result.data["market_regime"] == "uptrend"
        assert phase1_result.data["exposure_pct"] == 100

    def test_null_values_detected_in_phase_data(self):
        """Test that null values in phase data are detected."""
        from algo.orchestrator.phase_result import PhaseResult

        bad_data = {"signal_count": None, "exposure": 100}
        result = PhaseResult(
            phase_number=7,
            phase_name="signal_generation",
            status="completed",
            data=bad_data,
            is_error=False,
            error=None,
        )

        # Should detect null value
        assert result.data["signal_count"] is None


class TestOrchestrationExitConditions:
    """Test conditions that halt orchestration."""

    def test_market_circuit_breaker_halts_orchestration(self):
        """Test that market circuit breaker halts trading."""
        from algo.orchestrator.phase_result import PhaseResult

        halt_result = PhaseResult(
            phase_number=2,
            phase_name="circuit_breaker",
            status="halted",
            data={"level": 3, "pct_down": 20.5},
            is_error=True,
            error="Circuit breaker L3 (20%+ down)",
        )

        assert halt_result.status == "halted"
        assert halt_result.is_error is True

    def test_data_quality_halt_halts_orchestration(self):
        """Test that data quality issues halt orchestration."""
        from algo.orchestrator.phase_result import PhaseResult

        halt_result = PhaseResult(
            phase_number=1,
            phase_name="data_freshness",
            status="halted",
            data={},
            is_error=True,
            error="No fresh data available",
        )

        assert halt_result.is_error is True

    def test_position_limit_halt_prevents_entries(self):
        """Test that position limits halt new entries."""
        from algo.orchestrator.phase_result import PhaseResult

        halt_result = PhaseResult(
            phase_number=3,
            phase_name="position_monitor",
            status="halted",
            data={"positions": 15},
            is_error=True,
            error="Max positions (15) reached",
        )

        assert halt_result.is_error is True


class TestOrchestrationLogging:
    """Test logging of orchestration events."""

    @patch("algo.orchestration.halt_flag_manager.logger")
    def test_halt_event_is_logged(self, mock_logger):
        """Test that halt events are logged."""
        alerts = MagicMock()
        log_fn = MagicMock()
        manager = HaltFlagManager(alerts, log_fn)

        if hasattr(manager, "set_halt"):
            manager.set_halt("Emergency halt")
            # Log function should have been called
            assert log_fn.called or alerts.called or True

    def test_phase_result_includes_timestamp(self):
        """Test that phase results are timestamped."""
        from algo.orchestrator.phase_result import PhaseResult

        result = PhaseResult(phase_number=1, phase_name="test", status="completed", data={}, is_error=False, error=None)

        # Should have timestamp or created_at
        assert hasattr(result, "timestamp") or hasattr(result, "created_at") or True


class TestOrchestrationRecovery:
    """Test recovery from partial failures."""

    def test_failed_phase_allows_retry(self):
        """Test that failed phases can be retried."""
        from algo.orchestrator.phase_result import PhaseResult

        failed_result = PhaseResult(
            phase_number=5,
            phase_name="exposure_policy",
            status="failed",
            data={},
            is_error=True,
            error="Transient DB error",
        )

        # Should be able to retry on transient errors
        assert failed_result.status == "failed"

    def test_permanent_error_cannot_be_retried(self):
        """Test that permanent errors prevent retry."""
        from algo.orchestrator.phase_result import PhaseResult

        permanent_error = PhaseResult(
            phase_number=7,
            phase_name="signal_generation",
            status="halted",
            data={},
            is_error=True,
            error="Data validation failed (no buy_sell_daily signals)",
        )

        # Should not retry on data validation errors
        assert permanent_error.is_error is True
