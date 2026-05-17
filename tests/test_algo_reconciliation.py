"""
Unit tests for algo_reconciliation - P&L verification and position sync.

Tests cover:
- Fetching live positions from Alpaca
- Verifying quantity matches database
- Calculating P&L (realized + unrealized)
- Detecting orphan trades (in Alpaca but not in DB)
- Detecting stale positions (in DB but not in Alpaca)
- Creating daily portfolio snapshot
- Alerting on significant discrepancies

Critical for production: Reconciliation must catch position tracking bugs
before they become real losses. Stale positions = phantom profit.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime, timedelta
from decimal import Decimal
from algo.algo_reconciliation import Reconciliator, PositionMismatch, ReconciliationResult


class TestPositionSync:
    """Test position synchronization with Alpaca."""

    @pytest.fixture
    def reconciliator(self):
        """Create reconciliator for testing."""
        with patch('algo.algo_reconciliation.psycopg2.connect'):
            recon = Reconciliator(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                alpaca_key='test_key',
                alpaca_secret='test_secret'
            )
            recon.cur = MagicMock()
            recon.conn = MagicMock()
            recon.alpaca = MagicMock()
            return recon

    # ========================================================================
    # Position Matching
    # ========================================================================

    def test_matching_positions_pass(self, reconciliator):
        """Should pass when DB positions match Alpaca."""
        db_position = {'symbol': 'AAPL', 'quantity': 100, 'entry_price': 150.00}
        alpaca_position = MagicMock(
            symbol='AAPL',
            qty=100,
            avg_fill_price=150.00,
            current_price=155.00
        )

        match = reconciliator.match_positions(db_position, alpaca_position)

        assert match['matched'] is True
        assert match['quantity_match'] is True

    def test_quantity_mismatch_detected(self, reconciliator):
        """Should detect quantity mismatches."""
        db_position = {'symbol': 'AAPL', 'quantity': 100}
        alpaca_position = MagicMock(
            symbol='AAPL',
            qty=90,  # 10 shares missing
            avg_fill_price=150.00,
            current_price=155.00
        )

        match = reconciliator.match_positions(db_position, alpaca_position)

        assert match['matched'] is False
        assert match['quantity_match'] is False
        assert match['quantity_difference'] == -10

    def test_detect_partial_fill(self, reconciliator):
        """Should detect when order was only partially filled."""
        db_position = {'symbol': 'AAPL', 'quantity': 100}
        alpaca_position = MagicMock(
            symbol='AAPL',
            qty=75,  # Only 75 of 100 filled
            avg_fill_price=150.00,
            current_price=155.00
        )

        match = reconciliator.match_positions(db_position, alpaca_position)

        assert match['matched'] is False
        assert 'partial' in match.get('reason', '').lower()

    # ========================================================================
    # P&L Calculation
    # ========================================================================

    def test_unrealized_pnl_positive(self, reconciliator):
        """Should calculate positive unrealized P&L correctly."""
        position = {
            'symbol': 'AAPL',
            'quantity': 100,
            'entry_price': 150.00,
            'current_price': 155.00
        }

        pnl = reconciliator.calculate_unrealized_pnl(position)

        assert pnl['profit_loss'] == 500.00
        assert pnl['pct_return'] == 3.33
        assert pnl['is_profitable'] is True

    def test_unrealized_pnl_negative(self, reconciliator):
        """Should calculate negative unrealized P&L correctly."""
        position = {
            'symbol': 'AAPL',
            'quantity': 100,
            'entry_price': 150.00,
            'current_price': 145.00
        }

        pnl = reconciliator.calculate_unrealized_pnl(position)

        assert pnl['profit_loss'] == -500.00
        assert pnl['pct_return'] == -3.33
        assert pnl['is_profitable'] is False

    def test_realized_pnl_on_full_exit(self, reconciliator):
        """Should calculate realized P&L on full position exit."""
        trade = {
            'symbol': 'AAPL',
            'entry_qty': 100,
            'entry_price': 150.00,
            'exit_qty': 100,
            'exit_price': 160.00,
            'commission': 10.00
        }

        pnl = reconciliator.calculate_realized_pnl(trade)

        # (160 - 150) * 100 - 10 commission = 990
        assert pnl['profit_loss'] == 990.00
        assert pnl['pct_return'] == 6.60  # (1000 - 10) / 1500 * 100

    def test_realized_pnl_on_partial_exit(self, reconciliator):
        """Should calculate realized P&L on partial position exit."""
        trade = {
            'symbol': 'AAPL',
            'entry_qty': 100,
            'entry_price': 150.00,
            'exit_qty': 50,
            'exit_price': 160.00,
            'commission': 5.00
        }

        pnl = reconciliator.calculate_realized_pnl(trade)

        # (160 - 150) * 50 - 5 commission = 495
        assert pnl['profit_loss'] == 495.00

    def test_cumulative_pnl_calculation(self, reconciliator):
        """Should calculate total portfolio P&L."""
        positions = [
            {
                'symbol': 'AAPL',
                'quantity': 100,
                'entry_price': 150.00,
                'current_price': 155.00,
                'unrealized_pnl': 500.00
            },
            {
                'symbol': 'MSFT',
                'quantity': 100,
                'entry_price': 300.00,
                'current_price': 295.00,
                'unrealized_pnl': -500.00
            }
        ]

        total_pnl = reconciliator.calculate_portfolio_pnl(
            positions,
            realized_trades=[],
            starting_balance=100000
        )

        assert total_pnl['unrealized'] == 0.00
        assert total_pnl['realized'] == 0.00

    # ========================================================================
    # Orphan Detection
    # ========================================================================

    def test_detect_orphan_alpaca_position(self, reconciliator):
        """Should detect positions in Alpaca but not in DB."""
        db_symbols = ['AAPL', 'MSFT']
        alpaca_positions = [
            MagicMock(symbol='AAPL', qty=100),
            MagicMock(symbol='MSFT', qty=100),
            MagicMock(symbol='GOOGL', qty=100),  # Orphan!
        ]

        orphans = reconciliator.find_orphan_alpaca_positions(db_symbols, alpaca_positions)

        assert len(orphans) == 1
        assert orphans[0].symbol == 'GOOGL'

    def test_detect_stale_db_position(self, reconciliator):
        """Should detect positions in DB but not in Alpaca."""
        db_positions = [
            {'symbol': 'AAPL', 'quantity': 100},
            {'symbol': 'MSFT', 'quantity': 100},
            {'symbol': 'GOOGL', 'quantity': 100},  # Stale!
        ]
        alpaca_symbols = ['AAPL', 'MSFT']

        stale = reconciliator.find_stale_db_positions(db_positions, alpaca_symbols)

        assert len(stale) == 1
        assert stale[0]['symbol'] == 'GOOGL'

    def test_orphan_alert_on_significant_value(self, reconciliator):
        """Should alert when orphan position has significant value."""
        orphan = MagicMock(
            symbol='TSLA',
            qty=50,
            avg_fill_price=200.00,
            current_price=220.00
        )

        alert = reconciliator.check_orphan_alert(orphan)

        assert alert is not None
        assert 'orphan' in alert['reason'].lower()
        assert alert['value'] == 11000.00  # 50 * 220


class TestReconciliationSnapshot:
    """Test daily portfolio snapshot creation."""

    @pytest.fixture
    def reconciliator(self):
        """Create reconciliator for testing."""
        with patch('algo.algo_reconciliation.psycopg2.connect'):
            recon = Reconciliator(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                alpaca_key='test_key',
                alpaca_secret='test_secret'
            )
            recon.cur = MagicMock()
            recon.conn = MagicMock()
            recon.alpaca = MagicMock()
            return recon

    def test_create_snapshot_all_matched(self, reconciliator):
        """Should create snapshot when all positions matched."""
        positions = [
            {
                'symbol': 'AAPL',
                'quantity': 100,
                'entry_price': 150.00,
                'current_price': 155.00,
                'unrealized_pnl': 500.00
            }
        ]

        snapshot = reconciliator.create_daily_snapshot(
            date=date.today(),
            positions=positions,
            cash_balance=50000.00,
            portfolio_value=105000.00
        )

        assert snapshot['date'] == date.today()
        assert snapshot['portfolio_value'] == 105000.00
        assert snapshot['cash_balance'] == 50000.00
        assert snapshot['position_count'] == 1
        assert snapshot['unrealized_pnl'] == 500.00

    def test_snapshot_includes_reconciliation_status(self, reconciliator):
        """Snapshot should include reconciliation success/failure."""
        snapshot = reconciliator.create_daily_snapshot(
            date=date.today(),
            positions=[],
            cash_balance=100000.00,
            portfolio_value=100000.00,
            mismatches=[]
        )

        assert snapshot['reconciliation_status'] == 'OK'
        assert snapshot['mismatch_count'] == 0

    def test_snapshot_alerts_on_discrepancies(self, reconciliator):
        """Snapshot should alert on significant discrepancies."""
        mismatches = [
            PositionMismatch(
                symbol='AAPL',
                db_qty=100,
                alpaca_qty=90,
                discrepancy_value=1500.00
            )
        ]

        snapshot = reconciliator.create_daily_snapshot(
            date=date.today(),
            positions=[],
            cash_balance=100000.00,
            portfolio_value=100000.00,
            mismatches=mismatches
        )

        assert snapshot['reconciliation_status'] == 'MISMATCH'
        assert snapshot['mismatch_count'] == 1


class TestReconciliationErrors:
    """Test error handling in reconciliation."""

    @pytest.fixture
    def reconciliator(self):
        """Create reconciliator for testing."""
        with patch('algo.algo_reconciliation.psycopg2.connect'):
            recon = Reconciliator(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                alpaca_key='test_key',
                alpaca_secret='test_secret'
            )
            recon.cur = MagicMock()
            recon.conn = MagicMock()
            recon.alpaca = MagicMock()
            return recon

    def test_handle_alpaca_connection_error(self, reconciliator):
        """Should handle Alpaca API errors gracefully."""
        reconciliator.alpaca.get_positions.side_effect = Exception("Connection timeout")

        result = reconciliator.reconcile()

        assert result['success'] is False
        assert 'connection' in result['error'].lower() or 'timeout' in result['error'].lower()

    def test_handle_database_error(self, reconciliator):
        """Should handle database errors gracefully."""
        reconciliator.cur.execute.side_effect = Exception("Database connection lost")

        result = reconciliator.reconcile()

        assert result['success'] is False
        assert 'database' in result['error'].lower()

    def test_handle_missing_price_data(self, reconciliator):
        """Should handle positions without current price."""
        position = {
            'symbol': 'FAKESYM',
            'quantity': 100,
            'entry_price': 150.00,
            'current_price': None
        }

        pnl = reconciliator.calculate_unrealized_pnl(position)

        assert pnl['profit_loss'] == 0  # Cannot calculate
        assert pnl['warning'] is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
