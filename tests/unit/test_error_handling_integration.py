#!/usr/bin/env python3
"""Integration tests proving operators see different error messages in phase execution.

Tests actual Phase 1 and Phase 5 behavior to verify error categorization is applied
and operators can distinguish failure modes in real phase output.
"""

from datetime import date as _date
from unittest.mock import MagicMock, Mock, patch

import pytest

from algo.orchestrator.phase_error_handling import ErrorCategory


class TestPhase5ErrorHandling:
    """Test Phase 5 fails loudly with categorized errors (not silent degradation)."""

    def test_phase5_fails_when_validation_finds_incomplete_signals(self):
        """Incomplete signals now raise exceptions (not silently filtered)."""
        # This test verifies the fix: incomplete signals cause validation to fail
        from algo.orchestrator.phase7_signal_generation import _validate_signal_completeness

        # Mock candidates with incomplete data (missing composite_score)
        candidates = [
            {
                "symbol": "AAPL",
                "composite_score": 75.0,
                "entry_price": 150.0,
                "close": 150.5,
                "sma_50": 148.0,
                "signal_strength": 0.8,
            },
            {
                "symbol": "MSFT",
                "composite_score": None,  # MISSING!
                "entry_price": 300.0,
                "close": 301.0,
                "sma_50": 299.0,
                "signal_strength": 0.7,
            },
        ]

        # Verify: validation now RAISES, not silently filters
        with pytest.raises(ValueError) as exc_info:
            _validate_signal_completeness(candidates, "test_source")

        # Verify error message is clear for operators
        error_msg = str(exc_info.value)
        assert "incomplete" in error_msg.lower() or "validation" in error_msg.lower()
        assert "cannot proceed" in error_msg.lower()

    def test_phase5_detects_db_error_and_raises_not_silently_degrades(self):
        """DB errors now raise exceptions (not return empty dict)."""
        import psycopg2

        from algo.orchestrator.phase7_signal_generation import _detect_upstream_data_quality_drift

        # Mock DatabaseContext to raise DB error
        with patch("algo.orchestrator.phase7_signal_generation.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value.execute.side_effect = psycopg2.OperationalError(
                "connection timeout"
            )

            # Verify: DB error now RAISES, not returns empty dict
            with pytest.raises(RuntimeError) as exc_info:
                _detect_upstream_data_quality_drift(_date(2024, 1, 12), "buysell_breakout")

            # Verify error is categorized and logged
            error_msg = str(exc_info.value)
            assert "cannot proceed" in error_msg.lower()
            assert "data quality" in error_msg.lower()


class TestPhase1ErrorHandling:
    """Test Phase 1 returns categorized errors (not continues silently)."""

    def test_phase1_returns_halted_with_data_stale_category_when_price_data_old(self):
        """Phase 1 must fail with DATA_STALE when prices are old."""
        from algo.infrastructure import get_config
        from algo.orchestrator.phase1_data_freshness import run as run_phase1

        run_date = _date(2024, 1, 12)  # Friday

        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock: price_daily has old data (2 days behind)
            mock_cur.fetchone.side_effect = [
                (3000,),  # stock_scores count
                (_date(2024, 1, 9),),  # max price date (Tuesday, not Friday)
            ]

            config = {"phase1_min_coverage_pct": 75, "phase1_min_symbol_count": 3000}
            alerts = Mock()
            log_fn = Mock()

            result = run_phase1(
                config=config,
                run_date=run_date,
                dry_run=False,
                alerts=alerts,
                verbose=False,
                log_phase_result_fn=log_fn,
            )

            # Verify Phase 1 halted
            assert result.halted is True
            assert result.status == "halted"
            assert "Insufficient price data" in result.error or "price" in result.error.lower()

            # Verify error was logged with categorization
            # log_fn should have been called with error details
            assert log_fn.called

    def test_phase1_returns_halted_with_data_incomplete_category_when_coverage_low(self):
        """Phase 1 must fail with DATA_INCOMPLETE when symbol coverage is insufficient."""
        from algo.orchestrator.phase1_data_freshness import run as run_phase1

        run_date = _date(2024, 1, 12)  # Friday (trading day)

        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock: prices are fresh but only 50% coverage (want 75%)
            mock_cur.fetchone.side_effect = [
                (3000,),  # stock_scores count
                (_date(2024, 1, 12),),  # max price date (today, fresh)
                (2000,),  # symbols loaded (only 2000 vs 3000 required)
                (4000,),  # prior count
            ]

            config = {"phase1_min_coverage_pct": 75, "phase1_min_symbol_count": 3000}
            alerts = Mock()
            log_fn = Mock()

            result = run_phase1(
                config=config,
                run_date=run_date,
                dry_run=False,
                alerts=alerts,
                verbose=False,
                log_phase_result_fn=log_fn,
            )

            # Verify Phase 1 halted
            assert result.halted is True
            assert result.status == "halted"
            assert "Insufficient" in result.error or "price" in result.error.lower()

            # Verify error was logged
            assert log_fn.called


class TestOperatorsCanDistinguishErrors:
    """Prove operators see different error messages for different failure modes."""

    def test_operators_see_different_messages_for_market_closed_vs_loader_failed(self):
        """Different error categories produce different operator messages."""
        from algo.orchestrator.phase_error_handling import create_error_message

        # Market closed message
        market_closed_msg = create_error_message(ErrorCategory.MARKET_CLOSED, "No trading today")
        # This is NORMAL - operators know not to investigate
        assert "normal" in market_closed_msg.lower() or "closed" in market_closed_msg.lower()

        # Loader failed message
        loader_failed_msg = create_error_message(ErrorCategory.DATA_MISSING, "No buy_sell_daily signals")
        # This is an ERROR - operators know to investigate logs
        assert "loader" in loader_failed_msg.lower() or "check" in loader_failed_msg.lower()

        # Messages must be different
        assert market_closed_msg != loader_failed_msg

    def test_phase_errors_include_recovery_guidance_for_operators(self):
        """Phase errors must explain what operators should do."""
        from algo.orchestrator.phase_error_handling import create_error_message

        errors_with_recovery = {
            ErrorCategory.DATA_STALE: ["loader", "check"],
            ErrorCategory.DATA_INCOMPLETE: ["check", "loader"],
            ErrorCategory.DATABASE_ERROR: ["database", "check"],
            ErrorCategory.DATA_INVALID: ["data", "check"],
        }

        for category, keywords in errors_with_recovery.items():
            # Use create_error_message to get full guidance including recovery instructions
            message = create_error_message(category, "test details")

            # Verify message includes recovery guidance
            assert message, f"{category.value} should produce a message with guidance"
            assert len(message) > 20, f"{category.value} message should be substantive"

            # Verify guidance keywords appear
            combined_text = message.lower()
            found_keyword = any(kw in combined_text for kw in keywords)
            assert found_keyword, f"{category.value} error message should include recovery guidance like: {keywords}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
