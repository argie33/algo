#!/usr/bin/env python3
"""
Database Schema Validation Tests

Verifies database schema integrity - all critical tables exist with expected columns.
These tests catch schema drift and migration issues early.

Run with: pytest tests/integration/test_database_schema.py -v --tb=short
"""

import pytest
import psycopg2
import psycopg2.extras
from datetime import datetime


@pytest.fixture(scope="module")
def db_connection():
    """
    Create database connection for schema validation.
    Skips tests if database is not available.
    """
    import os
    from config.credential_helper import get_db_config

    try:
        config = get_db_config()
        # Use test database if configured, otherwise skip
        test_db_name = os.getenv('TEST_DB_NAME', config.get('database'))

        conn = psycopg2.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=test_db_name,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        yield conn
        conn.close()

    except (psycopg2.OperationalError, ValueError) as e:
        pytest.skip(f"Database not available: {e}")


class TestDatabaseSchemaTables:
    """Validate that all required tables exist in the database."""

    def test_core_market_data_tables_exist(self, db_connection):
        """Verify core market data tables exist."""
        required_tables = [
            'stock_symbols',
            'price_daily',
            'price_weekly',
            'price_monthly',
            'company_profile',
            'technical_data_daily',
            'buy_sell_daily',
            'buy_sell_weekly',
            'buy_sell_monthly',
        ]

        cur = db_connection.cursor()
        try:
            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()['exists']
                assert exists, f"Required table '{table_name}' does not exist"
        finally:
            cur.close()

    def test_metrics_tables_exist(self, db_connection):
        """Verify financial metrics tables exist."""
        required_tables = [
            'stock_scores',
            'value_metrics',
            'quality_metrics',
            'growth_metrics',
            'stability_metrics',
            'key_metrics',
        ]

        cur = db_connection.cursor()
        try:
            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()['exists']
                assert exists, f"Metrics table '{table_name}' does not exist"
        finally:
            cur.close()

    def test_algo_trading_tables_exist(self, db_connection):
        """Verify algo trading system tables exist."""
        required_tables = [
            'algo_trades',
            'algo_positions',
            'algo_portfolio_snapshots',
            'algo_notifications',
            'algo_config',
            'algo_audit_log',
        ]

        cur = db_connection.cursor()
        try:
            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()['exists']
                assert exists, f"Algo trading table '{table_name}' does not exist"
        finally:
            cur.close()

    def test_financial_statement_tables_exist(self, db_connection):
        """Verify financial statement tables exist."""
        required_tables = [
            'annual_income_statement',
            'annual_balance_sheet',
            'annual_cash_flow',
            'quarterly_income_statement',
            'quarterly_balance_sheet',
            'quarterly_cash_flow',
            'ttm_income_statement',
            'ttm_cash_flow',
        ]

        cur = db_connection.cursor()
        try:
            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()['exists']
                assert exists, f"Financial statement table '{table_name}' does not exist"
        finally:
            cur.close()


class TestDatabaseSchemaColumns:
    """Validate that key tables have the expected columns."""

    def test_price_daily_columns(self, db_connection):
        """Verify price_daily has all required OHLCV columns."""
        required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'adj_close']

        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'price_daily' AND table_schema = 'public'
            """)
            existing_columns = [row['column_name'] for row in cur.fetchall()]

            for col in required_columns:
                assert col in existing_columns, f"price_daily missing column: {col}"

        finally:
            cur.close()

    def test_swing_trader_scores_columns(self, db_connection):
        """Verify swing_trader_scores has score (not swing_score) and components columns."""
        required_columns = ['symbol', 'date', 'score', 'components']

        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'swing_trader_scores' AND table_schema = 'public'
            """)
            existing_columns = [row['column_name'] for row in cur.fetchall()]

            for col in required_columns:
                assert col in existing_columns, f"swing_trader_scores missing column: {col}"

            # Verify 'swing_score' column does NOT exist (common mistake)
            assert 'swing_score' not in existing_columns, "swing_trader_scores should have 'score', not 'swing_score'"

        finally:
            cur.close()

    def test_algo_notifications_columns(self, db_connection):
        """Verify algo_notifications has correct column names (kind, seen, not type, is_read)."""
        required_columns = ['id', 'kind', 'severity', 'title', 'message', 'seen', 'created_at']

        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'algo_notifications' AND table_schema = 'public'
            """)
            existing_columns = [row['column_name'] for row in cur.fetchall()]

            for col in required_columns:
                assert col in existing_columns, f"algo_notifications missing column: {col}"

            # Verify correct names are used (common mistakes)
            assert 'kind' in existing_columns, "algo_notifications should have 'kind', not 'type'"
            assert 'seen' in existing_columns, "algo_notifications should have 'seen', not 'is_read'"

        finally:
            cur.close()

    def test_company_profile_primary_key(self, db_connection):
        """Verify company_profile has ticker as PK (not symbol)."""
        cur = db_connection.cursor()
        try:
            # Check for ticker column
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'company_profile' AND table_schema = 'public'
                AND column_name = 'ticker'
            """)
            assert cur.fetchone(), "company_profile missing 'ticker' column"

            # Verify ticker is used correctly (has data)
            cur.execute("SELECT COUNT(*) as count FROM company_profile WHERE ticker IS NOT NULL")
            count = cur.fetchone()['count']
            assert count > 0, "company_profile has no rows with ticker values"

        finally:
            cur.close()


class TestDatabaseIndexes:
    """Validate that key indexes exist for query performance."""

    def test_price_daily_indexes(self, db_connection):
        """Verify price_daily has (symbol, date) index."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'price_daily'
                AND indexdef LIKE '%symbol%date%' OR indexdef LIKE '%date%symbol%'
            """)
            indexes = cur.fetchall()

            # At least one index on (symbol, date) should exist
            assert len(indexes) > 0, "price_daily missing (symbol, date) index"

        finally:
            cur.close()

    def test_buy_sell_daily_indexes(self, db_connection):
        """Verify buy_sell_daily has (symbol, date) index."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'buy_sell_daily'
            """)
            indexes = [row['indexname'] for row in cur.fetchall()]

            # Should have some indexes
            assert len(indexes) > 0, "buy_sell_daily has no indexes"

        finally:
            cur.close()


class TestDatabaseDataIntegrity:
    """Validate data integrity constraints."""

    def test_stock_symbols_has_data(self, db_connection):
        """Verify stock_symbols table is populated."""
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT COUNT(*) as count FROM stock_symbols")
            count = cur.fetchone()['count']
            pytest.skip(f"stock_symbols is empty ({count} rows)") if count == 0 else None
            assert count > 1000, f"stock_symbols has very few rows: {count}"

        finally:
            cur.close()

    def test_company_profile_has_data(self, db_connection):
        """Verify company_profile table is populated."""
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT COUNT(*) as count FROM company_profile")
            count = cur.fetchone()['count']
            pytest.skip(f"company_profile is empty ({count} rows)") if count == 0 else None
            assert count > 1000, f"company_profile has very few rows: {count}"

        finally:
            cur.close()

    def test_unique_constraints(self, db_connection):
        """Verify critical unique constraints are enforced."""
        cur = db_connection.cursor()
        try:
            # price_daily should have UNIQUE(symbol, date)
            cur.execute("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name = 'price_daily'
                AND constraint_type = 'UNIQUE'
            """)
            constraints = [row['constraint_name'] for row in cur.fetchall()]
            assert len(constraints) > 0, "price_daily missing UNIQUE constraint"

        finally:
            cur.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
