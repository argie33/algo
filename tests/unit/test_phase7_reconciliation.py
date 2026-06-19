import inspect
from unittest.mock import Mock, patch

import pytest

from algo.infrastructure.reconciliation import DailyReconciliation


class TestDailyReconciliationDatabaseContext:
    """Test that DailyReconciliation properly uses DatabaseContext."""

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.get_alpaca_base_url")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_compute_closed_trade_metrics_accepts_cursor(self, mock_notify, mock_base_url, mock_get_cred):
        """Test compute_closed_trade_metrics accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "test_key_123",
            "secret": "test_secret_456",
        }
        mock_base_url.return_value = "https://api.test.alpaca.markets"
        recon = DailyReconciliation({})

        mock_cur = Mock()
        mock_cur.fetchall.return_value = []

        # Should not raise TypeError about missing cursor parameter
        result = recon.compute_closed_trade_metrics(mock_cur)
        assert "updated" in result
        assert "reason" in result

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.get_alpaca_base_url")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_compute_analytics_metrics_accepts_cursor(self, mock_notify, mock_base_url, mock_get_cred):
        """Test compute_analytics_metrics accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "test_key_123",
            "secret": "test_secret_456",
        }
        mock_base_url.return_value = "https://api.test.alpaca.markets"
        recon = DailyReconciliation({})

        mock_cur = Mock()
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = None

        # Should not raise TypeError about missing cursor parameter
        result = recon.compute_analytics_metrics(mock_cur)
        assert "ic" in result
        assert "expectancy" in result

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.get_alpaca_base_url")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_sync_alpaca_positions_accepts_cursor(self, mock_notify, mock_base_url, mock_get_cred):
        """Test sync_alpaca_positions accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "test_key_123",
            "secret": "test_secret_456",
        }
        mock_base_url.return_value = "https://api.test.alpaca.markets"
        recon = DailyReconciliation({})
        recon.trading_client = None  # No Alpaca client

        mock_cur = Mock()

        # Should not raise TypeError about missing cursor parameter
        result = recon.sync_alpaca_positions(mock_cur)
        assert "imported" in result
        assert "orphaned" in result


class TestAlpacaCredentialValidation:
    """Test that credential initialization fails explicitly when credentials are missing."""

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_init_fails_on_missing_api_key(self, mock_notify, mock_get_cred):
        """Test DailyReconciliation fails explicitly when API key is missing."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": None,
            "secret": "test_secret_456",
        }

        with pytest.raises(ValueError) as exc_info:
            DailyReconciliation({})

        assert "API key missing" in str(exc_info.value)
        mock_notify.assert_called_once()
        notify_call = mock_notify.call_args
        assert notify_call[0][0] == "critical"

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_init_fails_on_missing_api_secret(self, mock_notify, mock_get_cred):
        """Test DailyReconciliation fails explicitly when API secret is missing."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "test_key_123",
            "secret": None,
        }

        with pytest.raises(ValueError) as exc_info:
            DailyReconciliation({})

        assert "API secret missing" in str(exc_info.value)
        mock_notify.assert_called_once()

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.get_alpaca_base_url")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_init_fails_on_missing_base_url(self, mock_notify, mock_base_url, mock_get_cred):
        """Test DailyReconciliation fails explicitly when base URL is missing."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "test_key_123",
            "secret": "test_secret_456",
        }
        mock_base_url.return_value = None

        with pytest.raises(ValueError) as exc_info:
            DailyReconciliation({})

        assert "base URL" in str(exc_info.value)
        mock_notify.assert_called_once()

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    @patch("algo.infrastructure.reconciliation.notify")
    def test_init_fails_on_credential_fetch_exception(self, mock_notify, mock_get_cred):
        """Test DailyReconciliation fails explicitly on credential fetch exception."""
        mock_get_cred.return_value.get_alpaca_credentials.side_effect = Exception("credential fetch failed")

        with pytest.raises(ValueError) as exc_info:
            DailyReconciliation({})

        assert "credential initialization failed" in str(exc_info.value)
        mock_notify.assert_called_once()


class TestPhase7MethodSignatures:
    """Test that Phase 7 methods have correct signatures."""

    def test_compute_closed_trade_metrics_signature(self):
        """Verify compute_closed_trade_metrics has cur parameter."""
        import inspect

        sig = inspect.signature(DailyReconciliation.compute_closed_trade_metrics)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "cur" in params

    def test_compute_analytics_metrics_signature(self):
        """Verify compute_analytics_metrics has cur parameter."""
        import inspect

        sig = inspect.signature(DailyReconciliation.compute_analytics_metrics)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "cur" in params

    def test_sync_alpaca_positions_signature(self):
        """Verify sync_alpaca_positions has cur parameter."""
        sig = inspect.signature(DailyReconciliation.sync_alpaca_positions)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "cur" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
