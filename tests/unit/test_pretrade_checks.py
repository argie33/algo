"""
Unit tests for pre-trade validation checks.

Tests the algo_pretrade_checks module which runs before every trade:
- Maximum position size enforcement
- Buying power validation
- Market hours verification
- Symbol blocklist checks
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, time, datetime, timedelta


@pytest.mark.unit
class TestPretradeChecks:
    """Unit tests for pre-trade validation logic."""

    def test_maximum_position_size_enforcement(self):
        """Should reject positions exceeding max size."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'max_position_size_pct': 8.0,
        }

        checks = PretradeChecks(config)

        # Mock cursor and connection
        mock_cur = MagicMock()
        portfolio_value = 100000.0
        proposed_position = 10000.0  # 10% > 8% max

        result = checks.check_position_size(proposed_position, portfolio_value)

        # Should fail - position too large
        assert result is False or result.get('status') == 'rejected'

    def test_position_size_within_limits(self):
        """Should allow positions within max size."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'max_position_size_pct': 8.0,
        }

        checks = PretradeChecks(config)

        portfolio_value = 100000.0
        proposed_position = 7000.0  # 7% < 8% max

        result = checks.check_position_size(proposed_position, portfolio_value)

        # Should pass - position within limits
        assert result is True or result.get('status') == 'approved'

    def test_buying_power_check_passes_sufficient_funds(self):
        """Should allow trades when buying power is sufficient."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {}

        checks = PretradeChecks(config)

        buying_power = 50000.0
        trade_cost = 10000.0  # Less than buying power

        result = checks.check_buying_power(trade_cost, buying_power)

        # Should pass - sufficient buying power
        assert result is True or result.get('status') == 'approved'

    def test_buying_power_check_fails_insufficient_funds(self):
        """Should reject trades when buying power is insufficient."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {}

        checks = PretradeChecks(config)

        buying_power = 5000.0
        trade_cost = 10000.0  # More than buying power

        result = checks.check_buying_power(trade_cost, buying_power)

        # Should fail - insufficient buying power
        assert result is False or result.get('status') == 'rejected'

    def test_market_hours_check_allows_trading_hours(self):
        """Should allow trades during market hours."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'market_open': '09:30',
            'market_close': '16:00',
        }

        checks = PretradeChecks(config)

        # Mock time during market hours (10:00 AM)
        mock_now = datetime.combine(date.today(), time(10, 0, 0))

        result = checks.check_market_hours(mock_now)

        # Should pass - within market hours
        assert result is True or result.get('status') == 'approved'

    def test_market_hours_check_rejects_before_open(self):
        """Should reject trades before market open."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'market_open': '09:30',
            'market_close': '16:00',
        }

        checks = PretradeChecks(config)

        # Mock time before market open (8:00 AM)
        mock_now = datetime.combine(date.today(), time(8, 0, 0))

        result = checks.check_market_hours(mock_now)

        # Should fail - before market open
        assert result is False or result.get('status') == 'rejected'

    def test_market_hours_check_rejects_after_close(self):
        """Should reject trades after market close."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'market_open': '09:30',
            'market_close': '16:00',
        }

        checks = PretradeChecks(config)

        # Mock time after market close (5:00 PM)
        mock_now = datetime.combine(date.today(), time(17, 0, 0))

        result = checks.check_market_hours(mock_now)

        # Should fail - after market close
        assert result is False or result.get('status') == 'rejected'

    def test_symbol_blocklist_allows_non_blocked(self):
        """Should allow trading symbols not on blocklist."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'symbol_blocklist': ['TSLA', 'GME', 'AMC'],
        }

        checks = PretradeChecks(config)

        symbol = 'AAPL'

        result = checks.check_symbol_blocklist(symbol)

        # Should pass - symbol not on blocklist
        assert result is True or result.get('status') == 'approved'

    def test_symbol_blocklist_rejects_blocked_symbols(self):
        """Should reject trading symbols on blocklist."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'symbol_blocklist': ['TSLA', 'GME', 'AMC'],
        }

        checks = PretradeChecks(config)

        symbol = 'TSLA'

        result = checks.check_symbol_blocklist(symbol)

        # Should fail - symbol is blocklisted
        assert result is False or result.get('status') == 'rejected'

    def test_comprehensive_pretrade_check_all_pass(self):
        """Should approve trade when all checks pass."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'max_position_size_pct': 8.0,
            'market_open': '09:30',
            'market_close': '16:00',
            'symbol_blocklist': ['TSLA', 'GME'],
        }

        checks = PretradeChecks(config)

        # All parameters valid
        portfolio_value = 100000.0
        proposed_position = 7000.0
        buying_power = 50000.0
        trade_cost = 5000.0
        symbol = 'AAPL'
        mock_now = datetime.combine(date.today(), time(10, 0, 0))

        # Run all checks
        results = checks.run_all_checks(
            proposed_position=proposed_position,
            portfolio_value=portfolio_value,
            buying_power=buying_power,
            trade_cost=trade_cost,
            symbol=symbol,
            timestamp=mock_now
        )

        # Should approve - all checks pass
        assert results.get('approved') is True or results.get('all_passed') is True

    def test_comprehensive_pretrade_check_fails_one(self):
        """Should reject trade if any check fails."""
        from algo.algo_pretrade_checks import PretradeChecks

        config = {
            'max_position_size_pct': 8.0,
            'market_open': '09:30',
            'market_close': '16:00',
            'symbol_blocklist': ['TSLA', 'GME'],
        }

        checks = PretradeChecks(config)

        # Position exceeds max size
        portfolio_value = 100000.0
        proposed_position = 10000.0  # 10% > 8% max
        buying_power = 50000.0
        trade_cost = 5000.0
        symbol = 'AAPL'
        mock_now = datetime.combine(date.today(), time(10, 0, 0))

        results = checks.run_all_checks(
            proposed_position=proposed_position,
            portfolio_value=portfolio_value,
            buying_power=buying_power,
            trade_cost=trade_cost,
            symbol=symbol,
            timestamp=mock_now
        )

        # Should reject - position size check fails
        assert results.get('approved') is False or results.get('all_passed') is False
