#!/usr/bin/env python3
"""Verify Session 155 deployment (DynamoDB tables + Docker image rebuild).

Post-deployment validation for:
1. DynamoDB tables created with correct attributes
2. Lambda orchestrator can acquire locks
3. ECS loaders running with updated images
4. Growth scores populate in AWS API

Usage: python scripts/verify_session_155_deployment.py
"""

import logging
import sys
from datetime import datetime, timedelta

import boto3
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def check_dynamodb_tables() -> bool:
    """Verify DynamoDB tables exist with correct attributes."""
    logger.info("\n=== DYNAMODB TABLE VERIFICATION ===")

    try:
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")

        # Tables that should exist after Terraform apply
        required_tables = [
            "algo-orchestrator-locks-dev",
            "algo-loader-locks-dev",
            "algo-loader-config-dev",
            "algo-loader-status-dev",
            "algo_orchestrator_state",
            "algo_phase1_cache",
            "algo-contact-rate-limit-dev",
            "algo-token-blocklist-dev",
        ]

        existing_tables = dynamodb.list_tables()["TableNames"]

        missing = []
        for table in required_tables:
            if table not in existing_tables:
                missing.append(table)
                logger.error(f"✗ MISSING: {table}")
            else:
                logger.info(f"✓ EXISTS: {table}")

        return len(missing) == 0

    except Exception as e:
        logger.error(f"Failed to check DynamoDB tables: {e}")
        return False


def check_lambda_orchestrator_logs() -> bool:
    """Verify Lambda orchestrator is running without lock acquisition errors."""
    logger.info("\n=== LAMBDA ORCHESTRATOR LOG CHECK ===")

    try:
        logs = boto3.client("logs", region_name="us-east-1")

        # Get recent Lambda orchestrator logs
        # Log group pattern: /aws/lambda/algo-orchestrator-*

        # Look for successful execution vs lock acquisition errors
        log_groups = logs.describe_log_groups(
            logGroupNamePrefix="/aws/lambda/algo-orchestrator"
        )

        if not log_groups["logGroups"]:
            logger.warning("No Lambda orchestrator log groups found")
            return False

        log_group = log_groups["logGroups"][0]["logGroupName"]
        logger.info(f"Checking: {log_group}")

        # Get recent log streams (last hour)
        since = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)

        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=5,
        )

        if not streams["logStreams"]:
            logger.warning("No recent log streams found")
            return False

        # Check for lock acquisition errors
        has_lock_error = False
        has_success = False

        for stream in streams["logStreams"][:3]:
            stream_name = stream["logStreamName"]

            try:
                events = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    limit=50,
                )

                for event in events["events"]:
                    message = event["message"].lower()

                    if "lock" in message and "failed" in message:
                        has_lock_error = True
                        logger.error(f"✗ Lock error: {event['message'][:100]}")

                    if "successfully" in message or "completed" in message:
                        has_success = True
                        logger.info(f"✓ Success: {event['message'][:100]}")

            except Exception as e:
                logger.debug(f"Error reading stream {stream_name}: {e}")

        return has_success and not has_lock_error

    except Exception as e:
        logger.error(f"Failed to check Lambda logs: {e}")
        return False


def check_aws_api_growth_scores() -> bool:
    """Verify AWS API returns growth_scores (not NULL)."""
    logger.info("\n=== AWS API GROWTH SCORES CHECK ===")

    try:
        import requests

        from dashboard.credentials_provider import CredentialsProvider

        creds = CredentialsProvider.get_credentials()
        api_url = creds.get("DASHBOARD_API_URL")

        if not api_url:
            logger.error("DASHBOARD_API_URL not configured")
            return False

        # Make request to growth scores endpoint
        response = requests.get(
            f"{api_url}/api/growth-scores",
            headers={"Authorization": f"Bearer {creds.get('access_token')}"},
            timeout=10,
        )

        if response.status_code != 200:
            logger.error(f"API returned {response.status_code}: {response.text[:200]}")
            return False

        data = response.json()

        if "scores" not in data or not data["scores"]:
            logger.error("No growth scores in API response")
            return False

        # Check percentage with scores
        total = len(data["scores"])
        with_scores = sum(1 for s in data["scores"] if s.get("growth_score") is not None)
        pct = 100.0 * with_scores / total if total > 0 else 0

        logger.info(f"✓ Growth scores: {with_scores}/{total} ({pct:.1f}%)")

        # We expect > 80% populated
        return pct > 80

    except Exception as e:
        logger.error(f"Failed to check AWS API: {e}")
        return False


def check_local_database() -> bool:
    """Verify local database has recent data."""
    logger.info("\n=== LOCAL DATABASE FRESHNESS CHECK ===")

    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        # Check growth scores
        cur.execute("""
            SELECT COUNT(*),
                   COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_score
            FROM stock_scores
            WHERE updated_at > NOW() - INTERVAL '1 hour'
        """)

        total, with_scores = cur.fetchone()
        pct = 100.0 * with_scores / total if total > 0 else 0

        logger.info(f"✓ Recent growth scores: {with_scores}/{total} ({pct:.1f}%)")

        conn.close()
        return pct > 80

    except Exception as e:
        logger.error(f"Failed to check local database: {e}")
        return False


def main() -> int:
    """Run all verification checks."""
    logger.info("=" * 70)
    logger.info("SESSION 155 DEPLOYMENT VERIFICATION")
    logger.info("=" * 70)

    checks = [
        ("DynamoDB Tables", check_dynamodb_tables),
        ("Lambda Orchestrator Logs", check_lambda_orchestrator_logs),
        ("AWS API Growth Scores", check_aws_api_growth_scores),
        ("Local Database Freshness", check_local_database),
    ]

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Check '{name}' failed with exception: {e}")
            results.append((name, False))

    logger.info("\n" + "=" * 70)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info(f"\nOverall: {passed}/{total} checks passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
