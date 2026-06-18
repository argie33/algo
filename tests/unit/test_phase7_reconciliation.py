import inspect
from unittest.mock import Mock, patch

import pytest

from algo.infrastructure.reconciliation import DailyReconciliation


class TestDailyReconciliationDatabaseContext:
    """Test that DailyReconciliation properly uses DatabaseContext."""

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    def test_compute_closed_trade_metrics_accepts_cursor(self, mock_get_cred):
        """Test compute_closed_trade_metrics accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }
        recon = DailyReconciliation({})

        mock_cur = Mock()
        mock_cur.fetchall.return_value = []

        # Should not raise TypeError about missing cursor parameter
        result = recon.compute_closed_trade_metrics(mock_cur)
        assert "updated" in result
        assert "reason" in result

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    def test_compute_analytics_metrics_accepts_cursor(self, mock_get_cred):
        """Test compute_analytics_metrics accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }
        recon = DailyReconciliation({})

        mock_cur = Mock()
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = None

        # Should not raise TypeError about missing cursor parameter
        result = recon.compute_analytics_metrics(mock_cur)
        assert "ic" in result
        assert "expectancy" in result

    @patch("algo.infrastructure.reconciliation.get_credential_manager")
    def test_sync_alpaca_positions_accepts_cursor(self, mock_get_cred):
        """Test sync_alpaca_positions accepts and uses cursor parameter."""
        mock_get_cred.return_value.get_alpaca_credentials.return_value = {
            "key": "",
            "secret": "",
        }
        recon = DailyReconciliation({})
        recon.trading_client = None  # No Alpaca client

        mock_cur = Mock()

        # Should not raise TypeError about missing cursor parameter
        result = recon.sync_alpaca_positions(mock_cur)
        assert "imported" in result
        assert "orphaned" in result


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
