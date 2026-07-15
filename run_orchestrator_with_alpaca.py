#!/usr/bin/env python3
"""
Wrapper script to run orchestrator with Alpaca credentials from AWS Secrets Manager.

This loads credentials from Secrets Manager and injects them into the subprocess
environment, bypassing Windows env var inheritance issues.

Usage:
    python3 run_orchestrator_with_alpaca.py --morning
    python3 run_orchestrator_with_alpaca.py --afternoon
    python3 run_orchestrator_with_alpaca.py --evening
"""

import json
import os
import subprocess
import sys


def load_alpaca_credentials():
    """Load Alpaca credentials from AWS Secrets Manager."""
    try:
        import boto3

        client = boto3.client("secretsmanager", region_name="us-east-1")
        response = client.get_secret_value(SecretId="algo/alpaca")
        secret_string = response.get("SecretString")

        if not secret_string:
            raise ValueError("Secret exists but contains no SecretString")

        credentials = json.loads(secret_string)
        return {
            "APCA_API_KEY_ID": credentials.get("APCA_API_KEY_ID"),
            "APCA_API_SECRET_KEY": credentials.get("APCA_API_SECRET_KEY"),
            "APCA_API_BASE_URL": credentials.get("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"),
        }
    except Exception as e:
        print(f"ERROR: Failed to load Alpaca credentials from AWS Secrets Manager: {e}")
        raise


def run_orchestrator(args, alpaca_env):
    """Run orchestrator with Alpaca credentials injected into environment."""
    # Create environment with credentials
    env = os.environ.copy()
    env.update(alpaca_env)

    print("=" * 70)
    print("ORCHESTRATOR WITH ALPACA CREDENTIALS")
    print("=" * 70)
    print("Credentials loaded from: AWS Secrets Manager (algo/alpaca)")
    print(f"  APCA_API_KEY_ID: {alpaca_env['APCA_API_KEY_ID'][:15]}...")
    print(f"  APCA_API_SECRET_KEY: (set, {len(alpaca_env['APCA_API_SECRET_KEY'])} chars)")
    print(f"  APCA_API_BASE_URL: {alpaca_env['APCA_API_BASE_URL']}")
    print("")
    print(f"Running: python3 scripts/run_local_orchestrator.py {' '.join(args)}")
    print("=" * 70)
    print("")

    # Run orchestrator subprocess with credentials in environment
    result = subprocess.run(
        ["python3", "scripts/run_local_orchestrator.py"] + args,
        env=env,
    )

    return result.returncode


if __name__ == "__main__":
    try:
        # Load credentials from Secrets Manager
        print("Loading Alpaca credentials from AWS Secrets Manager...")
        alpaca_env = load_alpaca_credentials()

        # Run orchestrator with those credentials
        exit_code = run_orchestrator(sys.argv[1:], alpaca_env)
        sys.exit(exit_code)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
