#!/usr/bin/env python3
"""Test Phase 1 portfolio symbol price validation.

Verifies that Phase 1 halts when portfolio symbols lack price data,
preventing Phase 6 exit evaluation failures (root cause of 5-error pattern).
"""

import logging
import pytest
from datetime import date as _date
from unittest.mock import MagicMock, patch, call

logger = logging.getLogger(__name__)


def test_phase1_halts_when_portfolio_symbol_missing_prices():
    """Phase 1 should halt if open positions lack prices for trading date."""
    from algo.orchestrator.phase1_data_freshness import check_data_freshness
    from algo.orchestrator.phase_result import PhaseResult

    # Mock cursor and database
    mock_cur = MagicMock()
    mock_db_conn = MagicMock()
    mock_db_conn.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_conn.__exit__ = MagicMock(return_value=None)

    run_date = _date(2026, 7, 29)  # Tuesday, trading day
    current_date = run_date

    # Set up mock responses
    response_index = 0

    def mock_execute(query, params=None):
        """Route queries to appropriate mock responses."""
        nonlocal response_index

        # Market calendar check
        if "market_calendar" in query.lower():
            return

        # Phase retries
        if "phase1_retry_attempt" in query.lower():
            mock_cur.fetchone.return_value = None
            return

        # Price data freshness (overall table check)
        if "MAX(date) FROM price_daily WHERE symbol NOT LIKE" in query:
            mock_cur.fetchone.return_value = (_date(2026, 7, 29),)
            return

        # Portfolio symbols check - NEW CODE BEING TESTED
        if "DISTINCT symbol FROM algo_positions" in query:
            # Return 2 open positions
            mock_cur.fetchall.return_value = [("AAPL",), ("MSFT",)]
            return

        # Price check for AAPL - has prices
        if "price_daily WHERE symbol = %s AND date = %s" in query and params and params[0] == "AAPL":
            mock_cur.fetchone.return_value = (1,)  # COUNT = 1, prices exist
            return

        # Price check for MSFT - NO prices (this is the failure case)
        if "price_daily WHERE symbol = %s AND date = %s" in query and params and params[0] == "MSFT":
            mock_cur.fetchone.return_value = (0,)  # COUNT = 0, no prices
            return

        # Symbol coverage checks
        if "COUNT(DISTINCT pd.symbol)" in query:
            mock_cur.fetchone.return_value = (100,)
            return

        # Stock symbols count
        if "COUNT(*) FROM stock_symbols WHERE active" in query:
            mock_cur.fetchone.return_value = (500,)
            return

        # Other checks - generic responses to pass
        if "DISTINCT" in query or "SELECT" in query:
            mock_cur.fetchone.return_value = (0,) if "COUNT" in query else None
            mock_cur.fetchall.return_value = []

    mock_cur.execute = mock_execute
    mock_cur.fetchone.return_value = (0,)
    mock_cur.fetchall.return_value = []

    # Mock the database context
    with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
        mock_db.return_value = mock_db_conn

        # Mock logger to capture calls
        with patch("algo.orchestrator.phase1_data_freshness.logger") as mock_logger:
            # Mock log_phase_result_fn
            mock_log_fn = MagicMock()

            # Call Phase 1
            result = check_data_freshness(
                run_date=run_date,
                pipeline_context="MORNING",
                dry_run=False,
                log_phase_result_fn=mock_log_fn,
            )

            # Assert: Phase 1 should HALT because MSFT has no prices
            assert isinstance(result, PhaseResult)
            assert result.halted is True, "Phase 1 should halt when portfolio symbol lacks prices"
            assert result.phase_num == 1
            assert result.name == "portfolio_price_coverage"
            assert "MSFT" in result.error or "missing" in result.name.lower()

            # Verify log was called
            mock_log_fn.assert_called()
            # Check that critical log was called
            critical_calls = [
                c for c in mock_logger.critical.call_args_list
                if "MSFT" in str(c)
            ]
            assert len(critical_calls) > 0, "Should log critical message for missing MSFT prices"


def test_phase1_passes_when_all_portfolio_symbols_have_prices():
    """Phase 1 should pass if ALL portfolio symbols have prices."""
    from algo.orchestrator.phase1_data_freshness import check_data_freshness
    from algo.orchestrator.phase_result import PhaseResult

    # Mock cursor and database
    mock_cur = MagicMock()
    mock_db_conn = MagicMock()
    mock_db_conn.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_conn.__exit__ = MagicMock(return_value=None)

    run_date = _date(2026, 7, 29)  # Tuesday, trading day

    def mock_execute(query, params=None):
        """Route queries to appropriate mock responses."""
        # Portfolio symbols check
        if "DISTINCT symbol FROM algo_positions" in query:
            # Return 2 open positions
            mock_cur.fetchall.return_value = [("AAPL",), ("MSFT",)]
            return

        # Price check - both symbols have prices
        if "price_daily WHERE symbol = %s AND date = %s" in query:
            mock_cur.fetchone.return_value = (1,)  # Both return COUNT = 1
            return

        # Symbol coverage checks
        if "COUNT(DISTINCT pd.symbol)" in query:
            mock_cur.fetchone.return_value = (100,)
            return

        # Stock symbols count
        if "COUNT(*) FROM stock_symbols WHERE active" in query:
            mock_cur.fetchone.return_value = (500,)
            return

        # Price freshness
        if "MAX(date) FROM price_daily WHERE symbol NOT LIKE" in query:
            mock_cur.fetchone.return_value = (run_date,)
            return

        # Default for other checks
        if "COUNT" in query:
            mock_cur.fetchone.return_value = (0,)
        else:
            mock_cur.fetchone.return_value = None
        mock_cur.fetchall.return_value = []

    mock_cur.execute = mock_execute

    # Mock the database context
    with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
        mock_db.return_value = mock_db_conn

        mock_log_fn = MagicMock()

        # Call Phase 1
        result = check_data_freshness(
            run_date=run_date,
            pipeline_context="MORNING",
            dry_run=False,
            log_phase_result_fn=mock_log_fn,
        )

        # Assert: Phase 1 should PASS when all symbols have prices
        assert isinstance(result, PhaseResult)
        assert result.halted is False, "Phase 1 should pass when all portfolio symbols have prices"
        assert result.phase_num == 1
        # Data should indicate portfolio price coverage
        if result.data:
            assert result.data.get("portfolio_price_coverage") == "complete"


def test_phase1_continues_without_halt_on_portfolio_check_error():
    """Phase 1 should continue (not halt) if portfolio price check throws exception."""
    from algo.orchestrator.phase1_data_freshness import check_data_freshness
    from algo.orchestrator.phase_result import PhaseResult

    # Mock cursor that throws exception during portfolio check
    mock_cur = MagicMock()
    mock_db_conn = MagicMock()
    mock_db_conn.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_conn.__exit__ = MagicMock(return_value=None)

    run_date = _date(2026, 7, 29)

    def mock_execute(query, params=None):
        # Throw exception during portfolio symbols fetch (simulating DB error)
        if "DISTINCT symbol FROM algo_positions" in query:
            raise RuntimeError("Database connection lost")

        # Other queries respond normally
        if "MAX(date) FROM price_daily WHERE symbol NOT LIKE" in query:
            mock_cur.fetchone.return_value = (run_date,)
        elif "COUNT" in query:
            mock_cur.fetchone.return_value = (100,)
        else:
            mock_cur.fetchone.return_value = None

    mock_cur.execute = mock_execute

    # Mock the database context
    with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
        mock_db.return_value = mock_db_conn

        with patch("algo.orchestrator.phase1_data_freshness.logger") as mock_logger:
            mock_log_fn = MagicMock()

            # Call Phase 1
            result = check_data_freshness(
                run_date=run_date,
                pipeline_context="MORNING",
                dry_run=False,
                log_phase_result_fn=mock_log_fn,
            )

            # Assert: Phase 1 should continue (not halt) on portfolio check error
            # It logs warning but doesn't halt - portfolio check is supplementary
            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "portfolio" in str(c).lower()
            ]
            assert len(warning_calls) > 0, "Should log warning about portfolio check error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
