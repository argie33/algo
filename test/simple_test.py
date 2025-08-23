#!/usr/bin/env python3
"""
Simple test script to validate the ECS container test environment.
This script tests basic functionality without running the full data loading scripts.
"""
import logging
import os
import sys
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("simple_test")

# IMPORTANT: Import mock_boto3 BEFORE importing boto3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import mock_boto3

    # Replace boto3 in sys.modules before any imports
    sys.modules["boto3"] = mock_boto3
    logger.info("Mock boto3 module installed")
except Exception as e:
    logger.error(f"Failed to install mock boto3: {e}")

import json

# Now we can safely import boto3 (which will be our mock)
import boto3
import psycopg2


def test_mock_boto3():
    """Test that mock boto3 is working"""
    logger.info("Testing mock boto3...")

    try:
        # Test Secrets Manager
        client = boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId="test-db-secret")
        logger.info(f"✅ Secrets Manager mock working: {secret['SecretId']}")

        # Test S3
        s3_client = boto3.client("s3")
        logger.info("✅ S3 mock client created successfully")

        # Test SNS
        sns_client = boto3.client("sns")
        logger.info("✅ SNS mock client created successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Mock boto3 test failed: {str(e)}")
        return False


def test_database_connection():
    """Test database connectivity"""
    logger.info("Testing database connection...")

    try:
        conn = psycopg2.connect(
            host="postgres",
            port="5432",
            user="testuser",
            password="testpass",
            database="testdb",
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM stocks;")
        stock_count = cursor.fetchone()[0]

        logger.info(f"✅ Database connection successful")
        logger.info(f"PostgreSQL version: {version}")
        logger.info(f"Stocks table has {stock_count} rows")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"❌ Database test failed: {str(e)}")
        return False


def test_environment_variables():
    """Test that required environment variables are set"""
    logger.info("Testing environment variables...")

    required_vars = {"DB_SECRET_ARN": "test-db-secret", "PYTHONUNBUFFERED": "1"}

    all_good = True

    for var, expected in required_vars.items():
        actual = os.environ.get(var)
        if actual == expected:
            logger.info(f"✅ {var}={actual}")
        else:
            logger.error(f"❌ {var}={actual} (expected: {expected})")
            all_good = False

    # Check PYTHONPATH
    python_path = ":".join(sys.path[:3])
    logger.info(f"✅ PYTHONPATH includes: {python_path}")

    return all_good


def test_table_structure():
    """Test that database tables have the expected structure"""
    logger.info("Testing database table structure...")

    try:
        conn = psycopg2.connect(
            host="postgres",
            port="5432",
            user="testuser",
            password="testpass",
            database="testdb",
        )

        cursor = conn.cursor()

        # Test stocks table structure
        cursor.execute(
            """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'stocks' 
            ORDER BY ordinal_position;
        """
        )

        stocks_columns = cursor.fetchall()
        expected_columns = [
            "id",
            "symbol",
            "name",
            "market",
            "created_at",
            "updated_at",
        ]
        actual_columns = [col[0] for col in stocks_columns]

        missing_columns = [col for col in expected_columns if col not in actual_columns]

        if missing_columns:
            logger.error(f"❌ Missing columns in stocks table: {missing_columns}")
            return False
        else:
            logger.info(
                f"✅ Stocks table structure correct: {len(actual_columns)} columns"
            )

        # Test that we can insert and retrieve data
        cursor.execute(
            """
            INSERT INTO stocks (symbol, name, market) 
            VALUES ('TEST', 'Test Company', 'TEST') 
            ON CONFLICT (symbol) DO NOTHING
            RETURNING id;
        """
        )

        result = cursor.fetchone()
        if result:
            logger.info("✅ Successfully inserted test data")
        else:
            logger.info("✅ Test data already exists (conflict handled)")

        conn.commit()
        cursor.close()
        conn.close()

        return True

    except Exception as e:
        logger.error(f"❌ Table structure test failed: {str(e)}")
        return False


def main():
    """Run all tests"""
    logger.info("=== Starting Simple Test Suite ===")

    tests = [
        ("Environment Variables", test_environment_variables),
        ("Mock boto3", test_mock_boto3),
        ("Database Connection", test_database_connection),
        ("Table Structure", test_table_structure),
    ]

    results = {}

    for test_name, test_func in tests:
        logger.info(f"\n--- Running: {test_name} ---")
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            logger.error(f"Test {test_name} threw exception: {str(e)}")
            results[test_name] = False

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")

    passed = 0
    for test_name, success in results.items():
        status = "PASS" if success else "FAIL"
        status_icon = "✅" if success else "❌"
        logger.info(f"{status_icon} {status}: {test_name}")
        if success:
            passed += 1

    total = len(results)
    logger.info(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All tests passed! Environment is ready.")
        return True
    else:
        logger.error("❌ Some tests failed. Check the logs above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
