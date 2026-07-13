#!/usr/bin/env python3
"""
Start dashboard in AWS mode with all credentials properly configured.

This script ensures:
1. All AWS credentials are loaded (from Secrets Manager if needed)
2. Dashboard connects to AWS API (not localhost)
3. Cognito authentication is configured
4. Clear error messages if anything is missing
"""

import json
import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def load_aws_credentials():
    """Load and validate AWS credentials."""
    logger.info("="*70)
    logger.info("AWS Dashboard Startup")
    logger.info("="*70)

    # Check environment
    api_url = os.environ.get("DASHBOARD_API_URL")
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")
    username = os.environ.get("COGNITO_USERNAME")
    password = os.environ.get("COGNITO_PASSWORD")

    logger.info("\nChecking AWS credentials...")

    # If password is missing, fetch from Secrets Manager
    if not password:
        logger.info("  COGNITO_PASSWORD not set - fetching from Secrets Manager...")
        try:
            import boto3
            sm = boto3.client("secretsmanager", region_name="us-east-1")
            secret_resp = sm.get_secret_value(SecretId="algo/dashboard-config")
            secret_data = json.loads(secret_resp["SecretString"])
            password = secret_data.get("cognito_password")
            if password:
                os.environ["COGNITO_PASSWORD"] = password
                logger.info("  ✓ Got COGNITO_PASSWORD from Secrets Manager")
            else:
                logger.error("  ✗ COGNITO_PASSWORD not in Secrets Manager")
                return False
        except Exception as e:
            logger.error(f"  ✗ Failed to fetch from Secrets Manager: {e}")
            return False

    # Validate all required credentials
    if not all([api_url, pool_id, client_id, username, password]):
        missing = []
        if not api_url:
            missing.append("DASHBOARD_API_URL")
        if not pool_id:
            missing.append("COGNITO_USER_POOL_ID")
        if not client_id:
            missing.append("COGNITO_CLIENT_ID")
        if not username:
            missing.append("COGNITO_USERNAME")
        if not password:
            missing.append("COGNITO_PASSWORD")

        logger.error(f"  ✗ Missing credentials: {', '.join(missing)}")
        return False

    logger.info("  ✓ All credentials configured")
    logger.info(f"    DASHBOARD_API_URL: {api_url[:50]}...")
    logger.info(f"    COGNITO_USER_POOL_ID: {pool_id}")
    logger.info(f"    COGNITO_USERNAME: {username}")

    return True


def start_dashboard():
    """Start the dashboard in AWS mode."""
    logger.info("\nStarting dashboard...")
    logger.info("  Using AWS API endpoint")
    logger.info("  Press Ctrl+C to exit\n")

    try:
        subprocess.run([sys.executable, "-m", "dashboard"], check=False)
    except KeyboardInterrupt:
        logger.info("\nDashboard stopped")


if __name__ == "__main__":
    if not load_aws_credentials():
        logger.error("\nCannot start dashboard - missing or invalid credentials")
        sys.exit(1)

    start_dashboard()
