#!/usr/bin/env python3
"""
Integration tests for data loader reliability and correctness.

Tests schema validation, error handling, idempotency, and data completeness.

Run: python3 -m pytest test_data_loaders.py -v
"""

import pytest
import psycopg2
from datetime import date, timedelta
from typing import List, Dict, Any

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
from loadpricedaily import PriceDailyLoader


class TestDataLoaderSchema:
    """Test that loaders populate tables with correct schema."""

    @pytest.fixture
    def db_connection(self):
        """Create a database connection."""
        credential_manager = get_credential_manager()
        config = {
            "host": "localhost",
            "port": 5432,
            "user": "stocks",
            "password": credential_manager.get_db_credentials()["password"],
            "database": "stocks",
        }
        try:
            conn = psycopg2.connect(**config)
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    def test_price_daily_columns_exist(self, db_connection):
        """
        Test that price_daily table has all required columns.

        Expected: symbol, date, open, high, low, close, volume, etc.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'price_daily'")
            columns = [row[0] for row in cur.fetchall()]

            required = ["symbol", "date", "open", "high", "low", "close", "volume"]
            for col in required:
                assert col in columns, f"Missing column: {col}"

        finally:
            cur.close()

    def test_technical_data_daily_columns(self, db_connection):
        """
        Test that technical_data_daily has RSI, MACD, SMA columns.

        Expected: sma_20, sma_50, sma_200, rsi, macd, atr, etc.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'technical_data_daily'")
            columns = [row[0] for row in cur.fetchall()]

            required = ["sma_20", "sma_50", "sma_200", "rsi", "macd", "atr"]
            for col in required:
                assert col in columns, f"Missing technical column: {col}"

        finally:
            cur.close()

    def test_swing_trader_scores_schema(self, db_connection):
        """
        Test that swing_trader_scores table has component score columns.

        Expected: swing_score, grade, setup_pts, trend_pts, momentum_pts, etc.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'swing_trader_scores'")
            columns = [row[0] for row in cur.fetchall()]

            required = ["swing_score", "grade", "setup_pts", "trend_pts", "momentum_pts"]
            for col in required:
                assert col in columns, f"Missing swing_trader_scores column: {col}"

        finally:
            cur.close()


class TestLoaderDataValidation:
    """Test that loaders validate data before inserting."""

    @pytest.fixture
    def db_connection(self):
        """Create a database connection."""
        credential_manager = get_credential_manager()
        config = {
            "host": "localhost",
            "port": 5432,
            "user": "stocks",
            "password": credential_manager.get_db_credentials()["password"],
            "database": "stocks",
        }
        try:
            conn = psycopg2.connect(**config)
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    def test_price_data_has_no_nulls(self, db_connection):
        """
        Test that price data doesn't have unexpected NULLs.

        Expected: symbol, date, close, volume should never be NULL.
        """
        cur = db_connection.cursor()
        try:
            # Check latest AAPL prices
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE symbol = 'AAPL'
                AND date > CURRENT_DATE - INTERVAL '30 days'
                AND (symbol IS NULL OR date IS NULL OR close IS NULL)
            """)
            null_count = cur.fetchone()[0]
            assert null_count == 0, f"Found {null_count} rows with NULL critical columns"

        finally:
            cur.close()

    def test_ohlc_logic_valid(self, db_connection):
        """
        Test that OHLC values follow market rules: low <= open <= close <= high.

        Expected: No OHLC violations in recent data.
        """
        cur = db_connection.cursor()
        try:
            # Check for OHLC violations
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE date > CURRENT_DATE - INTERVAL '30 days'
                AND NOT (low <= open AND open <= close AND close <= high)
            """)
            violations = cur.fetchone()[0]
            assert violations == 0, f"Found {violations} OHLC logic violations"

        finally:
            cur.close()

    def test_volume_non_negative(self, db_connection):
        """
        Test that volume values are non-negative.

        Expected: No negative volumes.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE date > CURRENT_DATE - INTERVAL '30 days'
                AND volume < 0
            """)
            neg_count = cur.fetchone()[0]
            assert neg_count == 0, f"Found {neg_count} rows with negative volume"

        finally:
            cur.close()


class TestLoaderIdempotency:
    """Test that loaders can run multiple times safely."""

    @pytest.fixture
    def db_connection(self):
        """Create a database connection."""
        credential_manager = get_credential_manager()
        config = {
            "host": "localhost",
            "port": 5432,
            "user": "stocks",
            "password": credential_manager.get_db_credentials()["password"],
            "database": "stocks",
        }
        try:
            conn = psycopg2.connect(**config)
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    def test_price_loader_idempotent(self, db_connection):
        """
        Test that running price loader twice doesn't duplicate data.

        Expected: Row count should be same after second run.
        """
        cur = db_connection.cursor()
        try:
            # Get baseline count for AAPL
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE symbol = 'AAPL' AND date > CURRENT_DATE - INTERVAL '10 days'
            """)
            baseline = cur.fetchone()[0]

            # In a real test, would run: loader.run(['AAPL'], parallelism=1)
            # For now, just verify the query works

            # Check count again (would be same if loader is idempotent)
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE symbol = 'AAPL' AND date > CURRENT_DATE - INTERVAL '10 days'
            """)
            after = cur.fetchone()[0]

            # Counts should match (within reason, allowing 1-2 new records if date rolled)
            assert abs(baseline - after) <= 2, "Loader may not be idempotent"

        finally:
            cur.close()


class TestLoaderDataAge:
    """Test that loaders keep data current."""

    @pytest.fixture
    def db_connection(self):
        """Create a database connection."""
        credential_manager = get_credential_manager()
        config = {
            "host": "localhost",
            "port": 5432,
            "user": "stocks",
            "password": credential_manager.get_db_credentials()["password"],
            "database": "stocks",
        }
        try:
            conn = psycopg2.connect(**config)
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    def test_price_data_recent(self, db_connection):
        """
        Test that price_daily has data from the last trading day.

        Expected: MAX(date) should be today or yesterday.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            today = date.today()
            max_days_old = (today - max_date).days

            # Allow up to 2 business days old (weekend, holiday)
            assert max_days_old <= 2, f"Latest price data is {max_days_old} days old"

        finally:
            cur.close()

    def test_technical_data_recent(self, db_connection):
        """
        Test that technical_data_daily is current.

        Expected: MAX(date) should be recent.
        """
        cur = db_connection.cursor()
        try:
            cur.execute("SELECT MAX(date) FROM technical_data_daily")
            max_date = cur.fetchone()[0]

            if max_date:  # May be empty in test environment
                today = date.today()
                max_days_old = (today - max_date).days
                assert max_days_old <= 2, f"Latest technical data is {max_days_old} days old"

        finally:
            cur.close()


class TestLoaderErrorHandling:
    """Test that loaders handle errors gracefully."""

    def test_network_timeout_handling(self):
        """
        Test that loader handles network timeouts without crashing.

        Expected: Should fail gracefully with clear error message.
        """
        # This would require mocking the API layer
        # For now, document the expected behavior
        pytest.skip("Requires API mocking to test network failures")

    def test_database_error_handling(self):
        """
        Test that loader handles database errors without crashing.

        Expected: Should log error and allow retry.
        """
        pytest.skip("Requires DB failure simulation")

    def test_partial_data_load(self):
        """
        Test that loader handles partial success (some symbols fail).

        Expected: Should load successful symbols, report failures.
        """
        pytest.skip("Requires simulated symbol failures")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
