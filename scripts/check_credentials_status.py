#!/usr/bin/env python3
"""Check and validate AWS credentials and Alpaca API status.

SESSION 289 FIX: Alpaca API returning 401 Unauthorized in orchestrator runs.
This script checks if credentials are valid and accessible.
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def check_aws_credentials() -> bool:
    """Check if AWS credentials are accessible."""
    logger.info("1. Checking AWS Credentials...")

    try:
        import boto3

        # Try to get identity
        sts = boto3.client("sts", region_name=os.getenv("AWS_REGION", "us-east-1"))
        identity = sts.get_caller_identity()

        logger.info(f"  AWS Account: {identity['Account']}")
        logger.info(f"  AWS User/Role: {identity['Arn']}")
        logger.info("  Status: OK - AWS credentials are valid")
        return True

    except Exception as e:
        logger.error(f"  FAILED: {type(e).__name__}: {e}")
        logger.error("  AWS credentials may be expired or misconfigured")
        return False


def check_alpaca_credentials() -> bool:
    """Check if Alpaca API credentials are valid."""
    logger.info("\n2. Checking Alpaca Credentials...")

    try:
        # Try environment variables first
        api_key = os.getenv("APCA_API_KEY_ID")
        api_secret = os.getenv("APCA_API_SECRET_KEY")

        if not api_key or not api_secret:
            logger.warning("  Alpaca env vars not set, trying from Secrets Manager...")
            try:
                import boto3

                sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
                secret = sm.get_secret_value(SecretId="algo/alpaca")
                import json

                data = json.loads(secret["SecretString"])
                api_key = data.get("APCA_API_KEY_ID")
                api_secret = data.get("APCA_API_SECRET_KEY")
            except Exception as e:
                logger.error(f"  Could not load from Secrets Manager: {e}")
                return False

        if not api_key or not api_secret:
            logger.error("  Alpaca credentials not found")
            return False

        # Try to connect to Alpaca
        import alpaca_trade_api

        api = alpaca_trade_api.REST(api_key, api_secret)
        account = api.get_account()

        logger.info(f"  Alpaca Account: {account.account_number}")
        logger.info(f"  Account Status: {account.status}")
        logger.info(f"  Buying Power: ${float(account.buying_power):,.2f}")
        logger.info("  Status: OK - Alpaca credentials are valid")
        return True

    except Exception as e:
        logger.error(f"  FAILED: {type(e).__name__}: {e}")
        if "401" in str(e) or "Unauthorized" in str(e):
            logger.error("  Alpaca returned 401 Unauthorized - credentials may be expired")
        return False


def check_database_connection() -> bool:
    """Check if database is accessible."""
    logger.info("\n3. Checking Database Connection...")

    try:
        import psycopg2

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()

        logger.info("  Database connection: OK")
        return True

    except Exception as e:
        logger.error(f"  FAILED: {e}")
        return False


def main() -> int:
    """Check all credentials."""
    logger.info("=== CREDENTIALS STATUS CHECK ===\n")

    results = {
        "aws": check_aws_credentials(),
        "alpaca": check_alpaca_credentials(),
        "database": check_database_connection(),
    }

    logger.info("\n=== SUMMARY ===\n")
    for name, status in results.items():
        icon = "OK" if status else "FAIL"
        print(f"  {icon}: {name:15s}")

    all_ok = all(results.values())

    if all_ok:
        logger.info("\nAll credentials are valid. Orchestrator should work.")
        return 0
    else:
        logger.error("\nSome credentials are invalid or unavailable.")
        logger.error("FIX: Update AWS Secrets Manager with fresh Alpaca API credentials")
        return 1


if __name__ == "__main__":
    sys.exit(main())
