"""
Pytest configuration and shared fixtures for algo trading system tests.

Provides:
- Database fixtures (in-memory SQLite or test PostgreSQL)
- Alpaca API mocks
- Config fixtures with sensible test defaults
- Portfolio state fixtures
"""

import os
import pytest
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

# Load test env vars
env_file = Path(__file__).parent.parent / '.env.test'
if env_file.exists():
    load_dotenv(env_file)

# Test database config — use test-specific DB if available
TEST_DB_HOST = os.getenv('TEST_DB_HOST', 'localhost')
TEST_DB_PORT = int(os.getenv('TEST_DB_PORT', 5432))
TEST_DB_NAME = os.getenv('TEST_DB_NAME', 'stocks_test')
TEST_DB_USER = os.getenv('TEST_DB_USER', 'stocks')
TEST_DB_PASSWORD = os.getenv('TEST_DB_PASSWORD', '')


@pytest.fixture
def test_db():
    """Connect to test database and clean up after test.

    Yields a psycopg2 connection to the test database.
    Caller responsible for committing/rolling back.
    """
    conn = psycopg2.connect(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        database=TEST_DB_NAME,
        user=TEST_DB_USER,
        password=TEST_DB_PASSWORD,
    )
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def seeded_test_db(request):
    """Set up stocks_test database with schema and seed data.

    This fixture runs once per session and sets up the complete test environment:
    - Creates stocks_test database if it doesn't exist
    - Initializes the schema
    - Seeds minimal realistic test data (prices, signals, positions, trades)

    Use this fixture in integration tests that need a real database with data.
    Tests connect to the database directly; this fixture ensures it's set up.

    If the database is not available (e.g., postgres not running in CI), skip the test.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from setup_test_db import setup_test_db
    try:
        setup_test_db()
        print("\n✓ Test database setup complete")
    except Exception as e:
        print(f"\n✗ Test database setup failed: {e}")
        # Skip the test instead of failing if the database is not available
        pytest.skip(f"Test database not available: {e}", allow_module_level=False)

    yield  # Tests run here


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration with institutional defaults."""
    from algo_config import AlgoConfig

    config = AlgoConfig()
    # Override with test-safe defaults
    config._config.update({
        'execution_mode': 'paper',  # Never live in tests
        'enable_algo': True,
        'base_risk_pct': 0.75,
        'max_positions': 12,
        'max_position_size_pct': 8.0,
        'max_concentration_pct': 50.0,
        'vix_max_threshold': 35.0,
        'vix_caution_threshold': 25.0,
        'vix_caution_risk_reduction': 0.75,
        'risk_reduction_at_minus_5': 0.75,
        'risk_reduction_at_minus_10': 0.5,
        'risk_reduction_at_minus_15': 0.25,
        'risk_reduction_at_minus_20': 0.0,
        't1_target_r_multiple': 1.5,
        't2_target_r_multiple': 3.0,
        't3_target_r_multiple': 4.0,
        'max_hold_days': 20,
    })
    return config


@pytest.fixture
def alpaca_mock():
    """Mock Alpaca API responses with proper object attributes.

    Returns objects that match the real Alpaca SDK interface:
    - account.portfolio_value (string attribute)
    - order.id, order.status, order.filled_qty, order.filled_avg_price (attributes)
    """
    class MockAccount:
        def __init__(self):
            self.portfolio_value = '100000.00'
            self.equity = '100000.00'
            self.cash = '50000.00'

    class MockAsset:
        def __init__(self):
            self.symbol = 'AAPL'
            self.tradable = True
            self.status = 'active'

    class MockOrder:
        def __init__(self, status='filled', filled_qty=None, filled_price=None):
            self.id = 'test-order-' + str(datetime.now().timestamp())
            self.symbol = 'AAPL'
            self.qty = 100
            self.side = 'buy'
            self.type = 'limit'
            self.status = status
            self.filled_qty = filled_qty or 100
            self.filled_avg_price = filled_price or '150.25'
            self.order_class = 'bracket'
            self.legs = [
                MagicMock(id='leg-1', status=status),
                MagicMock(id='leg-2', status='pending'),
                MagicMock(id='leg-3', status='pending'),
            ] if status == 'filled' else []

    mock = MagicMock()
    mock.get_account = MagicMock(return_value=MockAccount())
    mock.get_asset = MagicMock(return_value=MockAsset())
    mock.MockOrder = MockOrder
    return mock


@pytest.fixture
def portfolio_snapshot():
    """Create a baseline portfolio snapshot for testing."""
    return {
        'snapshot_date': date.today(),
        'total_portfolio_value': Decimal('100000.00'),
        'cash': Decimal('50000.00'),
        'positions_value': Decimal('50000.00'),
        'daily_return_pct': Decimal('0.50'),
        'cumulative_return_pct': Decimal('5.25'),
        'sharpe_ratio': Decimal('1.45'),
    }


@pytest.fixture
def sample_trade():
    """Create a sample trade record for testing."""
    return {
        'trade_id': 'TRD-TEST001',
        'symbol': 'AAPL',
        'signal_date': date.today() - timedelta(days=5),
        'entry_price': 150.00,
        'entry_quantity': 100,
        'stop_loss_price': 142.50,
        'target_1_price': 157.50,
        'target_2_price': 165.00,
        'target_3_price': 172.50,
        'status': 'open',
        'execution_mode': 'paper',
        'swing_score': 75.0,
        'swing_grade': 'A',
        'base_type': 'tight_consolidation',
        'stage_phase': 'Early',
    }


@pytest.fixture
def sample_position(sample_trade):
    """Create a sample open position for testing."""
    return {
        'position_id': 'POS-TEST001',
        'symbol': sample_trade['symbol'],
        'quantity': sample_trade['entry_quantity'],
        'avg_entry_price': sample_trade['entry_price'],
        'current_price': 152.50,
        'position_value': 15250.00,
        'status': 'open',
        'trade_ids_arr': [sample_trade['trade_id']],
        'current_stop_price': sample_trade['stop_loss_price'],
        'target_levels_hit': '[]',
    }


@pytest.fixture
def circuit_breaker_status():
    """Default circuit breaker status (all clear)."""
    return {
        'halted': False,
        'halt_reasons': [],
        'checks': {
            'drawdown': {'halted': False, 'value': 5.0, 'threshold': 20.0},
            'daily_loss': {'halted': False, 'value': 0.25, 'threshold': 2.0},
            'consecutive_losses': {'halted': False, 'value': 1, 'threshold': 3},
            'total_risk': {'halted': False, 'value': 1.5, 'threshold': 4.0},
            'vix_spike': {'halted': False, 'value': 18.5, 'threshold': 35.0},
            'market_stage': {'halted': False, 'value': 1, 'threshold': 4},
            'weekly_loss': {'halted': False, 'value': 1.2, 'threshold': 5.0},
            'data_freshness': {'halted': False, 'value': 'current'},
        }
    }


@pytest.fixture(autouse=True)
def reset_imports():
    """Reset module imports between tests to avoid state pollution."""
    yield
    # Clean up module-level state if needed
    import sys
    # Don't remove actual modules, just reset any singletons
    if 'algo_config' in sys.modules:
        # Reset global config instance
        import algo_config
        algo_config._instance = None


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        'markers', 'unit: unit tests (fast, no external deps)'
    )
    config.addinivalue_line(
        'markers', 'edge_case: edge case tests (position size limits, partial fills, etc)'
    )
    config.addinivalue_line(
        'markers', 'integration: integration tests (full orchestrator flow)'
    )
    config.addinivalue_line(
        'markers', 'slow: slow tests (backtests, large datasets)'
    )
    config.addinivalue_line(
        'markers', 'db: tests requiring database connection'
    )


# Minimal pytest.ini-equivalent options
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        '--run-slow', action='store_true', default=False,
        help='run slow tests'
    )
    parser.addoption(
        '--run-db', action='store_true', default=False,
        help='run tests requiring database'
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers."""
    if not config.getoption('--run-slow'):
        skip_slow = pytest.mark.skip(reason='need --run-slow option to run')
        for item in items:
            if 'slow' in item.keywords:
                item.add_marker(skip_slow)

    if not config.getoption('--run-db'):
        skip_db = pytest.mark.skip(reason='need --run-db option to run')
        for item in items:
            if 'db' in item.keywords:
                item.add_marker(skip_db)
