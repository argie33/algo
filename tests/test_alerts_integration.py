#!/usr/bin/env python3
"""
Integration test for alert system (email + webhook).

Run locally to test alerts:
  export ALERT_EMAIL_TO="your-email@gmail.com"
  export ALERT_SMTP_HOST="smtp.gmail.com"
  export ALERT_SMTP_PORT="587"
  export ALERT_SMTP_USER="your-email@gmail.com"
  export ALERT_SMTP_PASSWORD="your-app-password"
  export ALERT_SMTP_FROM="your-email@gmail.com"
  python3 -m pytest tests/test_alerts_integration.py -v -s

Or test with webhook:
  export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  python3 -m pytest tests/test_alerts_integration.py -v -s
"""

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from algo.algo_alerts import AlertManager


class TestAlertManager:
    """Test AlertManager email and webhook functionality."""

    def test_alert_manager_initialization(self):
        """Test that AlertManager initializes without errors."""
        with mock.patch.dict(os.environ, {}, clear=False):
            am = AlertManager()
            assert am is not None

    def test_alert_manager_email_configured(self):
        """Test that email alerts are configured."""
        env_vars = {
            'ALERT_EMAIL_TO': 'test@example.com',
            'ALERT_SMTP_HOST': 'smtp.gmail.com',
            'ALERT_SMTP_USER': 'test@gmail.com',
            'ALERT_SMTP_PASSWORD': 'test-password',
            'ALERT_SMTP_FROM': 'alerts@example.com',
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            am = AlertManager()
            assert am.email_to == ['test@example.com']
            assert am.smtp_host == 'smtp.gmail.com'
            assert am.smtp_user == 'test@gmail.com'
            assert am.smtp_password == 'test-password'
            assert am.email_from == 'alerts@example.com'

    def test_alert_manager_webhook_configured(self):
        """Test that webhook is configured when set."""
        webhook_url = 'https://hooks.slack.com/services/T00/B00/XXXX'

        with mock.patch.dict(os.environ, {'ALERT_WEBHOOK_URL': webhook_url}, clear=False):
            am = AlertManager()
            assert am.webhook_url == webhook_url

    def test_send_patrol_alert_email(self):
        """Test sending patrol alert via email."""
        env_vars = {
            'ALERT_EMAIL_TO': 'test@example.com',
            'ALERT_SMTP_HOST': 'smtp.gmail.com',
            'ALERT_SMTP_USER': 'test@gmail.com',
            'ALERT_SMTP_PASSWORD': 'test-password',
            'ALERT_SMTP_FROM': 'alerts@example.com',
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            with mock.patch('smtplib.SMTP') as mock_smtp:
                mock_server = mock.MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                am = AlertManager()
                am.send_patrol_alert(
                    'PATROL-TEST-123',
                    {'critical': 1, 'error': 2, 'warn': 3, 'info': 10},
                    [
                        {
                            'check': 'staleness',
                            'severity': 'critical',
                            'target': 'price_daily',
                            'message': 'Data stale: 9d > 7d threshold'
                        }
                    ]
                )

                # Verify SMTP was called
                assert mock_server.starttls.called
                assert mock_server.login.called
                assert mock_server.send_message.called

    def test_send_position_alert_email(self):
        """Test sending position alert via email."""
        env_vars = {
            'ALERT_EMAIL_TO': 'test@example.com',
            'ALERT_SMTP_HOST': 'smtp.gmail.com',
            'ALERT_SMTP_USER': 'test@gmail.com',
            'ALERT_SMTP_PASSWORD': 'test-password',
            'ALERT_SMTP_FROM': 'alerts@example.com',
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            with mock.patch('smtplib.SMTP') as mock_smtp:
                mock_server = mock.MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                am = AlertManager()
                am.send_position_alert(
                    'AAPL',
                    'STUCK_ORDER',
                    'Order has been pending for 5 minutes',
                    {'order_id': '12345', 'qty': 100}
                )

                # Verify SMTP was called
                assert mock_server.send_message.called

    def test_send_loader_alert_email(self):
        """Test sending loader alert via email."""
        env_vars = {
            'ALERT_EMAIL_TO': 'test@example.com',
            'ALERT_SMTP_HOST': 'smtp.gmail.com',
            'ALERT_SMTP_USER': 'test@gmail.com',
            'ALERT_SMTP_PASSWORD': 'test-password',
            'ALERT_SMTP_FROM': 'alerts@example.com',
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            with mock.patch('smtplib.SMTP') as mock_smtp:
                mock_server = mock.MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                am = AlertManager()
                findings = [
                    ('CRITICAL', 'staleness', 'price_daily is 10 days old (threshold 7d)'),
                    ('ERROR', 'row_count', 'stock_scores has 0 rows'),
                ]
                am.send_loader_alert(findings)

                # Verify SMTP was called
                assert mock_server.send_message.called

    def test_send_webhook_alert(self):
        """Test sending alert via webhook."""
        webhook_url = 'https://hooks.slack.com/services/T00/B00/XXXX'
        env_vars = {'ALERT_WEBHOOK_URL': webhook_url}

        with mock.patch.dict(os.environ, env_vars, clear=True):
            with mock.patch('requests.post') as mock_requests:
                mock_requests.return_value.status_code = 200

                am = AlertManager()
                am.send_patrol_alert(
                    'PATROL-TEST-123',
                    {'critical': 1, 'error': 0, 'warn': 0, 'info': 0},
                    [
                        {
                            'check': 'test',
                            'severity': 'critical',
                            'target': 'test_table',
                            'message': 'Test critical issue'
                        }
                    ]
                )

                # Verify webhook was called
                assert mock_requests.called

    def test_critical_alert_email(self):
        """Test sending generic critical alert."""
        env_vars = {
            'ALERT_EMAIL_TO': 'test@example.com',
            'ALERT_SMTP_HOST': 'smtp.gmail.com',
            'ALERT_SMTP_USER': 'test@gmail.com',
            'ALERT_SMTP_PASSWORD': 'test-password',
            'ALERT_SMTP_FROM': 'alerts@example.com',
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            with mock.patch('smtplib.SMTP') as mock_smtp:
                mock_server = mock.MagicMock()
                mock_smtp.return_value.__enter__.return_value = mock_server

                am = AlertManager()
                am.critical('Test critical alert message')

                # Verify SMTP was called
                assert mock_server.send_message.called


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
