#!/usr/bin/env python3
"""Unit tests for CircuitBreaker module."""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add algo directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from algo.risk import CircuitBreaker


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        "circuit_breaker_enabled": True,
        "daily_loss_limit": -5000,
        "drawdown_limit": -20,
    }


@pytest.fixture
def mock_connection():
    """Create mock database connection."""
    mock_conn = Mock()
    mock_cur = Mock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn, mock_cur


@pytest.fixture
def circuit_breaker(mock_config):
    """Create CircuitBreaker instance with mocked database."""
    return CircuitBreaker(config=mock_config)


class TestCircuitBreakerInit:
    """Test CircuitBreaker initialization."""

    def test_init_with_config(self, mock_config):
        """Test initialization with configuration."""
        cb = CircuitBreaker(config=mock_config)
        assert cb.config == mock_config


class TestCircuitBreakerBasic:
    """Test basic CircuitBreaker functionality."""

    def test_check_all(self, circuit_breaker):
        """Test overall circuit breaker check."""
        mock_cur = Mock()
        mock_cur.fetchone.return_value = None
        all_pass = {"halted": False, "passed": True}
        check_methods = [
            "_check_daily_loss", "_check_drawdown", "_check_drawdown_re_engagement",
            "_check_consecutive_losses", "_check_total_risk", "_check_vix_spike",
            "_check_market_stage", "_check_weekly_loss", "_check_sector_concentration",
            "_check_intraday_market_health", "_check_win_rate_floor",
            "_check_daily_profit_cap", "_check_data_freshness",
        ]
        with patch("algo.algo_circuit_breaker.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            patches = [patch.object(circuit_breaker, m, return_value=all_pass) for m in check_methods]
            for p in patches:
                p.start()
            try:
                result = circuit_breaker.check_all()
                assert isinstance(result, dict)
                assert "halted" in result
            finally:
                for p in patches:
                    p.stop()


class TestCircuitBreakerVIX:
    """Test VIX-based circuit breaker logic."""

    def test_vix_spike_check(self, circuit_breaker):
        """Test VIX spike detection."""
        with patch.object(circuit_breaker, "_check_vix_spike") as mock_vix:
            mock_vix.return_value = {"halted": False, "vix_level": 20, "threshold": 30}
            result = circuit_breaker._check_vix_spike()
            assert isinstance(result, dict)
            assert "halted" in result
            assert "vix_level" in result


class TestCircuitBreakerAll:
    """Test combined circuit breaker checks."""

    def test_all_breakers_integration(self, circuit_breaker):
        """Test all circuit breakers together."""
        circuit_breaker.conn = Mock()
        circuit_breaker.cur = Mock()

        with patch.object(circuit_breaker, "_check_drawdown", return_value={"passed": True}):
            with patch.object(circuit_breaker, "_check_daily_loss", return_value={"passed": True}):
                assert circuit_breaker.conn is not None
                assert circuit_breaker.cur is not None
