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
os.environ["ORCHESTRATOR_EXECUTION_MODE"] = "paper"
os.environ["ORCHESTRATOR_DRY_RUN"] = "true"


def _create_mock_cursor():
    from datetime import date
    from collections import namedtuple

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

    # Track the last query to return appropriate mock data
    last_query = [None]

    def mock_execute(query, params=None):
        last_query[0] = query if isinstance(query, str) else str(query)

    def mock_fetchall():
        query = last_query[0] or ""

        # Data patrol alignment checks
        if "sqs_count" in query and "buy_sell_count" in query:
            # Two columns: sqs_count, buy_sell_count
            return [(150, 140)]
        if "COUNT(DISTINCT symbol) FROM signal_quality_scores" in query:
            return [(date(2026, 7, 18),)]
        if "COUNT(DISTINCT symbol) FROM buy_sell_daily" in query:
            return [(date(2026, 7, 18),)]

        # Fundamental data checks (union query returns tbl_name, latest, total, unique_syms)
        if "UNION ALL" in query and "quarterly_income_statement" in query:
            Row = namedtuple("Row", ["tbl_name", "latest", "total", "unique_syms"])
            return [
                Row("quarterly_income_statement", date(2026, 7, 10), 1500, 480),
                Row("quarterly_balance_sheet", date(2026, 7, 10), 1500, 480),
                Row("quarterly_cash_flow", date(2026, 7, 10), 1500, 480),
                Row("annual_income_statement", date(2026, 7, 10), 480, 480),
                Row("annual_balance_sheet", date(2026, 7, 10), 480, 480),
                Row("annual_cash_flow", date(2026, 7, 10), 480, 480),
                Row("key_metrics", date(2026, 7, 18), 1500, 480),
            ]

        # Trade alignment check
        if "algo_trades" in query and "price_daily" in query:
            return []  # No orphaned trades

        # Sentiment aggregate columns check
        if "information_schema.columns" in query and "sentiment_aggregate" in query:
            return [("date",), ("aggregate_sentiment",), ("aaii_bullish",), ("naaim_bullish",), ("updated_at",)]

        # Default: config data
        return list(mock_config_rows)

    def mock_fetchone():
        from datetime import datetime, timezone

        query = last_query[0] or ""

        # Return 2-element tuples for alignment checks
        if "sqs_count" in query and "buy_sell_count" in query:
            return (150, 140)

        # Earnings table checks - COUNT(*), MAX(col::date)
        if "earnings_estimates" in query or "earnings_estimate_revisions" in query or "earnings_history" in query:
            if "COUNT(*)" in query and "MAX(" in query:
                return (500, date(2026, 7, 10))  # count, latest_date
            # Coverage query
            if "price_daily" in query and "LEFT JOIN" in query:
                return (420, 480)  # est_syms, price_syms

        # Sentiment aggregate freshness
        if "MAX(date), MAX(updated_at)" in query and "sentiment_aggregate" in query:
            return (date(2026, 7, 18), datetime(2026, 7, 18, 15, 30, 0, tzinfo=timezone.utc))

        # Return single value or tuple for MAX date queries
        if "MAX(date)" in query or "MAX(created_at::date)" in query:
            if "signal_quality_scores" in query:
                return (date(2026, 7, 18),)
            elif "buy_sell_daily" in query:
                return (date(2026, 7, 18),)
            elif "price_daily" in query:
                return (date(2026, 7, 18),)
            else:
                return (date(2026, 7, 10),)

        # Technical data RSI/NaN checks
        if "FILTER (WHERE rsi" in query or "FILTER (WHERE atr" in query:
            return (0, 0, 500)  # bad_rsi, null_rsi, total

        # Cross-alignment baseline
        if "COUNT(DISTINCT symbol) FROM price_daily" in query:
            return (500,)

        # Trade table column check - COUNT(*), MAX(created_at)
        if "MAX(created_at)" in query and ("algo_trades" in query or "algo_positions" in query):
            if "algo_trades" in query:
                return (10, datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc))
            else:
                return (5, datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc))

        # Default: config
        return ("max_positions", "50", "int")

    cursor.execute.side_effect = mock_execute
    cursor.fetchall.side_effect = mock_fetchall
    cursor.fetchone.side_effect = mock_fetchone
    cursor.fetchmany.return_value = []
    cursor.description = None
    cursor.rowcount = len(mock_config_rows)
    cursor.connection = MagicMock()
    cursor.connection.rollback = MagicMock()
    return cursor


def _create_mock_connection():
    conn = MagicMock()
    conn.cursor.return_value = _create_mock_cursor()
    conn.commit.return_value = None
    conn.rollback.return_value = None
    conn.close.return_value = None
    conn.closed = False
    return conn


def pytest_configure(config):
    """Mock database connections and AWS."""
    # Only apply mocking during pytest runs in this process
    # This prevents affecting subprocess dev_server instances
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
    original_init = original_pool.__init__

    def mock_pool_init(self, *args, **kwargs):
        # Don't call original - just become our mock pool
        self._mock_pool = MockConnectionPool()

    # Store original for restoration if needed
    original_pool._pytest_original_init = original_init
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
            # Top-level tests/ files - treat as unit tests
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def mock_db():
    """Mock database context."""
    with patch("utils.db.DatabaseContext") as m:
        yield m


@pytest.fixture(autouse=True)
def reload_lambda_api_modules():
    """Auto-reload Lambda API modules before each test to prevent isolation issues.

    When tests import modules from lambda/api/shared_contracts, Python caches them.
    If one test modifies the cached module (e.g., modifying DASHBOARD_ENDPOINTS),
    subsequent tests see the modified version. This fixture ensures fresh imports.

    Strategy: Remove modules from sys.modules BEFORE test runs (not after), then
    reload them. This forces a complete reimport on the next import statement.

    Affects: ResponseValidator, dashboard_api_contract, and other lambda/api modules.
    """
    import importlib

    # Modules to reload before each test
    modules_to_clear = [
        "shared_contracts.response_validator",
        "shared_contracts.dashboard_api_contract",
        "shared_contracts.api_contracts",
        "routes.algo_handlers.dashboard",
        "routes.algo_handlers.market",
        "routes.utils",
        "routes.algo",
        "routes.health",
    ]

    # BEFORE test: Clear modules from cache to force reimport
    for module_name in modules_to_clear:
        if module_name in sys.modules:
            del sys.modules[module_name]

    yield

    # AFTER test: Clear again so next test gets fresh state
    for module_name in modules_to_clear:
        if module_name in sys.modules:
            del sys.modules[module_name]
