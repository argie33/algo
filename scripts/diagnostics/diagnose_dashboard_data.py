#!/usr/bin/env python3
"""Diagnose why dashboard shows data_unavailable for all panels."""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def check_api_endpoints():
    """Check which API endpoints are defined and what they return."""
    print("\n=== API ENDPOINT ANALYSIS ===")

    try:
        # Import from lambda package (use sys.path trick to avoid reserved keyword issues)
        import importlib.util
        spec = importlib.util.find_spec("lambda.api.shared_contracts.dashboard_api_contract")
        if spec is None:
            # Try direct import path
            sys.path.insert(0, str(Path(__file__).parent / "lambda" / "api" / "shared_contracts"))
            from dashboard_api_contract import DASHBOARD_ENDPOINTS
        else:
            from lambda.api.shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS

        print(f"✓ Found {len(DASHBOARD_ENDPOINTS)} dashboard endpoints defined:")
        for key, endpoint in list(DASHBOARD_ENDPOINTS.items())[:5]:
            print(f"  - {key}: {endpoint.get('path', 'N/A')}")
    except Exception as e:
        print(f"✗ Could not load dashboard endpoints: {e}")
        return False

    return True


def check_database_connection():
    """Check if we can connect to the database."""
    print("\n=== DATABASE CONNECTION ===")

    try:
        from utils.db import DatabaseContext
        db = DatabaseContext("read")

        # Try a simple query
        with db.execute("SELECT 1 as health_check") as result:
            if result.fetchone():
                print("✓ Database connection successful")
                return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


def check_api_data_sources():
    """Check what API data sources exist and if they have data."""
    print("\n=== API DATA SOURCES ===")

    try:
        from utils.db import DatabaseContext
        db = DatabaseContext("read")

        # Check key tables that the API uses
        tables_to_check = [
            ("algo_trades", "Open trades"),
            ("algo_positions_with_risk", "Positions view"),
            ("algo_portfolio_snapshots", "Portfolio snapshots"),
            ("stock_scores", "Stock scores"),
            ("algo_signals", "Trading signals"),
            ("orchestrator_execution_log", "Orchestrator runs"),
        ]

        for table, desc in tables_to_check:
            try:
                query = f"SELECT COUNT(*) as cnt FROM {table} LIMIT 1"
                with db.execute(query) as result:
                    row = result.fetchone()
                    count = row[0] if row else 0
                    print(f"✓ {table}: {count} records ({desc})")
            except Exception as e:
                print(f"✗ {table}: Error - {str(e)[:60]}")

    except Exception as e:
        print(f"✗ Could not check data sources: {e}")
        return False

    return True


def check_dashboard_config():
    """Check dashboard configuration."""
    print("\n=== DASHBOARD CONFIGURATION ===")

    api_url = os.environ.get("DASHBOARD_API_URL", "NOT SET")
    print(f"DASHBOARD_API_URL: {api_url}")

    if api_url == "NOT SET":
        print("  → Set this to your AWS API Gateway URL for AWS mode")
        print("  → Or use --local flag to connect to localhost:3001")

    local_mode = "--local" in sys.argv
    print(f"Local mode: {local_mode}")


def check_aws_credentials():
    """Check AWS credential status."""
    print("\n=== AWS CREDENTIALS ===")

    try:
        import boto3
        from botocore.exceptions import ClientError

        # Try to get caller identity
        iam = boto3.client("iam", region_name="us-east-1")
        try:
            response = iam.get_user()
            user = response["User"]["UserName"]
            print(f"✓ AWS credentials valid, user: {user}")
            return True
        except ClientError as e:
            if "not authorized" in str(e).lower():
                print(f"✗ AWS credentials present but lacking permissions: {str(e)[:100]}")
                return False
            raise
    except Exception as e:
        print(f"✗ AWS credentials error: {e}")
        return False


def main():
    print("=" * 60)
    print("DASHBOARD DATA AVAILABILITY DIAGNOSTIC")
    print("=" * 60)

    results = {
        "api_endpoints": check_api_endpoints(),
        "database": check_database_connection(),
        "data_sources": check_api_data_sources(),
        "aws_credentials": check_aws_credentials(),
    }

    check_dashboard_config()

    print("\n=== SUMMARY ===")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Checks passed: {passed}/{total}")

    if not results.get("database"):
        print("\n🚨 CRITICAL: Database connection failed - API cannot fetch data")

    if not results.get("aws_credentials"):
        print("\n⚠️  WARNING: AWS credentials have permission issues")

    print("\nNext steps:")
    print("1. If database failed: Check DATABASE_URL and credentials")
    print("2. If AWS credentials failed: Check IAM permissions for lambda:ListFunctions")
    print("3. To test dashboard locally: python -m dashboard --local")
    print("4. To test dashboard with AWS: Set DASHBOARD_API_URL and run: python -m dashboard")


if __name__ == "__main__":
    main()
