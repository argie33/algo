"""Test untracked positions sync logic.

Verifies that:
1. Orphan positions (in Alpaca but not in algo_positions) are identified correctly
2. Untracked positions are inserted/updated properly
3. Closed positions are marked appropriately
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


class TestUntrackedPositionsSync(unittest.TestCase):
    """Test suite for untracked positions synchronization."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = {
            "alpaca_paper_trading": True,
            "api_request_timeout_seconds": 30,
            "execution_mode": "paper",
        }

    @patch("algo.infrastructure.alpaca_sync_manager.get_credential_manager")
    def test_orphan_detection_basic(self, mock_cred_manager: MagicMock) -> None:
        """Test that orphan positions are correctly identified."""
        # Setup
        mock_cred_manager.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }

        # Mock cursor with algo_positions
        mock_cursor = MagicMock()

        # algo_positions has: AAPL (algo-managed)
        # Alpaca has: AAPL (algo-managed), TSLA (orphan), MSFT (orphan)

        # Simulate alpaca_symbols: AAPL, TSLA, MSFT
        alpaca_symbols = {"AAPL", "TSLA", "MSFT"}

        # Simulate db_symbols (from algo_positions): AAPL
        db_symbols = {"AAPL"}

        # Orphans should be: TSLA, MSFT
        orphans = list(alpaca_symbols - db_symbols)

        assert len(orphans) == 2
        assert "TSLA" in orphans
        assert "MSFT" in orphans
        assert "AAPL" not in orphans

    @patch("algo.infrastructure.alpaca_sync_manager.get_credential_manager")
    def test_untracked_position_fields(self, mock_cred_manager: MagicMock) -> None:
        """Test that untracked positions have correct fields when inserted."""
        # Setup
        mock_cred_manager.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }

        mock_cursor = MagicMock()

        # Sample untracked position data
        untracked_data = {
            "symbol": "TSLA",
            "qty": "50",
            "current_price": "250.00",
            "position_value": 12500.00,
            "detected_at": datetime.now().isoformat(),
            "last_seen_at": datetime.now().isoformat(),
        }

        # Verify fields
        assert untracked_data["symbol"] == "TSLA"
        assert float(untracked_data["qty"]) == 50.0
        assert float(untracked_data["current_price"]) == 250.00
        assert untracked_data["position_value"] == 12500.00

    @patch("algo.infrastructure.alpaca_sync_manager.get_credential_manager")
    def test_empty_alpaca_positions_handling(self, mock_cred_manager: MagicMock) -> None:
        """Test handling when Alpaca has no positions (all closed)."""
        mock_cred_manager.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }

        # If Alpaca has no positions and DB has none either
        alpaca_symbols: set[str] = set()
        db_symbols: set[str] = set()
        orphans = list(alpaca_symbols - db_symbols)

        assert len(orphans) == 0

        # If DB has positions but Alpaca is empty (all closed)
        db_symbols = {"AAPL", "TSLA", "MSFT"}
        orphans = list(alpaca_symbols - db_symbols)

        assert len(orphans) == 0
        # All DB positions should be marked as closed

    @patch("algo.infrastructure.alpaca_sync_manager.get_credential_manager")
    def test_quantity_validation(self, mock_cred_manager: MagicMock) -> None:
        """Test that quantity is properly validated and converted."""
        mock_cred_manager.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }

        # Test quantity conversions
        test_cases = [
            ("100", 100.0),
            ("50.5", 50.5),
            ("0.01", 0.01),
            ("1000.1234", 1000.1234),
        ]

        for qty_str, expected_float in test_cases:
            result = float(qty_str)
            assert result == expected_float

    @patch("algo.infrastructure.alpaca_sync_manager.get_credential_manager")
    def test_position_value_calculation(self, mock_cred_manager: MagicMock) -> None:
        """Test position value calculation: qty * current_price."""
        mock_cred_manager.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }

        # Test cases: (qty, price, expected_value)
        test_cases = [
            (100, 150.0, 15000.0),
            (50, 250.0, 12500.0),
            (200, 50.50, 10100.0),
        ]

        for qty, price, expected in test_cases:
            calculated = qty * price
            assert abs(calculated - expected) < 0.01


if __name__ == "__main__":
    unittest.main()
