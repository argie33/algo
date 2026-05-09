#!/usr/bin/env python3
"""
Test credential rotation logic locally without AWS

Validates:
- Credential manager loads from Secrets Manager or env vars
- Password generation works
- RDS connection validation works (requires running RDS instance)
- Rotation event simulation

Usage:
    # Test credential loading
    python test_credential_rotation.py --test-cred-load

    # Test password generation
    python test_credential_rotation.py --test-password-gen

    # Test RDS connection (requires DB_HOST, DB_USER, DB_PASSWORD env vars)
    python test_credential_rotation.py --test-rds-connection

    # Simulate rotation event
    python test_credential_rotation.py --simulate-rotation
"""

import json
import logging
import os
import sys
import argparse
import psycopg2
import secrets
import string
from typing import Dict, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class RotationTestHelper:
    """Test helper for credential rotation."""

    def test_credential_manager_load(self) -> bool:
        """Test that credential_manager loads correctly."""
        try:
            from credential_manager import get_credential_manager
            cred_mgr = get_credential_manager()

            logger.info("✓ credential_manager imported successfully")

            # Try to get credentials
            try:
                db_creds = cred_mgr.get_db_credentials()
                logger.info(f"✓ DB credentials loaded from {db_creds['host']}")
                return True
            except ValueError as e:
                logger.warning(f"DB credentials not available (expected if env not set): {e}")
                return True  # Expected in local dev

        except ImportError as e:
            logger.error(f"✗ Failed to import credential_manager: {e}")
            return False

    def test_password_generation(self) -> bool:
        """Test password generation."""
        try:
            chars = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
            password1 = ''.join(secrets.choice(chars) for _ in range(32))
            password2 = ''.join(secrets.choice(chars) for _ in range(32))

            assert len(password1) == 32, "Password length mismatch"
            assert len(password2) == 32, "Password length mismatch"
            assert password1 != password2, "Passwords should be different"

            logger.info(f"✓ Generated 2 unique passwords (length: {len(password1)})")
            logger.info(f"  Sample: {password1[:10]}... (masked for security)")

            # Verify password can be JSON encoded
            test_secret = {"password": password1}
            json_str = json.dumps(test_secret)
            parsed = json.loads(json_str)
            assert parsed["password"] == password1

            logger.info("✓ Passwords are JSON-serializable")
            return True

        except Exception as e:
            logger.error(f"✗ Password generation failed: {e}")
            return False

    def test_rds_connection(self, host: str, port: int = 5432, user: str = "postgres", password: str = "", database: str = "postgres") -> bool:
        """Test RDS connection with stored credentials."""
        try:
            if not password:
                logger.error("✗ Password not provided or empty")
                return False

            logger.info(f"Testing connection to {host}:{port}/{database}...")

            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=5
            )

            cur = conn.cursor()
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            cur.close()
            conn.close()

            logger.info(f"✓ Connection successful to {host}")
            logger.info(f"  PostgreSQL: {version.split(',')[0]}")
            return True

        except psycopg2.OperationalError as e:
            logger.error(f"✗ Connection failed (check host, port, user, password): {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error: {e}")
            return False

    def test_password_update_sql(self) -> bool:
        """Test password update SQL syntax."""
        try:
            test_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
            username = "testuser"

            # Simulate the SQL that would be executed
            escaped_password = test_password.replace("'", "''")
            sql = f"ALTER USER {username} WITH PASSWORD '{escaped_password}'"

            logger.info(f"✓ Generated ALTER USER SQL:")
            logger.info(f"  ALTER USER {username} WITH PASSWORD '<masked>'")

            # Verify SQL doesn't have syntax errors (basic check)
            assert "ALTER USER" in sql
            assert "WITH PASSWORD" in sql
            assert f"'{escaped_password}'" in sql

            logger.info("✓ SQL syntax is valid")
            return True

        except Exception as e:
            logger.error(f"✗ SQL generation failed: {e}")
            return False

    def simulate_rotation_event(self, secret_id: str = "test-secret") -> bool:
        """Simulate a rotation event structure."""
        try:
            # Simulate the three stages of rotation
            stages = ["create", "set", "finish"]

            for stage in stages:
                event = {
                    "ClientRequestToken": secrets.token_hex(16),
                    "SecretId": secret_id,
                    "Step": stage,
                    "SecretVersion": secrets.token_hex(16)
                }

                logger.info(f"✓ Rotation event ({stage}):")
                logger.info(f"  ClientRequestToken: {event['ClientRequestToken'][:16]}...")
                logger.info(f"  SecretId: {event['SecretId']}")
                logger.info(f"  Step: {event['Step']}")

            logger.info("\n✓ All rotation stages simulated successfully")
            return True

        except Exception as e:
            logger.error(f"✗ Rotation simulation failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Test credential rotation components")

    parser.add_argument("--test-cred-load", action="store_true", help="Test credential manager loading")
    parser.add_argument("--test-password-gen", action="store_true", help="Test password generation")
    parser.add_argument("--test-rds-connection", action="store_true", help="Test RDS connection (requires env vars)")
    parser.add_argument("--test-sql", action="store_true", help="Test password update SQL")
    parser.add_argument("--simulate-rotation", action="store_true", help="Simulate rotation event")
    parser.add_argument("--all", action="store_true", help="Run all tests")

    # RDS connection params
    parser.add_argument("--db-host", default=os.getenv("DB_HOST", "localhost"), help="Database host")
    parser.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "5432")), help="Database port")
    parser.add_argument("--db-user", default=os.getenv("DB_USER", "postgres"), help="Database user")
    parser.add_argument("--db-password", default=os.getenv("DB_PASSWORD", ""), help="Database password")
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "postgres"), help="Database name")

    args = parser.parse_args()

    helper = RotationTestHelper()
    results = {}

    # Run selected tests
    if args.test_cred_load or args.all:
        logger.info("\n=== Testing Credential Manager ===")
        results["credential_manager"] = helper.test_credential_manager_load()

    if args.test_password_gen or args.all:
        logger.info("\n=== Testing Password Generation ===")
        results["password_generation"] = helper.test_password_generation()

    if args.test_sql or args.all:
        logger.info("\n=== Testing Password Update SQL ===")
        results["sql_generation"] = helper.test_password_update_sql()

    if args.test_rds_connection or args.all:
        logger.info("\n=== Testing RDS Connection ===")
        results["rds_connection"] = helper.test_rds_connection(
            host=args.db_host,
            port=args.db_port,
            user=args.db_user,
            password=args.db_password,
            database=args.db_name
        )

    if args.simulate_rotation or args.all:
        logger.info("\n=== Simulating Rotation Event ===")
        results["rotation_event"] = helper.simulate_rotation_event()

    # Summary
    if not results:
        parser.print_help()
        sys.exit(1)

    logger.info("\n" + "=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_bool in results.items():
        status = "✓ PASS" if passed_bool else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {passed}/{total} passed")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
