#!/usr/bin/env python3
"""Pytest configuration - mock database connections at the high level."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "algo_trading"
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "test_password"
os.environ["ALPACA_API_KEY"] = "PK_TEST"
os.environ["ALPACA_SECRET_KEY"] = "sk_test"
os.environ["AWS_REGION"] = "us-east-1"


def _create_mock_cursor():
    """Create a mock cursor with proper algo_config data."""
    cursor = MagicMock()

    # Create realistic algo_config data (key, value, dtype tuples)
    # All values must pass validation - use safe defaults matching VALIDATION_SCHEMA ranges
    mock_config_rows = [
        ("max_positions", "15", "int"),  # 15 max concurrent positions
        ("max_position_size_pct", "6.3", "float"),  # 6.3% per position
        ("max_total_invested_pct", "85", "float"),  # 85% total invested
        ("halt_drawdown_pct", "-20", "float"),  # NEGATIVE: -20% halt threshold (range -100 to -5)
        ("max_daily_loss_pct", "2", "float"),  # 2% daily loss cap (range 0.1-50)
        ("vix_max_threshold", "35", "float"),  # VIX max 35 (range 20-100)
        ("vix_caution_threshold", "25", "float"),  # VIX caution 25 (range 20-100)
        ("min_completeness_score", "70", "int"),  # 70% completeness (range 1-100)
        ("min_stock_price", "5", "float"),  # $5 min price (range 0.1-1000)
    ]

    def mock_fetchall():
        """Return mock config data on SELECT from algo_config."""
        return mock_config_rows

    def mock_fetchone():
        """Return single row for specific queries."""
        return ("max_positions", "50", "int")

    cursor.fetchall.side_effect = mock_fetchall
    cursor.fetchone.side_effect = mock_fetchone
    cursor.fetchmany.return_value = []
    cursor.description = None
    cursor.rowcount = len(mock_config_rows)
    return cursor


def _create_mock_connection():
    """Create a mock connection."""
    conn = MagicMock()
    conn.cursor.return_value = _create_mock_cursor()
    conn.commit.return_value = None
    conn.rollback.return_value = None
    conn.close.return_value = None
    conn.closed = False
    return conn


def pytest_configure(config):
    """Mock database connections and AWS."""
    # Mock psycopg2.pool.SimpleConnectionPool to return mock connections
    import psycopg2.pool

    class MockConnectionPool:
        """Mock pool that returns mock connections."""

        def getconn(self):
            return _create_mock_connection()

        def putconn(self, conn, close=False):
            pass

        def closeall(self):
            pass

    # Keep original class but override __init__ to return our mock pool
    original_pool = psycopg2.pool.SimpleConnectionPool

    def mock_pool_init(self, *args, **kwargs):
        # Don't call original - just become our mock pool
        self._mock_pool = MockConnectionPool()

    original_pool.__init__ = mock_pool_init
    original_pool.getconn = lambda self: self._mock_pool.getconn()
    original_pool.putconn = lambda self, conn, close=False: self._mock_pool.putconn(conn, close)
    original_pool.closeall = lambda self: self._mock_pool.closeall()

    # Also mock get_db_connection as fallback
    patch("utils.db.connection.get_db_connection", return_value=_create_mock_connection()).start()

    # Mock credential manager functions
    def mock_db_creds():
        return {
            "host": "localhost",
            "port": 5432,
            "user": "postgres",
            "password": "test_password",
            "database": "algo_trading",
            "username": "postgres",
            "dbname": "algo_trading",
        }

    def mock_alpaca_creds():
        return {
            "api_key": "PK_TEST",
            "secret_key": "sk_test",
        }

    def mock_alpaca_url():
        return "https://paper-api.alpaca.markets"

    import config.credential_manager as cm

    cm.get_db_credentials = mock_db_creds
    cm.get_alpaca_credentials = mock_alpaca_creds
    cm.get_alpaca_base_url = mock_alpaca_url

    # Mock boto3
    import boto3

    original_client = boto3.client

    def mock_client(service_name, **kwargs):
        if service_name == "secretsmanager":
            mock_sm = MagicMock()
            mock_sm.get_secret_value.return_value = {
                "SecretString": '{"host":"localhost","port":5432,"user":"postgres","password":"test_password","database":"algo_trading"}'
            }
            return mock_sm
        return original_client(service_name, **kwargs)

    boto3.client = mock_client


def pytest_collection_modifyitems(items: list) -> None:
    """Auto-apply pytest marks based on directory so `make test-unit/edge/integration` work.

    Files under tests/unit/       → @pytest.mark.unit
    Files under tests/edge_cases/ → @pytest.mark.edge
    Files under tests/integration/→ @pytest.mark.integration
    Top-level tests/test_*.py     → @pytest.mark.unit (default tier)
    """
    for item in items:
        path = str(item.fspath)
        if "/unit/" in path or "\\unit\\" in path:
            item.add_marker(pytest.mark.unit)
        elif "/edge_cases/" in path or "\\edge_cases\\" in path:
            item.add_marker(pytest.mark.edge)
        elif "/integration/" in path or "\\integration\\" in path:
            item.add_marker(pytest.mark.integration)
        else:
            # Top-level tests/ files — treat as unit tests
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def mock_db():
    """Mock database context."""
    with patch("utils.db.DatabaseContext") as m:
        yield m
