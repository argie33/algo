#!/usr/bin/env python3
"""Diagnose and clear stale DynamoDB orchestrator lock."""
import os
import sys
from datetime import datetime


def check_and_clear_lock():
    """Check and optionally clear stale DynamoDB orchestrator lock."""
    try:
        import boto3
    except ImportError:
        print("[ERROR] boto3 not available")
        return False

    try:
        # Get lock table name from environment or use default
        lock_table = os.getenv(
            "ORCHESTRATOR_LOCK_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-orchestrator-locks-dev"
        )

        print(f"[INFO] Checking lock table: {lock_table}")

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.Table(lock_table)

        # Get current lock status
        response = table.get_item(Key={"lock_key": "orchestrator-run-lock"})

        if "Item" not in response:
            print("[OK] No lock found - orchestrator can execute")
            return True

        item = response["Item"]
        lock_id = item.get("lock_id", "unknown")
        acquired_at = item.get("acquired_at", "unknown")
        expires_at = item.get("expires_at", "unknown")

        print("\n[WARN] Lock detected:")
        print(f"  Lock ID: {lock_id}")
        print(f"  Acquired: {acquired_at}")
        print(f"  Expires: {expires_at}")

        # Check if lock is expired
        try:
            expiry_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=expiry_time.tzinfo) if expiry_time.tzinfo else datetime.utcnow()

            # Remove timezone for comparison if needed
            if expiry_time.tzinfo:
                expiry_time = expiry_time.replace(tzinfo=None)
            now = datetime.utcnow()

            seconds_until_expiry = (expiry_time - now).total_seconds()

            if seconds_until_expiry > 0:
                print(f"  Time until expiry: {int(seconds_until_expiry)} seconds (~{int(seconds_until_expiry/60)} minutes)")
                print("\n[WARN] Lock is still valid. Options:")
                print(f"  1. Wait {int(seconds_until_expiry/60) + 1} minutes for automatic expiry")
                print("  2. Run with --force to immediately clear stale lock")
                return False
            else:
                print(f"  Lock is EXPIRED by {int(-seconds_until_expiry)} seconds - clearing...")
                table.delete_item(Key={"lock_key": "orchestrator-run-lock"})
                print("[OK] Cleared expired lock")
                return True

        except ValueError as e:
            print(f"  Could not parse expiry time: {e}")
            return False

    except Exception as e:
        print(f"[ERROR] Failed to check lock: {e}")
        return False

def force_clear_lock():
    """Force clear the orchestrator lock."""
    try:
        import boto3
    except ImportError:
        print("[ERROR] boto3 not available")
        return False

    try:
        lock_table = os.getenv(
            "ORCHESTRATOR_LOCK_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-orchestrator-locks-dev"
        )

        print(f"[INFO] Force clearing lock from: {lock_table}")

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.Table(lock_table)

        # Get current lock to show what we're clearing
        response = table.get_item(Key={"lock_key": "orchestrator-run-lock"})
        if "Item" in response:
            item = response["Item"]
            print("[WARN] Clearing lock:")
            print(f"  Lock ID: {item.get('lock_id', 'unknown')}")
            print(f"  Acquired: {item.get('acquired_at', 'unknown')}")
            print(f"  Expires: {item.get('expires_at', 'unknown')}")

        # Force delete
        table.delete_item(Key={"lock_key": "orchestrator-run-lock"})
        print("[OK] Lock cleared - orchestrator can execute now")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to clear lock: {e}")
        return False

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage DynamoDB orchestrator lock")
    parser.add_argument("--force", action="store_true", help="Force clear lock immediately")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("ORCHESTRATOR LOCK MANAGER")
    print("="*60 + "\n")

    if args.force:
        success = force_clear_lock()
    else:
        success = check_and_clear_lock()

    print()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
