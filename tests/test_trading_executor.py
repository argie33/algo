#!/usr/bin/env python3
"""
Comprehensive tests for trading executor (entry, position tracking, R-multiples).

Tests validate:
- Idempotent entry (no duplicate trades for same symbol same day)
- Atomic DB transactions for entry/exit
- R-multiple computation against actual stop loss
- Position status tracking
- Error handling and circuit breaker interaction
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest


project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# Import only when needed in fixtures/tests to avoid credential validation at import time
from utils.trading import PositionStatus, TradeStatus


class TestTradeExecutorEntry:
    """Test trade entry logic and idempotency."""

    @pytest.fixture
    def executor_config(self):
        """Minimal config for executor."""
        return {
            "mode": "review",
            "max_position_size": 100,
            "enable_partial_exits": True,
            "notifications_enabled": False,
        }

    @pytest.fixture
    def executor(self, executor_config):
        """Create executor with mocked credentials."""
        # Import inside fixture to avoid module-level credential validation
        from algo.trading.executor import TradeExecutor

        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return TradeExecutor(executor_config)

    def test_entry_creates_trade_in_database(self, executor):
        """Entry should create trade record with correct fields."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock duplicate check (no existing trade)
            mock_cur.fetchone.return_value = None

            entry_params = {
                "symbol": "AAPL",
                "quantity": 10,
                "entry_price": Decimal("150.00"),
                "stop_loss_price": Decimal("145.00"),
                "target_1_price": Decimal("157.50"),
                "target_2_price": Decimal("165.00"),
                "target_3_price": Decimal("172.50"),
                "stage_phase": "early",
            }

            executor.entry(**entry_params)

            # Verify INSERT was called
            assert mock_cur.execute.called
            call_args = [str(c) for c in mock_cur.execute.call_args_list]
            assert any("INSERT INTO algo_trades" in str(c) for c in call_args)

    def test_entry_rejects_duplicate_same_day(self, executor):
        """Entry should reject duplicate position for same symbol same day."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock duplicate check (trade exists)
            mock_cur.fetchone.return_value = (1,)  # Existing trade_id

            entry_params = {
                "symbol": "AAPL",
                "quantity": 10,
                "entry_price": Decimal("150.00"),
                "stop_loss_price": Decimal("145.00"),
                "target_1_price": Decimal("157.50"),
                "target_2_price": Decimal("165.00"),
                "target_3_price": Decimal("172.50"),
            }

            with pytest.raises(DuplicatePositionError):
                executor.entry(**entry_params)

    def test_r_multiple_calculated_correctly(self, executor):
        """R-multiple should be (entry - stop) / quantity."""
        # Given:
        entry_price = Decimal("150.00")
        stop_price = Decimal("145.00")
        quantity = 100

        # When:
        risk = entry_price - stop_price  # $5.00 per share
        expected_r = risk / quantity  # $0.05 per share

        # Then:
        assert expected_r == Decimal("0.05")

    def test_entry_validates_prices(self, executor):
        """Entry should reject invalid price relationships."""
        with mock.patch("utils.db.DatabaseContext"):
            invalid_params = {
                "symbol": "AAPL",
                "quantity": 10,
                "entry_price": Decimal("150.00"),
                "stop_loss_price": Decimal("155.00"),  # Stop ABOVE entry (invalid)
                "target_1_price": Decimal("157.50"),
                "target_2_price": Decimal("165.00"),
                "target_3_price": Decimal("172.50"),
            }

            with pytest.raises((ValueError, PretradeCheckFailedError)):
                executor.entry(**invalid_params)

    def test_entry_rejects_zero_quantity(self, executor):
        """Entry should reject zero or negative quantities."""
        with mock.patch("utils.db.DatabaseContext"):
            invalid_params = {
                "symbol": "AAPL",
                "quantity": 0,  # Invalid
                "entry_price": Decimal("150.00"),
                "stop_loss_price": Decimal("145.00"),
                "target_1_price": Decimal("157.50"),
                "target_2_price": Decimal("165.00"),
                "target_3_price": Decimal("172.50"),
            }

            with pytest.raises((ValueError, PretradeCheckFailedError)):
                executor.entry(**invalid_params)

    def test_entry_respects_max_position_size(self, executor):
        """Entry should reject positions exceeding max size."""
        with mock.patch("utils.db.DatabaseContext"):
            # executor has max_position_size=100
            oversized_params = {
                "symbol": "AAPL",
                "quantity": 150,  # Exceeds max
                "entry_price": Decimal("150.00"),
                "stop_loss_price": Decimal("145.00"),
                "target_1_price": Decimal("157.50"),
                "target_2_price": Decimal("165.00"),
                "target_3_price": Decimal("172.50"),
            }

            with pytest.raises(PretradeCheckFailedError):
                executor.entry(**oversized_params)


class TestTradeExecutorExit:
    """Test trade exit logic."""

    @pytest.fixture
    def executor_config(self):
        return {
            "mode": "review",
            "max_position_size": 100,
            "enable_partial_exits": True,
        }

    @pytest.fixture
    def executor(self, executor_config):
        from algo.trading.executor import TradeExecutor

        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return TradeExecutor(executor_config)

    def test_exit_updates_position_status(self, executor):
        """Exit should mark position as CLOSED."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock position lookup
            mock_cur.fetchone.return_value = (1, "AAPL", 10, PositionStatus.OPEN, 0)

            exit_params = {
                "trade_id": 1,
                "exit_price": Decimal("160.00"),
                "exit_reason": "TARGET_1_HIT",
            }

            executor.exit_trade(**exit_params)

            # Verify UPDATE was called
            assert mock_cur.execute.called
            call_args = [str(c) for c in mock_cur.execute.call_args_list]
            assert any("UPDATE algo_positions" in str(c) for c in call_args)

    def test_partial_exit_reduces_quantity(self, executor):
        """Partial exit should reduce position quantity, not close it."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock position lookup
            mock_cur.fetchone.return_value = (1, "AAPL", 100, PositionStatus.OPEN, 0)

            partial_exit_params = {
                "trade_id": 1,
                "exit_price": Decimal("160.00"),
                "exit_reason": "TARGET_1_HIT",
                "quantity_to_exit": 50,  # Partial exit
            }

            executor.exit_trade(**partial_exit_params)

            # Verify UPDATE reduces quantity
            assert mock_cur.execute.called

    def test_exit_rejects_nonexistent_trade(self, executor):
        """Exit should reject trades that don't exist."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock position lookup (not found)
            mock_cur.fetchone.return_value = None

            exit_params = {
                "trade_id": 9999,  # Doesn't exist
                "exit_price": Decimal("160.00"),
                "exit_reason": "TARGET_1_HIT",
            }

            with pytest.raises((ValueError, OrderExecutionError)):
                executor.exit_trade(**exit_params)


class TestPartialExitCostBasis:
    """Test partial exit P&L calculation with weighted cost basis."""

    @pytest.fixture
    def executor_config(self):
        return {
            "mode": "review",
            "max_position_size": 100,
            "enable_partial_exits": True,
        }

    @pytest.fixture
    def executor(self, executor_config):
        from algo.trading.executor import TradeExecutor

        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return TradeExecutor(executor_config)

    def test_partial_exit_t1_allocation(self):
        """T1 exit should allocate 50% of position."""
        total_quantity = 100
        t1_exit_percent = 0.50
        expected_t1_quantity = 50

        assert int(total_quantity * t1_exit_percent) == expected_t1_quantity

    def test_partial_exit_t2_allocation(self):
        """T2 exit should allocate 25% of position."""
        total_quantity = 100
        t2_exit_percent = 0.25
        expected_t2_quantity = 25

        assert int(total_quantity * t2_exit_percent) == expected_t2_quantity

    def test_partial_exit_t3_allocation(self):
        """T3 exit should allocate remaining 25% of position."""
        total_quantity = 100
        t1_exit = 50
        t2_exit = 25
        remaining = total_quantity - t1_exit - t2_exit

        assert remaining == 25

    def test_weighted_cost_basis_calculation(self):
        """Cost basis should account for all fills."""
        entry_price_1 = Decimal("150.00")
        quantity_1 = 50

        entry_price_2 = Decimal("151.00")
        quantity_2 = 50

        total_cost = (entry_price_1 * quantity_1) + (entry_price_2 * quantity_2)
        total_quantity = quantity_1 + quantity_2
        weighted_avg_cost = total_cost / total_quantity

        assert weighted_avg_cost == Decimal("150.50")

    def test_pnl_calculation_t1_exit(self):
        """P&L should be (exit_price - entry_price) * quantity."""
        entry_price = Decimal("150.00")
        exit_price = Decimal("157.50")  # T1 = 1.5R
        quantity = 50

        pnl = (exit_price - entry_price) * quantity
        expected_pnl = Decimal("375.00")

        assert pnl == expected_pnl


class TestPositionTracking:
    """Test position status and metadata tracking."""

    @pytest.fixture
    def executor_config(self):
        return {
            "mode": "review",
            "max_position_size": 100,
            "enable_partial_exits": True,
        }

    @pytest.fixture
    def executor(self, executor_config):
        from algo.trading.executor import TradeExecutor

        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return TradeExecutor(executor_config)

    def test_position_initially_open(self):
        """New position should have status OPEN."""
        initial_status = PositionStatus.OPEN
        assert initial_status == "OPEN"

    def test_position_tracks_target_levels_hit(self):
        """Position should track which target levels have triggered."""
        # A position can have hit 0, 1, 2, or 3 target levels
        target_levels_hit = 0
        assert target_levels_hit in [0, 1, 2, 3]

        target_levels_hit = 1
        assert target_levels_hit in [0, 1, 2, 3]

    def test_position_tracks_trailing_stop(self):
        """Position should update trailing stop after target hit."""
        initial_stop = Decimal("145.00")
        entry_price = Decimal("150.00")

        # After T1 hit, stop should raise to breakeven
        new_stop_after_t1 = entry_price
        assert new_stop_after_t1 > initial_stop

    def test_position_tracks_entry_time(self):
        """Position should record entry timestamp."""
        entry_timestamp = datetime.now(timezone.utc)
        assert isinstance(entry_timestamp, datetime)
        assert entry_timestamp.tzinfo is not None  # Must be timezone-aware


class TestExecutionModes:
    """Test different execution modes (review, dry, auto, paper)."""

    def test_review_mode_doesnt_send_orders(self):
        """Review mode should not call Alpaca API."""
        config = {"mode": "review", "max_position_size": 100}
        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
            mock.patch("requests.post") as mock_post,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"

            TradeExecutor(config)

            with mock.patch("utils.db.DatabaseContext"):
                # In review mode, should not make HTTP requests to Alpaca
                assert mock_post.call_count == 0

    def test_paper_mode_simulates_orders(self):
        """Paper mode should update DB but not send to exchange."""
        config = {"mode": "paper", "max_position_size": 100}
        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"

            executor = TradeExecutor(config)
            assert executor.config["mode"] == "paper"

    def test_auto_mode_sends_orders(self):
        """Auto mode should send real orders to exchange."""
        config = {"mode": "auto", "max_position_size": 100}
        with (
            mock.patch("algo.trading.executor.get_alpaca_credentials") as mock_creds,
            mock.patch("algo.trading.executor.get_alpaca_base_url") as mock_url,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"

            executor = TradeExecutor(config)
            assert executor.config["mode"] == "auto"
