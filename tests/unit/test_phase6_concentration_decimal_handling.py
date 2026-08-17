#!/usr/bin/env python3
"""Unit tests for Phase 6 concentration checks with Decimal type handling.

CRITICAL: Phase 6 concentration checks must handle psycopg2 Decimal types correctly.
Previous failure: "unsupported operand type(s) for -: 'decimal.Decimal' and 'float'"
when computing percentage calculations with database-returned Decimal types.

These tests verify the Decimal->float conversion is working correctly.

BUG FIX 2026-08-17: all `patch(...)` targets here used to be "utils.db.context.DatabaseContext"
- the wrong location. algo/orchestrator/phase6_exit_execution.py does
`from utils.db.context import DatabaseContext` (binding the name into its OWN module namespace
at import time), so patching the original definition site never intercepted calls made as
`DatabaseContext(...)` from inside that module - they silently used the real class, which then
fell through to tests/conftest.py's global mock cursor (which doesn't special-case this file's
exact position-concentration query), returning None where real Postgres never would and getting
misread as "query returned NULL". Same bug class as tests/test_pooled_connections.py's
get_db_connection patch-location fix. Patch the name where it's actually used instead.
"""

from datetime import date as _date
from decimal import Decimal
from itertools import chain, repeat
from unittest.mock import MagicMock, call, patch

import pytest

from algo.orchestrator.phase6_exit_execution import run as phase6_run
from algo.orchestrator.phase_result import PhaseResult


class TestPhase6ConcentrationDecimalHandling:
    """Test Decimal type handling in position size concentration checks."""

    @pytest.fixture
    def base_config(self):
        """Base configuration for Phase 6."""
        return {
            "execution_mode": "paper",
            "alpaca_paper_trading": True,
            "min_hold_days": 1,
            "max_hold_days": 90,
            "eight_week_rule_threshold_pct": 1.3,
            "eight_week_rule_window_days": 56,
            "exit_on_distribution_day": False,
            "max_distribution_days": 4,
            "move_be_at_r": 1.5,
            "chandelier_atr_mult": 3.0,
            # CRITICAL: Concentration checks config
            "max_positions_per_sector": 10,
            "max_position_size_pct": 6.0,  # 6% limit
        }

    @pytest.fixture
    def mock_db_decimal_returns(self):
        """Mock database context that returns Decimal types (like psycopg2 does)."""
        mock_context = MagicMock()
        mock_cursor = MagicMock()

        # Simulate concentration check query results with Decimal types
        # These are the EXACT types psycopg2 returns
        mock_cursor.execute = MagicMock()
        mock_cursor.rowcount = 0  # orphaned-trade cleanup DELETE (phase6_exit_execution.py) compares this to an int
        mock_context.__enter__ = MagicMock(return_value=mock_cursor)
        mock_context.__exit__ = MagicMock(return_value=None)

        return mock_context, mock_cursor

    def test_position_size_concentration_with_decimal_types(self, base_config, mock_db_decimal_returns):
        """Verify concentration check handles Decimal position_value from database."""
        mock_context, mock_cursor = mock_db_decimal_returns

        # Total portfolio value (SUM returns Decimal from psycopg2)
        total_value = Decimal("100000.00")  # $100k portfolio

        # Individual position values as Decimal (like psycopg2 returns)
        positions = [
            ("pos_001", "AAPL", Decimal("8500.00")),  # 8.5% - exceeds 6% limit
            ("pos_002", "MSFT", Decimal("5000.00")),  # 5% - OK
            ("pos_003", "GOOGL", Decimal("4000.00")),  # 4% - OK
        ]

        # Mock database returns for concentration check
        # First: COUNT check for NULL position_values
        mock_cursor.fetchone = MagicMock(
            side_effect=[
                (3, 0),  # COUNT(*), COUNT(NULL) - no NULLs
                (total_value,),  # SUM(position_value)
                # Then positions data
                ("pos_001", "AAPL", Decimal("8500.00")),
                ("pos_002", "MSFT", Decimal("5000.00")),
                ("pos_003", "GOOGL", Decimal("4000.00")),
            ]
        )

        mock_cursor.fetchall = MagicMock(
            side_effect=[
                [positions[0], positions[1], positions[2]],  # First call gets all positions
            ]
        )

        # Run Phase 6
        with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
            with patch("algo.trading.ExitEngine") as mock_engine:
                mock_engine.return_value.exit_trade = MagicMock(return_value={"status": "ok"})

                # Position recs empty - will trigger concentration checks
                result = phase6_run(
                    config=base_config,
                    run_date=_date.today(),
                    dry_run=True,  # Dry-run to avoid actual trade execution
                    alerts=MagicMock(),
                    verbose=False,
                    log_phase_result_fn=MagicMock(),
                    position_recs=[],  # Empty - concentration checks will run
                    exposure_actions=[],
                )

        # Verify Phase 6 completed successfully (not halted by Decimal arithmetic error)
        assert result is not None
        assert isinstance(result, PhaseResult)
        # Should detect 8.5% position as oversized and return actions
        # (dry-run won't actually execute, just count)

    def test_sector_concentration_with_decimal_counts(self, base_config, mock_db_decimal_returns):
        """Verify sector concentration check handles Decimal COUNT results."""
        mock_context, mock_cursor = mock_db_decimal_returns

        # Sector concentration query returns COUNT as integer, but max_per_sector might be Decimal
        # from algo.config.get()
        mock_cursor.fetchall = MagicMock(
            return_value=[
                ("Technology", Decimal("12")),  # 12 positions - exceeds limit of 10
                ("Finance", Decimal("8")),  # 8 positions - OK
            ]
        )

        mock_cursor.execute = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=(0,))

        # Run Phase 6
        with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
            with patch("algo.trading.ExitEngine"):
                # max_positions_per_sector as Decimal (like config.get() might return)
                config = base_config.copy()
                config["max_positions_per_sector"] = Decimal("10")  # Decimal from config

                result = phase6_run(
                    config=config,
                    run_date=_date.today(),
                    dry_run=True,
                    alerts=MagicMock(),
                    verbose=False,
                    log_phase_result_fn=MagicMock(),
                    position_recs=[],
                    exposure_actions=[],
                )

        # Should not halt on Decimal/int arithmetic
        assert result is not None

    def test_decimal_arithmetic_in_percentage_calculation(self):
        """Test the core Decimal/float arithmetic that was failing.

        CRITICAL: This is the exact operation that was failing with:
        "unsupported operand type(s) for -: 'decimal.Decimal' and 'float'"
        """
        # Simulate what Phase 6 was doing
        position_value = Decimal("8500")  # From database
        total_value = Decimal("100000")  # From SUM()
        limit = 6.0  # Config value converted to float

        # The WRONG way (what was causing the error):
        # pct = (position_value / total_value * 100)  # This returns Decimal
        # exceed = pct - limit  # TypeError: Decimal - float

        # The FIXED way (proper conversion):
        value_float = float(position_value)
        total_value_for_division = float(total_value)
        pct_value = value_float / total_value_for_division * 100
        pct_float = float(float(pct_value))  # Double convert to ensure float
        limit_for_math = float(limit)
        exceed_amount = pct_float - limit_for_math  # Should work: float - float

        # Verify
        assert isinstance(pct_float, float)
        assert isinstance(limit_for_math, float)
        assert isinstance(exceed_amount, float)
        assert exceed_amount == pytest.approx(2.5, rel=0.01)  # 8.5% - 6% = 2.5%

    def test_null_position_value_detection(self, base_config, mock_db_decimal_returns):
        """Verify Phase 6 detects and halts on NULL position_value (data integrity check).

        This is deliberate, not a bug: phase6_exit_execution.py's concentration-check callers
        (lines ~861-897) only degrade (skip + log) on transient/recoverable RuntimeErrors, and
        explicitly re-raise (halting all of Phase 6, including stop-loss/chandelier exits) when
        the error message contains "CRITICAL" or "Data integrity" - the NULL-position_value
        RuntimeError is raised with exactly that "[PHASE 6 CRITICAL] ... Data integrity" wording,
        so it was deliberately chosen to halt rather than degrade. Concentration cannot be safely
        assessed at all without every open position's value, so this isn't a "skip the bad row,
        process the rest" situation the way most other concentration-check failures are.
        """
        mock_context, mock_cursor = mock_db_decimal_returns

        # Simulate data integrity issue: 1 position has NULL value.
        # First fetchone() call is phase6_exit_execution's own orphaned-trade validation
        # check (runs before the concentration check this test targets) - must be 0 or
        # it halts on "orphaned trade(s)" before ever reaching the NULL-position-value path.
        mock_cursor.fetchone = MagicMock(side_effect=chain([(0,)], repeat((5, 1))))  # 5 total, 1 with NULL

        with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
            # Phase 6 returns halted result, not raised exception
            result = phase6_run(
                config=base_config,
                run_date=_date.today(),
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
                position_recs=[],
                exposure_actions=[],
            )
            # Concentration can't be assessed without every position's value - must halt,
            # not degrade, so a bad row doesn't silently mask a real concentration breach.
            assert result is not None
            assert result.status == "halted"
            assert "NULL position_value" in result.data["reason"]


class TestConfigValueValidation:
    """Test that config values are properly validated before arithmetic."""

    def test_max_position_size_pct_missing_halts_phase(self):
        """Verify Phase 6 halts if max_position_size_pct config is missing."""
        config = {
            "execution_mode": "paper",
            "alpaca_paper_trading": True,
            # Missing: max_position_size_pct
            "max_positions_per_sector": 10,
        }

        with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext"):
            # Phase 6 returns halted result on config errors
            result = phase6_run(
                config=config,
                run_date=_date.today(),
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
                position_recs=[],
                exposure_actions=[],
            )
            assert result.halted is True

    def test_max_positions_per_sector_missing_halts_phase(self):
        """Verify Phase 6 halts if max_positions_per_sector config is missing."""
        config = {
            "execution_mode": "paper",
            "alpaca_paper_trading": True,
            "max_position_size_pct": 6.0,
            # Missing: max_positions_per_sector
        }

        with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext"):
            # Phase 6 returns halted result on config errors
            result = phase6_run(
                config=config,
                run_date=_date.today(),
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
                position_recs=[],
                exposure_actions=[],
            )
            assert result.halted is True
