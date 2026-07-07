#!/usr/bin/env python3
"""
Test Script: Verify AWS RDS Credential Initialization

This script tests the RDS credential fetching and connection validation.

Usage:
    # Test with environment variables (local dev)
    python dashboard/test_aws_rds_connection.py

    # Test with AWS Secrets Manager
    export FORCE_AWS=true
    export DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:algo/rds-xxxxx
    python dashboard/test_aws_rds_connection.py

    # Test with specific secret
    python dashboard/test_aws_rds_connection.py --secret algo/rds --region us-east-1

    # Skip connection validation (for offline testing)
    python dashboard/test_aws_rds_connection.py --skip-validation
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_rds_initialization(
    secret_name: str | None = None,
    aws_region: str | None = None,
    force_aws: bool = False,
    skip_validation: bool = False,
) -> None:
    """Test RDS credential initialization.

    Args:
        secret_name: AWS Secrets Manager secret name/ARN
        aws_region: AWS region
        force_aws: Force AWS Secrets Manager even in local dev
        skip_validation: Skip connection validation
    """
    print("\n" + "=" * 70)
    print("AWS RDS Connection Test")
    print("=" * 70)

    print("\n1. Environment Setup")
    print(f"   AWS_REGION: {os.getenv('AWS_REGION', 'not set')}")
    print(f"   DB_SECRET_ARN: {os.getenv('DB_SECRET_ARN', 'not set')}")
    print(f"   DB_SECRET_NAME: {os.getenv('DB_SECRET_NAME', 'not set')}")
    print(f"   FORCE_AWS: {os.getenv('FORCE_AWS', 'false')}")
    print(f"   DB_HOST: {os.getenv('DB_HOST', 'not set')}")
    print(f"   DB_PORT: {os.getenv('DB_PORT', 'not set')}")
    print(f"   DB_USER: {os.getenv('DB_USER', 'not set')}")
    print(f"   DB_PASSWORD: {'***' if os.getenv('DB_PASSWORD') else 'not set'}")
    print(f"   DB_NAME: {os.getenv('DB_NAME', 'not set')}")

    print("\n2. Credential Fetching")
    try:
        from dashboard.aws_rds_init import initialize_aws_rds_credentials

        credentials = initialize_aws_rds_credentials(
            secret_name=secret_name,
            aws_region=aws_region,
            force_aws=force_aws,
            validate_connection=not skip_validation,
            verbose=True,
        )

        print("   ✓ Credentials successfully loaded")
        print(f"\n3. Connection Details")
        print(f"   Host: {credentials['host']}")
        print(f"   Port: {credentials['port']}")
        print(f"   User: {credentials['username'][:8]}...")
        print(f"   Database: {credentials['dbname']}")

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return

    print("\n4. Environment Variables")
    print(f"   DB_HOST: {os.getenv('DB_HOST')}")
    print(f"   DB_PORT: {os.getenv('DB_PORT')}")
    print(f"   DB_USER: {os.getenv('DB_USER', 'not set')[:8]}...")
    print(f"   DB_NAME: {os.getenv('DB_NAME')}")

    print("\n5. Database Context Test")
    try:
        from utils.db import DatabaseContext

        with DatabaseContext('read', timeout=10) as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()
            if version:
                print(f"   ✓ Query successful")
                print(f"   PostgreSQL version: {version[0][:80]}")
            else:
                print("   ✗ Query returned no result")

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return

    print("\n6. Bootstrap Verification")
    try:
        from dashboard.bootstrap import (
            bootstrap_dashboard_database,
            check_database_connectivity,
            get_dashboard_database_config,
        )

        config = get_dashboard_database_config()
        print(f"   ✓ Config retrieved: {config['host']}:{config['port']}/{config['database']}")

        if not skip_validation:
            if check_database_connectivity():
                print("   ✓ Connectivity check passed")
            else:
                print("   ✗ Connectivity check failed")

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return

    print("\n" + "=" * 70)
    print("SUCCESS: All tests passed!")
    print("=" * 70 + "\n")


def test_credentials_priority() -> None:
    """Test credential fetching priority order.

    Demonstrates the priority: Secrets Manager > Environment variables
    """
    print("\n" + "=" * 70)
    print("Credential Priority Test")
    print("=" * 70)

    try:
        from dashboard.aws_rds_init import RDSCredentialFetcher

        fetcher = RDSCredentialFetcher(aws_region="us-east-1", force_aws=False)

        print("\nTesting credential priority order:")
        print("1. AWS Secrets Manager (if secret_name provided and in AWS)")
        print("2. Environment variables (DB_HOST, DB_PORT, DB_USER, etc.)")

        # Try to get credentials using priority
        try:
            credentials = fetcher.get_credentials_from_env_or_secrets(secret_name=None)
            print(f"\n✓ Credentials obtained from environment variables")
            print(f"  Host: {credentials['host']}")
            print(f"  Database: {credentials['dbname']}")
        except Exception as e:
            print(f"\n✗ No credentials available: {e}")

    except Exception as e:
        print(f"\n✗ Priority test failed: {e}")

    print("\n" + "=" * 70 + "\n")


def test_error_handling() -> None:
    """Test error handling scenarios.

    Demonstrates fail-fast behavior on invalid credentials.
    """
    print("\n" + "=" * 70)
    print("Error Handling Test")
    print("=" * 70)

    from dashboard.aws_rds_init import (
        AWSRDSInitializationError,
        RDSCredentialFetcher,
    )

    scenarios: list[tuple[str, Callable[[], None]]] = [
        ("Missing DB_HOST", lambda: _test_missing_host()),
        ("Invalid DB_PORT", lambda: _test_invalid_port()),
        ("Invalid Secret", lambda: _test_invalid_secret()),
    ]

    for scenario_name, test_func in scenarios:
        try:
            print(f"\n{scenario_name}:")
            test_func()
        except AWSRDSInitializationError as e:
            print(f"  ✓ Caught expected error: {str(e)[:80]}...")
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")

    print("\n" + "=" * 70 + "\n")


def _test_missing_host() -> None:
    """Test handling of missing DB_HOST."""
    # Save original
    original_host = os.environ.pop("DB_HOST", None)
    original_endpoint = os.environ.pop("DB_ENDPOINT", None)

    try:
        from dashboard.aws_rds_init import RDSCredentialFetcher

        fetcher = RDSCredentialFetcher(force_aws=False)
        fetcher.get_credentials_from_env_or_secrets()
    finally:
        # Restore
        if original_host:
            os.environ["DB_HOST"] = original_host
        if original_endpoint:
            os.environ["DB_ENDPOINT"] = original_endpoint


def _test_invalid_port() -> None:
    """Test handling of invalid DB_PORT."""
    os.environ["DB_PORT"] = "not_a_number"
    os.environ["DB_HOST"] = "localhost"
    os.environ["DB_USER"] = "test"
    os.environ["DB_PASSWORD"] = "test"
    os.environ["DB_NAME"] = "test"

    try:
        from dashboard.aws_rds_init import RDSCredentialFetcher

        fetcher = RDSCredentialFetcher(force_aws=False)
        fetcher.get_credentials_from_env_or_secrets()
    finally:
        # Cleanup
        for var in ["DB_PORT", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]:
            os.environ.pop(var, None)


def _test_invalid_secret() -> None:
    """Test handling of invalid secret."""
    from dashboard.aws_rds_init import RDSCredentialFetcher

    fetcher = RDSCredentialFetcher(aws_region="us-east-1", force_aws=False)
    try:
        fetcher.fetch_from_secrets_manager("nonexistent-secret-that-does-not-exist")
    except Exception:
        raise  # Expected to fail


def main() -> None:
    """Run tests based on command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test AWS RDS credential initialization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with environment variables
  python dashboard/test_aws_rds_connection.py

  # Test with AWS Secrets Manager
  export FORCE_AWS=true
  export DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:algo/rds-xxxxx
  python dashboard/test_aws_rds_connection.py

  # Test specific secret
  python dashboard/test_aws_rds_connection.py --secret algo/rds --region us-east-1

  # Run all tests
  python dashboard/test_aws_rds_connection.py --all
        """,
    )

    parser.add_argument(
        "--secret",
        type=str,
        help="AWS Secrets Manager secret name/ARN",
    )
    parser.add_argument(
        "--region",
        type=str,
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip database connection validation",
    )
    parser.add_argument(
        "--priority",
        action="store_true",
        help="Test credential priority order only",
    )
    parser.add_argument(
        "--errors",
        action="store_true",
        help="Test error handling scenarios only",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests",
    )

    args = parser.parse_args()

    try:
        if args.all:
            test_rds_initialization(
                secret_name=args.secret,
                aws_region=args.region,
                skip_validation=args.skip_validation,
            )
            test_credentials_priority()
            test_error_handling()
        elif args.priority:
            test_credentials_priority()
        elif args.errors:
            test_error_handling()
        else:
            test_rds_initialization(
                secret_name=args.secret or os.getenv("DB_SECRET_ARN"),
                aws_region=args.region or os.getenv("AWS_REGION"),
                force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
                skip_validation=args.skip_validation,
            )
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {e}")
        logger.exception("Test exception:")
        sys.exit(1)


if __name__ == "__main__":
    main()
