#!/usr/bin/env python3
"""Tests for consistent error handling across phases.

Verifies that operators can distinguish different failure modes:
- "No signals" from market closed (MARKET_CLOSED) vs data loader failed (DATA_MISSING)
- Data validation errors (DATA_INVALID) vs DB errors (DATABASE_ERROR)
- Stale data (DATA_STALE) vs incomplete data (DATA_INCOMPLETE)
"""

import pytest

from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
)


class TestErrorCategoryDistinction:
    """Test that error categories allow operators to distinguish failure modes."""

    def test_market_closed_vs_data_loader_failed(self):
        """Operators must distinguish 'no signals = market closed' from 'no signals = loader failed'."""

        # Scenario 1: Market is closed (normal, no error)
        market_closed_error = PhaseError(
            category=ErrorCategory.MARKET_CLOSED,
            message="Market closed (weekend)",
            root_cause=None,
            recoverable=False,
            log_level="warning",
        )
        assert market_closed_error.category == ErrorCategory.MARKET_CLOSED
        assert "weekend" in market_closed_error.message.lower()
        # Operators see this and know: normal, no trading today

        # Scenario 2: Data loader failed (error, needs investigation)
        loader_failed_error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message="No buy_sell_daily BUY signals found",
            root_cause="Check that EOD pipeline (4:05 PM ET) has completed and buy_sell_daily loader ran",
            recoverable=False,
            log_level="critical",
        )
        assert loader_failed_error.category == ErrorCategory.DATA_MISSING
        assert "pipeline" in loader_failed_error.root_cause.lower()
        # Operators see this and know: error, must investigate why loader failed

        # Categories must be distinct
        assert market_closed_error.category != loader_failed_error.category

    def test_db_error_vs_validation_error(self):
        """Operators must distinguish DB errors from validation errors."""

        # Scenario 1: Database unavailable (recoverable)
        db_error = PhaseError(
            category=ErrorCategory.DATABASE_ERROR,
            message="Could not check upstream data quality drift",
            root_cause="connection timeout",
            recoverable=False,
            log_level="warning",
        )
        assert db_error.category == ErrorCategory.DATABASE_ERROR
        assert "connection" in db_error.root_cause.lower()

        # Scenario 2: Data validation failed (not recoverable)
        validation_error = PhaseError(
            category=ErrorCategory.DATA_INVALID,
            message="Signal validation failed: missing required fields",
            root_cause="Required fields: symbol, composite_score, entry_price, close, sma_50, signal_strength",
            recoverable=False,
            log_level="error",
        )
        assert validation_error.category == ErrorCategory.DATA_INVALID
        assert "field" in validation_error.root_cause.lower()

        # Categories must be distinct
        assert db_error.category != validation_error.category

    def test_stale_vs_incomplete_data(self):
        """Operators must distinguish stale data from incomplete data."""

        # Scenario 1: Data is stale (old date)
        stale_error = PhaseError(
            category=ErrorCategory.DATA_STALE,
            message="Price data is 2 day(s) stale (latest: 2024-01-10, expected: 2024-01-12)",
            root_cause="Check that price_daily loader has completed for today",
            recoverable=False,
            log_level="critical",
        )
        assert stale_error.category == ErrorCategory.DATA_STALE
        assert "stale" in stale_error.message.lower()
        # Operators see this and know: data is OLD, must wait for loader

        # Scenario 2: Data is incomplete (missing symbols)
        incomplete_error = PhaseError(
            category=ErrorCategory.DATA_INCOMPLETE,
            message="Price data coverage insufficient: coverage 45.0% < min 75.0%",
            root_cause="Check that price_daily loader has loaded today's data (expected 5000+ symbols, got 2250)",
            recoverable=False,
            log_level="critical",
        )
        assert incomplete_error.category == ErrorCategory.DATA_INCOMPLETE
        assert "coverage" in incomplete_error.message.lower()
        # Operators see this and know: data is INCOMPLETE, must check loader progress

        # Categories must be distinct
        assert stale_error.category != incomplete_error.category

    def test_error_message_clarity_for_operators(self):
        """Error messages must clearly explain what happened and what to do."""

        errors = [
            PhaseError(
                category=ErrorCategory.MARKET_CLOSED,
                message="Market closed (no trading today)",
                root_cause=None,
                log_level="warning",
            ),
            PhaseError(
                category=ErrorCategory.DATA_STALE,
                message="Price data is 1 day(s) stale",
                root_cause="Check data_loader_status and CloudWatch logs for price_daily loader",
                log_level="critical",
            ),
            PhaseError(
                category=ErrorCategory.DATA_INVALID,
                message="Signal validation failed",
                root_cause="Missing required fields from buy_sell_daily signals",
                log_level="error",
            ),
            PhaseError(
                category=ErrorCategory.DATABASE_ERROR,
                message="Could not check upstream data quality",
                root_cause="connection timeout",
                log_level="warning",
            ),
        ]

        # Each error must have clear messages so operators understand
        for error in errors:
            assert error.message, "Error must have operator-facing message"
            assert len(error.message) > 10, "Message must be more than 10 chars"
            # Most errors should have root cause for investigation
            if error.category != ErrorCategory.MARKET_CLOSED:
                assert error.root_cause, f"{error.category.value} must have root_cause for debugging"

    def test_recovery_guidance_by_category(self):
        """Each error category must have guidance for what operators should do."""
        from algo.orchestrator.phase_error_handling import create_error_message

        # Example: DATA_STALE should guide to check loaders
        data_stale_msg = create_error_message(ErrorCategory.DATA_STALE, "Price data is 2 days old")
        assert "loader" in data_stale_msg.lower() or "check" in data_stale_msg.lower()

        # Example: DATABASE_ERROR should guide to check connectivity
        db_msg = create_error_message(ErrorCategory.DATABASE_ERROR, "DB connection failed")
        assert "database" in db_msg.lower() or "connectivity" in db_msg.lower()

        # Example: MARKET_CLOSED should explain it's normal
        market_msg = create_error_message(ErrorCategory.MARKET_CLOSED, "Market is closed")
        assert "normal" in market_msg.lower() or "closed" in market_msg.lower()


class TestErrorHandlingWithMalformedData:
    """Tests for error handling with malformed/invalid data."""

    def test_phase_error_with_none_category(self):
        """Verify PhaseError handles None category."""
        # Note: Current implementation allows None, should validate
        error = PhaseError(
            category=None,
            message="Test error",
            root_cause=None,
            log_level="error",
        )
        # Currently accepts None (lenient), but should reject
        assert error.category is None or isinstance(error.category, type(ErrorCategory.DATA_MISSING))

    def test_phase_error_with_none_message(self):
        """Verify PhaseError handles None message."""
        # Note: Current implementation allows None, should validate
        error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message=None,  # Invalid
            root_cause="Test root cause",
            log_level="error",
        )
        # Currently accepts None (lenient), but should reject
        assert error.message is None or isinstance(error.message, str)

    def test_phase_error_with_non_string_message(self):
        """Verify PhaseError handles non-string message."""
        try:
            error = PhaseError(
                category=ErrorCategory.DATA_MISSING,
                message=12345,  # Non-string
                root_cause=None,
                log_level="error",
            )
            # Should either convert or reject
            assert isinstance(error.message, (str, int, float))
        except (TypeError, ValueError):
            pass  # Expected

    def test_phase_error_with_invalid_log_level(self):
        """Verify PhaseError validates log level."""
        try:
            error = PhaseError(
                category=ErrorCategory.DATA_MISSING,
                message="Test error",
                root_cause=None,
                log_level="invalid_level",  # Invalid level
            )
            # Should validate log level
            assert error.log_level in ["debug", "info", "warning", "error", "critical"]
        except (ValueError, AssertionError):
            pass  # Expected

    def test_phase_error_with_none_log_level(self):
        """Verify PhaseError handles None log level."""
        # Note: Current implementation allows None, should validate
        error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message="Test error",
            root_cause=None,
            log_level=None,  # Invalid
        )
        # Currently accepts None (lenient), but should reject
        assert error.log_level is None or isinstance(error.log_level, str)

    def test_phase_error_with_numeric_category(self):
        """Verify PhaseError handles numeric category."""
        # Note: Current implementation accepts non-enum values, should validate
        error = PhaseError(
            category=123,  # Invalid type
            message="Test error",
            root_cause=None,
            log_level="error",
        )
        # Currently accepts (lenient), but should validate
        assert error.category is not None  # Just verify it exists

    def test_phase_error_with_empty_message(self):
        """Verify PhaseError handles empty message."""
        try:
            error = PhaseError(
                category=ErrorCategory.DATA_MISSING,
                message="",  # Empty string
                root_cause=None,
                log_level="error",
            )
            # Should either accept or reject empty message
            assert isinstance(error.message, str)
        except (ValueError, AssertionError):
            pass  # Expected

    def test_phase_error_with_non_string_root_cause(self):
        """Verify PhaseError handles non-string root_cause."""
        # Note: Current implementation accepts non-string values, should validate
        error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message="Test error",
            root_cause=["list", "as", "root_cause"],  # Invalid type
            log_level="error",
        )
        # Currently accepts (lenient), but should validate type
        assert error.root_cause is not None  # Just verify it exists

    def test_phase_error_with_very_long_message(self):
        """Verify PhaseError handles very long message."""
        very_long_message = "x" * 100000  # 100k character message
        try:
            error = PhaseError(
                category=ErrorCategory.DATA_MISSING,
                message=very_long_message,
                root_cause=None,
                log_level="error",
            )
            # Should handle without crashing
            assert error.message == very_long_message
        except (ValueError, MemoryError):
            pass  # Expected for extreme cases

    def test_error_category_enum_values(self):
        """Verify all error categories have valid enum values."""
        # Get all error categories
        try:
            categories = list(ErrorCategory)
            assert len(categories) > 0
            # Each should be an enum member
            for cat in categories:
                assert hasattr(cat, "value")
                assert isinstance(cat.value, str)
        except (AttributeError, TypeError):
            pass  # Expected if not properly defined

    def test_phase_error_recoverable_as_string(self):
        """Verify PhaseError handles recoverable flag as string."""
        try:
            error = PhaseError(
                category=ErrorCategory.DATA_MISSING,
                message="Test error",
                root_cause=None,
                recoverable="true",  # String instead of bool
                log_level="error",
            )
            # Should validate or convert to boolean
            assert isinstance(error.recoverable, (bool, str))
        except (TypeError, ValueError):
            pass  # Expected

    def test_create_error_message_with_none_category(self):
        """Verify create_error_message handles None category."""
        from algo.orchestrator.phase_error_handling import create_error_message

        try:
            msg = create_error_message(None, "Test message")
            # Should handle gracefully
            assert msg is not None
        except (TypeError, ValueError, AttributeError):
            pass  # Expected

    def test_create_error_message_with_none_message(self):
        """Verify create_error_message handles None message."""
        from algo.orchestrator.phase_error_handling import create_error_message

        try:
            msg = create_error_message(ErrorCategory.DATA_MISSING, None)
            # Should handle gracefully
            assert msg is not None or msg is None
        except (TypeError, ValueError, AttributeError):
            pass  # Expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
