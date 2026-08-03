"""Test Phase 1 afternoon re-validation fix (2026-08-02).

ISSUE: Phase 1 checked for pipeline_context in ("AFTERNOON", "EVENING") but
pipeline_context was set to ("MORNING", "INTRADAY", "EOD"). This meant the
afternoon re-validation was dead code - never executed.

FIX: Changed line 658 to check for ("INTRADAY", "EOD") which are the actual
context values assigned for afternoon/evening hours.

Test: Verify that INTRADAY context (10am-4pm) and EOD context (4pm+) now
trigger today's price validation.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
import pytest
from algo.orchestrator.phase1_data_freshness import run as run_phase1


def test_afternoon_context_triggers_todays_price_validation():
    """Test that INTRADAY context (afternoon) triggers today's price check."""
    config = {
        "phase1_min_coverage_pct": 70,
        "phase1_min_symbol_count": 1000,
        "phase1_recent_cutoff_days": 1,
        "phase1_prior_cutoff_days": 5,
        "phase1_halt_table_max_tolerance_days": 1,
    }
    run_date = date(2026, 8, 2)  # Friday
    alerts = MagicMock()
    verbose = False
    log_phase_result_fn = MagicMock()

    # Mock the afternoon time (2 PM ET = hour 14)
    mock_now_et = datetime(2026, 8, 2, 14, 0, 0, tzinfo=timezone.utc).astimezone(tz=None)

    with patch("algo.orchestrator.phase1_data_freshness.dt") as mock_dt:
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
            with patch("algo.orchestrator.phase1_data_freshness.EASTERN_TZ") as mock_tz:
                with patch("algo.orchestrator.phase1_data_freshness.check_and_retry_incomplete_loaders") as mock_failsafe:
                    with patch("algo.orchestrator.phase1_data_freshness.MarketCalendar") as mock_calendar:
                        # Set up time mocking
                        mock_dt.now.return_value = mock_now_et
                        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

                        # Mock EASTERN_TZ
                        mock_tz_obj = MagicMock()
                        mock_tz_obj.__name__ = "US/Eastern"
                        mock_tz = mock_tz_obj

                        # Set up failsafe to pass (no incomplete loaders)
                        mock_failsafe.return_value = {
                            "incomplete_loaders": [],
                            "retried": [],
                            "recovered": [],
                            "still_failing": [],
                            "halt_required": False,
                        }

                        # Mock database cursor
                        mock_cursor = MagicMock()
                        mock_db.return_value.__enter__.return_value = mock_cursor

                        # Set up mock responses for database queries
                        def mock_execute(query, *args):
                            if "MAX(date)" in query and "price_daily" in query:
                                # Return yesterday's data
                                mock_cursor.fetchone.return_value = (date(2026, 8, 1),)
                            elif "COUNT(*) FROM stock_symbols" in query:
                                mock_cursor.fetchone.return_value = (5500,)
                            elif "COUNT(DISTINCT pd.symbol)" in query and len(args) > 0:
                                # Check if this is the today's data query
                                param = args[0][0] if args and args[0] else None
                                if param == run_date:
                                    # Today's data query - should be called in INTRADAY context
                                    mock_cursor.fetchone.return_value = (1500,)
                                else:
                                    # Yesterday's data query
                                    mock_cursor.fetchone.return_value = (5400,)
                            elif "market_health_daily" in query:
                                mock_cursor.fetchone.return_value = (date(2026, 8, 1),)
                            else:
                                mock_cursor.fetchone.return_value = None

                        mock_cursor.execute.side_effect = mock_execute

                        # Mock market calendar
                        mock_calendar.is_trading_day.return_value = True

                        # Run phase 1
                        result = run_phase1(config, run_date, False, alerts, verbose, log_phase_result_fn)

                        # Verify that the cursor was called with today's date for price validation
                        # Count how many times we queried for today's prices
                        today_price_calls = [
                            c for c in mock_cursor.execute.call_args_list
                            if "COUNT(DISTINCT pd.symbol)" in str(c) and call_args_has_date(c, run_date)
                        ]

                        # In INTRADAY context, we should have queried for today's prices
                        # (in addition to yesterday's prices for the main freshness check)
                        assert len(today_price_calls) > 0, (
                            "INTRADAY context should trigger today's price validation query. "
                            "This verifies the fix for pipeline_context check (was checking "
                            "('AFTERNOON', 'EVENING') instead of ('INTRADAY', 'EOD'))"
                        )


def test_eod_context_triggers_todays_price_validation():
    """Test that EOD context (4pm+) also triggers today's price check."""
    config = {
        "phase1_min_coverage_pct": 70,
        "phase1_min_symbol_count": 1000,
        "phase1_recent_cutoff_days": 1,
        "phase1_prior_cutoff_days": 5,
        "phase1_halt_table_max_tolerance_days": 1,
    }
    run_date = date(2026, 8, 2)  # Friday
    alerts = MagicMock()
    verbose = False
    log_phase_result_fn = MagicMock()

    # Mock the EOD time (5 PM ET = hour 17, after 4:30 grace period)
    mock_now_et = datetime(2026, 8, 2, 17, 0, 0, tzinfo=timezone.utc).astimezone(tz=None)

    with patch("algo.orchestrator.phase1_data_freshness.dt") as mock_dt:
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as mock_db:
            with patch("algo.orchestrator.phase1_data_freshness.EASTERN_TZ") as mock_tz:
                with patch("algo.orchestrator.phase1_data_freshness.check_and_retry_incomplete_loaders") as mock_failsafe:
                    with patch("algo.orchestrator.phase1_data_freshness.MarketCalendar") as mock_calendar:
                        # Set up time mocking
                        mock_dt.now.return_value = mock_now_et
                        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

                        # Set up failsafe to pass
                        mock_failsafe.return_value = {
                            "incomplete_loaders": [],
                            "retried": [],
                            "recovered": [],
                            "still_failing": [],
                            "halt_required": False,
                        }

                        # Mock database cursor
                        mock_cursor = MagicMock()
                        mock_db.return_value.__enter__.return_value = mock_cursor

                        # Set up mock responses
                        def mock_execute(query, *args):
                            if "MAX(date)" in query and "price_daily" in query:
                                mock_cursor.fetchone.return_value = (date(2026, 8, 2),)
                            elif "COUNT(*) FROM stock_symbols" in query:
                                mock_cursor.fetchone.return_value = (5500,)
                            elif "COUNT(DISTINCT pd.symbol)" in query:
                                mock_cursor.fetchone.return_value = (5400,)
                            elif "market_health_daily" in query:
                                mock_cursor.fetchone.return_value = (date(2026, 8, 2),)
                            else:
                                mock_cursor.fetchone.return_value = None

                        mock_cursor.execute.side_effect = mock_execute

                        # Mock market calendar
                        mock_calendar.is_trading_day.return_value = True

                        # Run phase 1
                        result = run_phase1(config, run_date, False, alerts, verbose, log_phase_result_fn)

                        # Verify that we queried for today's prices in EOD context
                        today_price_calls = [
                            c for c in mock_cursor.execute.call_args_list
                            if "COUNT(DISTINCT pd.symbol)" in str(c) and call_args_has_date(c, run_date)
                        ]

                        # In EOD context after grace period, we should validate today's prices
                        assert len(today_price_calls) > 0, (
                            "EOD context (after 4:30 PM) should trigger today's price validation. "
                            "Verifies fix for pipeline_context check."
                        )


def call_args_has_date(call_obj, target_date):
    """Helper to check if a call includes the target date in its arguments."""
    if call_obj.args:
        for arg in call_obj.args:
            if arg == target_date:
                return True
    if call_obj.kwargs:
        for val in call_obj.kwargs.values():
            if val == target_date:
                return True
    return False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
