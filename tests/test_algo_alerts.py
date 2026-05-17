"""
Unit tests for algo_alerts - trading alerts and notifications.

Tests cover:
- Alert generation for trading events (entry, exit, stop hit)
- Alert severity levels (INFO, WARNING, CRITICAL)
- Alert routing (DB log, email, Slack, SMS)
- Duplicate prevention (don't alert same event twice)
- Alert filtering (suppress low-severity in production)
- Position alerts (profit target hit, stop loss hit, drawdown)
- System alerts (data freshness, API errors, low cash)

Critical for production: Alerts must be timely, accurate, and not spam.
Missing critical alerts = undetected losses. Alert spam = ignored alerts.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta, date
from enum import Enum
from algo.algo_alerts import AlertManager, Alert, AlertLevel, AlertChannel


class TestAlertGeneration:
    """Test alert creation and classification."""

    @pytest.fixture
    def alert_manager(self):
        """Create alert manager for testing."""
        with patch('algo.algo_alerts.psycopg2.connect'):
            mgr = AlertManager(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                slack_webhook='https://hooks.slack.com/test'
            )
            mgr.cur = MagicMock()
            mgr.conn = MagicMock()
            return mgr

    # ========================================================================
    # Alert Creation
    # ========================================================================

    def test_create_entry_alert(self, alert_manager):
        """Should create alert for position entry."""
        alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        assert alert.symbol == 'AAPL'
        assert alert.event_type == 'ENTRY'
        assert alert.quantity == 100
        assert alert.severity == AlertLevel.INFO

    def test_create_exit_alert(self, alert_manager):
        """Should create alert for position exit."""
        alert = alert_manager.create_exit_alert(
            symbol='AAPL',
            quantity=100,
            exit_price=155.00,
            exit_type='TARGET_1',
            profit=500.00
        )

        assert alert.symbol == 'AAPL'
        assert alert.event_type == 'EXIT'
        assert alert.severity == AlertLevel.INFO
        assert alert.profit == 500.00

    def test_create_stop_hit_alert(self, alert_manager):
        """Should create CRITICAL alert when stop loss hit."""
        alert = alert_manager.create_stop_hit_alert(
            symbol='AAPL',
            stop_price=147.00,
            current_price=146.50,
            loss=400.00
        )

        assert alert.symbol == 'AAPL'
        assert alert.event_type == 'STOP_HIT'
        assert alert.severity == AlertLevel.CRITICAL
        assert alert.loss == 400.00

    def test_create_portfolio_alert(self, alert_manager):
        """Should create alert for portfolio-level events."""
        alert = alert_manager.create_portfolio_alert(
            event_type='HIGH_DRAWDOWN',
            severity=AlertLevel.WARNING,
            message='Portfolio down 5% from peak',
            details={'peak_value': 105000, 'current_value': 99750}
        )

        assert alert.event_type == 'HIGH_DRAWDOWN'
        assert alert.severity == AlertLevel.WARNING
        assert 'drawdown' in alert.message.lower()

    def test_create_system_alert(self, alert_manager):
        """Should create alert for system events."""
        alert = alert_manager.create_system_alert(
            event_type='DATA_FRESHNESS',
            severity=AlertLevel.WARNING,
            message='Price data 5 days old'
        )

        assert alert.event_type == 'DATA_FRESHNESS'
        assert alert.severity == AlertLevel.WARNING

    # ========================================================================
    # Alert Severity
    # ========================================================================

    def test_alert_severity_levels(self, alert_manager):
        """Should correctly classify alert severity."""
        # INFO: normal trading events
        info_alert = Alert(
            symbol='AAPL',
            event_type='ENTRY',
            severity=AlertLevel.INFO
        )
        assert info_alert.severity == AlertLevel.INFO

        # WARNING: potential issues
        warn_alert = Alert(
            symbol='AAPL',
            event_type='HIGH_DRAWDOWN',
            severity=AlertLevel.WARNING
        )
        assert warn_alert.severity == AlertLevel.WARNING

        # CRITICAL: immediate action needed
        crit_alert = Alert(
            symbol='AAPL',
            event_type='CIRCUIT_BREAKER',
            severity=AlertLevel.CRITICAL
        )
        assert crit_alert.severity == AlertLevel.CRITICAL

    def test_severity_affects_routing(self, alert_manager):
        """Should route based on severity (INFO to DB, WARNING to Slack, CRITICAL to all)."""
        info_alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        # INFO alerts → DB only
        routes = alert_manager.get_alert_routes(info_alert)
        assert AlertChannel.DATABASE in routes
        assert AlertChannel.SLACK not in routes

        # CRITICAL alerts → all channels
        crit_alert = alert_manager.create_system_alert(
            event_type='HALTED',
            severity=AlertLevel.CRITICAL,
            message='Orchestrator halted'
        )
        routes = alert_manager.get_alert_routes(crit_alert)
        assert AlertChannel.DATABASE in routes
        assert AlertChannel.SLACK in routes
        assert AlertChannel.EMAIL in routes


class TestAlertRouting:
    """Test alert delivery to different channels."""

    @pytest.fixture
    def alert_manager(self):
        """Create alert manager for testing."""
        with patch('algo.algo_alerts.psycopg2.connect'):
            mgr = AlertManager(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                slack_webhook='https://hooks.slack.com/test',
                email_recipients=['dev@example.com']
            )
            mgr.cur = MagicMock()
            mgr.conn = MagicMock()
            return mgr

    # ========================================================================
    # Alert Routing
    # ========================================================================

    def test_route_alert_to_database(self, alert_manager):
        """Should save all alerts to database."""
        alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        with patch.object(alert_manager, 'save_to_database') as mock_save:
            alert_manager.send_alert(alert)
            assert mock_save.called

    def test_route_warning_to_slack(self, alert_manager):
        """Should send WARNING+ alerts to Slack."""
        alert = alert_manager.create_portfolio_alert(
            event_type='HIGH_DRAWDOWN',
            severity=AlertLevel.WARNING,
            message='Portfolio down 5%'
        )

        with patch('algo.algo_alerts.requests.post') as mock_post:
            alert_manager.send_alert(alert)
            # Should call Slack webhook
            assert mock_post.called or alert_manager.slack_webhook is None

    def test_route_critical_to_email(self, alert_manager):
        """Should send CRITICAL alerts via email."""
        alert = alert_manager.create_system_alert(
            event_type='HALTED',
            severity=AlertLevel.CRITICAL,
            message='Orchestrator halted'
        )

        with patch('algo.algo_alerts.send_email') as mock_email:
            alert_manager.send_alert(alert)
            # Should send email
            if alert_manager.email_recipients:
                assert mock_email.called

    def test_dont_route_info_alerts_to_slack(self, alert_manager):
        """Should NOT send INFO alerts to Slack (spam prevention)."""
        alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        with patch('algo.algo_alerts.requests.post') as mock_post:
            alert_manager.send_alert(alert)
            # Should NOT call Slack for INFO
            assert not mock_post.called

    # ========================================================================
    # Alert Delivery
    # ========================================================================

    def test_send_alert_successfully(self, alert_manager):
        """Should successfully send alert through routing."""
        alert = alert_manager.create_system_alert(
            event_type='DATA_LOADED',
            severity=AlertLevel.INFO,
            message='Daily data loaded successfully'
        )

        result = alert_manager.send_alert(alert)

        assert result['success'] is True

    def test_handle_slack_error_gracefully(self, alert_manager):
        """Should handle Slack API errors without crashing."""
        alert = alert_manager.create_system_alert(
            event_type='ERROR',
            severity=AlertLevel.CRITICAL,
            message='Critical error'
        )

        with patch('algo.algo_alerts.requests.post') as mock_post:
            mock_post.side_effect = Exception("Connection timeout")

            # Should not raise exception
            result = alert_manager.send_alert(alert)

            # Should still have saved to DB
            assert result['database'] is True

    def test_handle_database_error_gracefully(self, alert_manager):
        """Should handle database errors when saving alert."""
        alert_manager.cur.execute.side_effect = Exception("DB connection lost")

        alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        # Should not raise exception
        result = alert_manager.send_alert(alert)
        assert result['success'] is False


class TestAlertDeduplication:
    """Test duplicate alert prevention."""

    @pytest.fixture
    def alert_manager(self):
        """Create alert manager for testing."""
        with patch('algo.algo_alerts.psycopg2.connect'):
            mgr = AlertManager(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                dedup_window_minutes=30
            )
            mgr.cur = MagicMock()
            mgr.conn = MagicMock()
            return mgr

    # ========================================================================
    # Duplicate Detection
    # ========================================================================

    def test_prevent_duplicate_entry_alert(self, alert_manager):
        """Should prevent duplicate entry alerts within dedup window."""
        alert1 = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        alert2 = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        # Both should have same dedup key
        assert alert_manager.get_dedup_key(alert1) == alert_manager.get_dedup_key(alert2)

        # First should send, second should be suppressed
        sent1 = alert_manager.should_send_alert(alert1)
        sent2 = alert_manager.should_send_alert(alert2)

        assert sent1 is True
        assert sent2 is False

    def test_different_quantities_not_duplicate(self, alert_manager):
        """Should NOT deduplicate alerts with different quantities."""
        alert1 = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        alert2 = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=50,  # Different
            entry_price=150.00,
            stop_price=147.00
        )

        # Should have different dedup keys
        assert alert_manager.get_dedup_key(alert1) != alert_manager.get_dedup_key(alert2)

    def test_dedup_window_expires(self, alert_manager):
        """Should allow duplicate after dedup window expires."""
        alert = alert_manager.create_entry_alert(
            symbol='AAPL',
            quantity=100,
            entry_price=150.00,
            stop_price=147.00
        )

        # First alert should send
        assert alert_manager.should_send_alert(alert) is True

        # Duplicate within window should be suppressed
        assert alert_manager.should_send_alert(alert) is False

        # Simulate window expiry
        alert_manager.dedup_timestamps[alert_manager.get_dedup_key(alert)] = \
            datetime.now() - timedelta(minutes=31)

        # After expiry, should send again
        assert alert_manager.should_send_alert(alert) is True


class TestAlertFiltering:
    """Test alert filtering and suppression."""

    @pytest.fixture
    def alert_manager(self):
        """Create alert manager for testing."""
        with patch('algo.algo_alerts.psycopg2.connect'):
            mgr = AlertManager(
                db_host=os.environ.get('DB_HOST', 'localhost'),
                db_name='stocks',
                user='stocks',
                password=os.environ.get('DB_PASSWORD', 'test'),
                production_mode=False
            )
            mgr.cur = MagicMock()
            mgr.conn = MagicMock()
            return mgr

    # ========================================================================
    # Alert Filtering
    # ========================================================================

    def test_suppress_debug_alerts_in_production(self, alert_manager):
        """Should suppress debug-level alerts in production."""
        alert_manager.production_mode = True

        debug_alert = Alert(
            symbol='AAPL',
            event_type='DEBUG',
            severity=AlertLevel.INFO,
            message='Debug info'
        )

        # Should be filtered
        assert alert_manager.should_send_alert(debug_alert) is False

    def test_allow_all_in_dev_mode(self, alert_manager):
        """Should allow all alerts in dev mode."""
        alert_manager.production_mode = False

        debug_alert = Alert(
            symbol='AAPL',
            event_type='DEBUG',
            severity=AlertLevel.INFO,
            message='Debug info'
        )

        # Should be allowed
        assert alert_manager.should_send_alert(debug_alert) is True

    def test_always_send_critical(self, alert_manager):
        """Should always send CRITICAL alerts regardless of mode."""
        alert_manager.production_mode = True

        crit_alert = Alert(
            symbol='AAPL',
            event_type='HALTED',
            severity=AlertLevel.CRITICAL,
            message='Critical error'
        )

        # Should always send critical
        assert alert_manager.should_send_alert(crit_alert) is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
