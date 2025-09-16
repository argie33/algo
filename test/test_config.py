#!/usr/bin/env python3
"""
Test configuration and utilities for the ECS container test environment.
"""
import logging
import os
import time

import psycopg2

logger = logging.getLogger("test_config")

# Test environment configuration
TEST_CONFIG = {
    "database": {
        "host": "postgres",
        "port": "5432",
        "user": "testuser",
        "password": "testpass",
        "database": "testdb",
    },
    "aws": {"region": "us-east-1", "secret_arn": "test-db-secret"},
    "scripts_to_test": [
        "loadstocksymbols_test.py",
        # Add more scripts as they are created
    ],
}


def verify_database_connection():
    """Verify that we can connect to the test database"""
    try:
        conn = psycopg2.connect(**TEST_CONFIG["database"])
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        logger.info(f"Database connection successful. PostgreSQL version: {version}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False


def verify_tables_exist():
    """Verify that required tables exist in the database"""
    try:
        conn = psycopg2.connect(**TEST_CONFIG["database"])
        cursor = conn.cursor()

        # Check for stocks table
        cursor.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('stocks', 'earnings', 'prices');
        """
        )
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = ["stocks", "earnings", "prices"]
        missing_tables = [table for table in expected_tables if table not in tables]

        if missing_tables:
            logger.warning(f"Missing tables: {missing_tables}")
        else:
            logger.info("All required tables exist")

        cursor.close()
        conn.close()
        return len(missing_tables) == 0

    except Exception as e:
        logger.error(f"Error checking tables: {str(e)}")
        return False


def get_table_counts():
    """Get row counts for main tables"""
    try:
        conn = psycopg2.connect(**TEST_CONFIG["database"])
        cursor = conn.cursor()

        counts = {}
        tables = ["stocks", "earnings", "prices"]

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            counts[table] = count
            logger.info(f"Table '{table}' has {count} rows")

        cursor.close()
        conn.close()
        return counts

    except Exception as e:
        logger.error(f"Error getting table counts: {str(e)}")
        return {}


def setup_test_data():
    """Set up additional test data if needed"""
    logger.info("Setting up test data...")

    try:
        conn = psycopg2.connect(**TEST_CONFIG["database"])
        cursor = conn.cursor()

        # Add some additional test stocks if they don't exist
        test_stocks = [
            ("TSLA", "Tesla, Inc.", "NASDAQ"),
            ("AMZN", "Amazon.com, Inc.", "NASDAQ"),
            ("META", "Meta Platforms, Inc.", "NASDAQ"),
            ("NVDA", "NVIDIA Corporation", "NASDAQ"),
            ("NFLX", "Netflix, Inc.", "NASDAQ"),
        ]

        for symbol, name, market in test_stocks:
            cursor.execute(
                """
                INSERT INTO stocks (symbol, name, market) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (symbol) DO NOTHING;
            """,
                (symbol, name, market),
            )

        conn.commit()
        logger.info("Test data setup completed")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Error setting up test data: {str(e)}")
        return False


def cleanup_test_data():
    """Clean up test data (optional)"""
    logger.info("Cleaning up test data...")
    # This could be used to reset the database state between tests
    # For now, we'll leave the data in place
    pass


def health_check():
    """Perform a comprehensive health check of the test environment"""
    logger.info("=== Performing Health Check ===")

    checks = {
        "database_connection": verify_database_connection(),
        "tables_exist": verify_tables_exist(),
        "test_data_setup": setup_test_data(),
    }

    # Log table counts
    get_table_counts()

    all_passed = all(checks.values())

    logger.info("=== Health Check Summary ===")
    for check, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {check}")

    if all_passed:
        logger.info("🎉 All health checks passed!")
    else:
        logger.error("❌ Some health checks failed")

    return all_passed


if __name__ == "__main__":
    # Run health check if this script is executed directly
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    )

    success = health_check()
    exit(0 if success else 1)
