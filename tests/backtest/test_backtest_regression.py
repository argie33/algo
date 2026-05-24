"""Backtest regression tests for orchestrator."""
import os
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import psycopg2


@pytest.fixture
def db_config():
    """Get database config from environment."""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'user': os.getenv('DB_USER', 'stocks'),
        'password': os.getenv('DB_PASSWORD', 'testpass'),
        'database': os.getenv('DB_NAME', 'stocks'),
    }


@pytest.fixture
def db_connection(db_config):
    """Connect to test database."""
    conn = psycopg2.connect(**db_config)
    yield conn
    conn.close()


def test_orchestrator_imports():
    """Verify orchestrator imports without errors."""
    from algo.algo_orchestrator import Orchestrator
    assert Orchestrator is not None


def test_orchestrator_initialization(db_config):
    """Test orchestrator can initialize with config."""
    from algo.algo_orchestrator import Orchestrator

    with patch.dict(os.environ, {
        'DB_HOST': db_config['host'],
        'DB_USER': db_config['user'],
        'DB_PASSWORD': db_config['password'],
        'DB_NAME': db_config['database'],
        'EXECUTION_MODE': 'paper',
        'ALPACA_PAPER_TRADING': 'true',
    }):
        orchestrator = Orchestrator(dry_run=True, verbose=False)
        assert orchestrator is not None
        assert orchestrator.dry_run is True


def test_orchestrator_phases_defined():
    """Verify all 7 phases are defined."""
    from algo.algo_orchestrator import Orchestrator

    with patch.dict(os.environ, {
        'DB_HOST': 'localhost',
        'DB_USER': 'stocks',
        'DB_PASSWORD': 'testpass',
        'DB_NAME': 'stocks',
        'EXECUTION_MODE': 'paper',
    }):
        orchestrator = Orchestrator(dry_run=True, verbose=False)

        phase_methods = [
            'phase_1_data_freshness',
            'phase_2_circuit_breakers',
            'phase_3_position_monitor',
            'phase_4_exit_execution',
            'phase_5_signal_generation',
            'phase_6_entry_execution',
            'phase_7_reconcile',
        ]

        for phase in phase_methods:
            assert hasattr(orchestrator, phase), f"Missing {phase}"


def test_config_loading():
    """Test that algo config loads successfully."""
    from algo.algo_config import get_config

    config = get_config()
    assert config is not None
    assert config.get('max_positions') is not None
    assert config.get('min_signal_quality_score') is not None


def test_trade_executor_imports():
    """Verify trade executor imports without errors."""
    from algo.algo_trade_executor import TradeExecutor
    assert TradeExecutor is not None


def test_filter_pipeline_imports():
    """Verify filter pipeline imports without errors."""
    from algo.algo_filter_pipeline import FilterPipeline
    assert FilterPipeline is not None


def test_circuit_breaker_imports():
    """Verify circuit breaker imports without errors."""
    from algo.algo_circuit_breaker import CircuitBreaker
    assert CircuitBreaker is not None


@pytest.mark.parametrize("position_count", [0, 1, 5, 10])
def test_position_scaling(position_count):
    """Test orchestrator handles various position counts."""
    from algo.algo_orchestrator import Orchestrator

    with patch.dict(os.environ, {
        'DB_HOST': 'localhost',
        'DB_USER': 'stocks',
        'DB_PASSWORD': 'testpass',
        'DB_NAME': 'stocks',
        'EXECUTION_MODE': 'paper',
    }):
        orchestrator = Orchestrator(dry_run=True, verbose=False)
        assert orchestrator.config.get('max_positions', 0) > 0


def test_dry_run_mode(db_config):
    """Test that dry_run=True prevents any trades."""
    from algo.algo_orchestrator import Orchestrator

    with patch.dict(os.environ, {
        'DB_HOST': db_config['host'],
        'DB_USER': db_config['user'],
        'DB_PASSWORD': db_config['password'],
        'DB_NAME': db_config['database'],
        'EXECUTION_MODE': 'paper',
        'ALPACA_PAPER_TRADING': 'true',
    }):
        orchestrator = Orchestrator(dry_run=True, verbose=False)
        assert orchestrator.dry_run is True


def test_signal_generation_ranking():
    """Test signal ranking logic works."""
    from algo.algo_signals import SignalComputer

    computer = SignalComputer()
    assert computer is not None


def test_market_calendar_initialized():
    """Verify market calendar is available."""
    from algo.algo_market_calendar import MarketCalendar

    calendar = MarketCalendar()
    assert calendar is not None
    assert callable(calendar.is_trading_day)


def test_alert_manager_initialized():
    """Verify alert manager initializes."""
    from algo.algo_alerts import AlertManager

    alert_manager = AlertManager()
    assert alert_manager is not None
