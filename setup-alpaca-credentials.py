#!/usr/bin/env python3
"""
Setup Alpaca API credentials in AWS Secrets Manager.

Alpaca data (historical OHLCV) is already the primary source in data_source_router.py.
This script populates the credentials so the loader can actually use it.

USAGE:
    python3 setup-alpaca-credentials.py --api-key YOUR_KEY --api-secret YOUR_SECRET

Or with environment variables:
    export ALPACA_API_KEY_ID=pk_xxx
    export ALPACA_API_SECRET_KEY=sk_xxx
    python3 setup-alpaca-credentials.py

WHERE TO GET CREDENTIALS:
    1. Go to https://app.alpaca.markets/signup (paper trading account)
    2. Navigate to "API Keys" in account settings
    3. Generate a new "Paper Trading" API key
    4. Copy the API Key ID and Secret Key
    5. Run this script
"""

import argparse
import json
import os
import sys
import boto3


def main():
    parser = argparse.ArgumentParser(
        description="Setup Alpaca credentials in Secrets Manager"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ALPACA_API_KEY_ID"),
        help="Alpaca API Key ID (or set ALPACA_API_KEY_ID env var)",
    )
    parser.add_argument(
        "--api-secret",
        default=os.getenv("ALPACA_API_SECRET_KEY"),
        help="Alpaca API Secret Key (or set ALPACA_API_SECRET_KEY env var)",
    )
    parser.add_argument(
        "--api-base-url",
        default="https://paper-api.alpaca.markets",
        help="Alpaca API base URL (default: paper trading)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region",
    )
    parser.add_argument(
        "--secret-name",
        default="stocks-algo-secrets",
        help="Name of Secrets Manager secret (stack-qualified)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without actually updating",
    )
    args = parser.parse_args()

    if not args.api_key or not args.api_secret:
        print("Error: Alpaca API key and secret are required.")
        print("Provide via --api-key/--api-secret or ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY env vars.")
        return 1

    # Build secret payload
    secret_value = {
        "APCA_API_KEY_ID": args.api_key,
        "APCA_API_SECRET_KEY": args.api_secret,
        "APCA_API_BASE_URL": args.api_base_url,
        "ALPACA_PAPER_TRADING": "true",
    }

    print("Alpaca Credentials Setup")
    print("=" * 60)
    print(f"Region:      {args.region}")
    print(f"Secret Name: {args.secret_name}")
    print(f"API Base:    {args.api_base_url}")
    print(f"Paper Trade: true")
    print("=" * 60)

    if args.dry_run:
        print("[DRY RUN] Would update with:")
        print(json.dumps(secret_value, indent=2))
        return 0

    # Update Secrets Manager
    try:
        client = boto3.client("secretsmanager", region_name=args.region)

        # Try to update existing secret
        try:
            response = client.update_secret(
                SecretId=args.secret_name,
                SecretString=json.dumps(secret_value),
            )
            print(f"[OK] Updated existing secret: {response['ARN']}")
        except client.exceptions.ResourceNotFoundException:
            # Create new secret if it doesn't exist
            response = client.create_secret(
                Name=args.secret_name,
                Description="Alpaca API credentials for data loading",
                SecretString=json.dumps(secret_value),
            )
            print(f"[OK] Created new secret: {response['ARN']}")

        print("\nAlpaca credentials are now available to:")
        print("  · data_source_router.py (primary OHLCV source)")
        print("  · ECS loaders (loadpricedaily.py, etc.)")
        print("  · Lambda functions")
        print("\nVerify with:")
        print(f"  aws secretsmanager get-secret-value --secret-id {args.secret_name} --region {args.region}")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to update Secrets Manager: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
