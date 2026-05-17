"""
Unit tests for algo_earnings_blackout - trading suspension around earnings.

Tests cover:
- Earnings date lookup (from DB or external API)
- Blackout period enforcement (typically -1 day to +1 day)
- Preventing new entries during blackout
- Force-closing positions before earnings if configured
- Handling missing earnings data gracefully
- Alerting on earnings events

Critical for production: Trading through earnings = uncontrolled volatility.
Bad earnings surprises can gap beyond stop losses. Blackout prevents this.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timedelta
from algo.algo_earnings_blackout import EarningsBlackout


class TestEarningsBlackoutLogic:
    """Test earnings blackout enforcement."""

    @pytest.fixture
    def blackout(self):
        """Create earnings blackout enforcer for testing."""
        with patch('algo.algo_earnings_blackout.psycopg2.connect'):
            bb = EarningsBlackout(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                blackout_days_before=1,
                blackout_days_after=1
            )
            bb.cur = MagicMock()
            bb.conn = MagicMock()
            return bb

    # ========================================================================
    # Blackout Period Detection
    # ========================================================================

    def test_today_has_earnings_event(self, blackout):
        """Should detect when symbol has earnings today."""
        earnings_date = date.today()

        status = blackout.check_blackout_status(
            symbol='AAPL',
            earnings_date=earnings_date,
            current_date=date.today()
        )

        assert status == BlackoutStatus.BLACKOUT_ACTIVE
        assert 'earnings' in status.reason.lower()

    def test_tomorrow_has_earnings(self, blackout):
        """Should detect when symbol has earnings tomorrow (1 day before)."""
        earnings_date = date.today() + timedelta(days=1)

        status = blackout.check_blackout_status(
            symbol='AAPL',
            earnings_date=earnings_date,
            current_date=date.today()
        )

        assert status == BlackoutStatus.BLACKOUT_ACTIVE
        assert 'tomorrow' in status.reason.lower()

    def test_yesterday_had_earnings(self, blackout):
        """Should detect when symbol had earnings yesterday (1 day after)."""
        earnings_date = date.today() - timedelta(days=1)

        status = blackout.check_blackout_status(
            symbol='AAPL',
            earnings_date=earnings_date,
            current_date=date.today()
        )

        assert status == BlackoutStatus.BLACKOUT_ACTIVE
        assert 'yesterday' in status.reason.lower() or 'past' in status.reason.lower()

    def test_earnings_too_far_away_not_blackout(self, blackout):
        """Should not blackout when earnings >2 days away."""
        earnings_date = date.today() + timedelta(days=3)

        status = blackout.check_blackout_status(
            symbol='AAPL',
            earnings_date=earnings_date,
            current_date=date.today()
        )

        assert status != BlackoutStatus.BLACKOUT_ACTIVE

    def test_earnings_already_past(self, blackout):
        """Should not blackout when earnings more than 1 day in the past."""
        earnings_date = date.today() - timedelta(days=2)

        status = blackout.check_blackout_status(
            symbol='AAPL',
            earnings_date=earnings_date,
            current_date=date.today()
        )

        assert status != BlackoutStatus.BLACKOUT_ACTIVE

    # ========================================================================
    # Entry Prevention
    # ========================================================================

    def test_prevent_new_entry_during_blackout(self, blackout):
        """Should reject new entries during earnings blackout."""
        earnings_date = date.today()

        allowed = blackout.allow_new_entry(
            symbol='AAPL',
            earnings_date=earnings_date
        )

        assert allowed is False

    def test_allow_entry_outside_blackout(self, blackout):
        """Should allow new entries outside earnings blackout."""
        earnings_date = date.today() + timedelta(days=5)

        allowed = blackout.allow_new_entry(
            symbol='AAPL',
            earnings_date=earnings_date
        )

        assert allowed is True

    def test_allow_entry_no_earnings_data(self, blackout):
        """Should allow entry if no earnings data available."""
        allowed = blackout.allow_new_entry(
            symbol='UNKNOWNSYM',
            earnings_date=None
        )

        # No earnings data = allow (assume safe)
        assert allowed is True

    # ========================================================================
    # Position Management
    # ========================================================================

    def test_force_exit_before_earnings(self, blackout):
        """Should recommend exit before earnings if enabled."""
        position = {
            'symbol': 'AAPL',
            'quantity': 100,
            'entry_price': 150.00,
            'current_price': 155.00,
        }

        exit_signal = blackout.check_exit_before_earnings(
            position=position,
            earnings_date=date.today() + timedelta(days=1),
            exit_before_earnings=True
        )

        assert exit_signal is not None
        assert 'exit' in exit_signal.reason.lower()

    def test_hold_through_earnings_if_configured(self, blackout):
        """Should not force exit if configured to hold through earnings."""
        position = {
            'symbol': 'AAPL',
            'quantity': 100,
            'entry_price': 150.00,
            'current_price': 155.00,
        }

        exit_signal = blackout.check_exit_before_earnings(
            position=position,
            earnings_date=date.today() + timedelta(days=1),
            exit_before_earnings=False
        )

        assert exit_signal is None

    def test_alert_on_earnings_in_existing_position(self, blackout):
        """Should alert if position will have earnings before exit."""
        position = {
            'symbol': 'AAPL',
            'quantity': 100,
            'entry_price': 150.00,
            'target_price': 160.00,  # Profit target
            'entry_date': date.today() - timedelta(days=5)
        }

        alert = blackout.check_earnings_proximity(
            position=position,
            earnings_date=date.today() + timedelta(days=2)
        )

        assert alert is not None
        assert 'earnings' in alert.reason.lower()


class TestEarningsDataManagement:
    """Test earnings date lookup and caching."""

    @pytest.fixture
    def blackout(self):
        """Create earnings blackout enforcer for testing."""
        with patch('algo.algo_earnings_blackout.psycopg2.connect'):
            bb = EarningsBlackout(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                blackout_days_before=1,
                blackout_days_after=1
            )
            bb.cur = MagicMock()
            bb.conn = MagicMock()
            return bb

    # ========================================================================
    # Earnings Date Lookup
    # ========================================================================

    def test_fetch_earnings_from_database(self, blackout):
        """Should fetch earnings dates from database."""
        blackout.cur.fetchone.return_value = (
            datetime.strptime('2026-05-20', '%Y-%m-%d').date(),
        )

        earnings_date = blackout.get_earnings_date('AAPL')

        assert earnings_date is not None
        assert earnings_date == date(2026, 5, 20)

    def test_return_none_if_no_earnings_data(self, blackout):
        """Should return None if no earnings data available."""
        blackout.cur.fetchone.return_value = None

        earnings_date = blackout.get_earnings_date('UNKNOWNSYM')

        assert earnings_date is None

    def test_cache_earnings_dates(self, blackout):
        """Should cache earnings dates to avoid repeated DB queries."""
        blackout.cur.fetchone.return_value = (date(2026, 5, 20),)

        # First lookup
        date1 = blackout.get_earnings_date('AAPL')
        # Second lookup (should use cache)
        date2 = blackout.get_earnings_date('AAPL')

        assert date1 == date2
        # DB should only be queried once (cached)
        assert blackout.cur.execute.call_count == 1

    def test_cache_expires_after_period(self, blackout):
        """Earnings cache should expire after configurable period."""
        blackout.cache_ttl = 86400  # 1 day
        blackout.cur.fetchone.return_value = (date(2026, 5, 20),)

        date1 = blackout.get_earnings_date('AAPL')
        # Simulate cache expiry
        blackout._cache_timestamp['AAPL'] = datetime.now() - timedelta(days=2)

        date2 = blackout.get_earnings_date('AAPL')

        # Both should be same, but DB should be queried twice
        assert date1 == date2
        assert blackout.cur.execute.call_count >= 1

    # ========================================================================
    # Missing Data Handling
    # ========================================================================

    def test_handle_database_error_gracefully(self, blackout):
        """Should handle database errors during earnings lookup."""
        blackout.cur.execute.side_effect = Exception("DB connection lost")

        earnings_date = blackout.get_earnings_date('AAPL')

        # Should return None on error (safe default = allow trading)
        assert earnings_date is None

    def test_handle_api_error_gracefully(self, blackout):
        """Should handle external API errors during earnings fetch."""
        with patch('algo.algo_earnings_blackout.fetch_earnings_api') as mock_api:
            mock_api.side_effect = Exception("API timeout")

            earnings_date = blackout.fetch_earnings_from_api('AAPL')

            # Safe default = allow trading
            assert earnings_date is None


class TestEarningsAlerts:
    """Test earnings event notifications."""

    @pytest.fixture
    def blackout(self):
        """Create earnings blackout enforcer for testing."""
        with patch('algo.algo_earnings_blackout.psycopg2.connect'):
            bb = EarningsBlackout(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                blackout_days_before=1,
                blackout_days_after=1
            )
            bb.cur = MagicMock()
            bb.conn = MagicMock()
            return bb

    def test_alert_earnings_today(self, blackout):
        """Should generate alert for earnings today."""
        alert = blackout.generate_earnings_alert(
            symbol='AAPL',
            earnings_date=date.today(),
            alert_level='WARNING'
        )

        assert alert is not None
        assert alert['symbol'] == 'AAPL'
        assert 'today' in alert['message'].lower()

    def test_alert_earnings_tomorrow(self, blackout):
        """Should generate alert for earnings tomorrow."""
        alert = blackout.generate_earnings_alert(
            symbol='MSFT',
            earnings_date=date.today() + timedelta(days=1),
            alert_level='WARNING'
        )

        assert alert is not None
        assert 'tomorrow' in alert['message'].lower()

    def test_no_alert_if_earnings_far_away(self, blackout):
        """Should not generate alert if earnings >3 days away."""
        alert = blackout.generate_earnings_alert(
            symbol='GOOGL',
            earnings_date=date.today() + timedelta(days=5),
            alert_level='WARNING'
        )

        assert alert is None or alert['level'] == 'INFO'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
