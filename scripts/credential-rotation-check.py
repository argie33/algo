#!/usr/bin/env python3
"""Credential rotation status checker for CI/CD pipelines."""

import json
import sys
from datetime import datetime, timezone

import boto3


class CredentialRotationChecker:
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.secretsmanager = boto3.client("secretsmanager", region_name=region)

    def get_credential_status(self) -> dict | None:
        """Retrieve credential status from Secrets Manager."""
        try:
            response = self.secretsmanager.get_secret_value(SecretId="algo/developer-credentials")
            secret_string = response["SecretString"]
            return json.loads(secret_string) if isinstance(secret_string, str) else None
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse credential status JSON: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(
                f"ERROR: Could not retrieve credentials from Secrets Manager: {e}",
                file=sys.stderr,
            )
            raise

    def check_grace_period(self, creds: dict) -> tuple[bool, str]:
        """Check if grace period is active and return status."""
        status = creds.get("status")

        if status == "dual_credentials_active":
            cleanup_date_str = creds.get("old_key_cleanup_date")
            if not cleanup_date_str:
                return False, "ERROR: No cleanup date in dual_credentials state"

            cleanup_date = datetime.strptime(cleanup_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)

            if now >= cleanup_date:
                return (
                    False,
                    f"GRACE_PERIOD_EXPIRED: Cleanup should have occurred on {cleanup_date_str}",
                )

            days_remaining = (cleanup_date - now).days
            return (
                True,
                f"GRACE_PERIOD_ACTIVE: Update by {cleanup_date_str} ({days_remaining} days remaining)",
            )

        elif status == "active":
            return True, "NORMAL: No rotation in progress"

        else:
            return False, f"UNKNOWN_STATUS: {status}"

    def check_credentials_up_to_date(self) -> tuple[bool, str]:
        """Check if local credentials are up to date (best-effort check)."""
        try:
            sts = boto3.client("sts")
            identity = sts.get_caller_identity()

            # Successfully authenticated
            account = identity.get("Account")
            return True, f"Credentials are valid (Account: {account})"
        except Exception as e:
            return False, f"Credentials are INVALID: {e!s}"

    def get_rotation_timeline(self, creds: dict) -> dict:
        """Extract rotation timeline information."""
        return {
            "rotation_date": creds.get("rotation_date"),
            "cleanup_date": creds.get("old_key_cleanup_date") or creds.get("cleanup_date"),
            "grace_period_days": creds.get("grace_period_days", 7),
            "status": creds.get("status"),
        }

    def run_checks(self) -> int:
        """Run all checks and return exit code (0=all good, 1=action needed, 2=error)."""
        creds = self.get_credential_status()
        if not creds:
            return 2

        # Check status
        in_grace_period, grace_msg = self.check_grace_period(creds)
        print(f"[GRACE PERIOD] {grace_msg}")

        # Check credentials
        valid, cred_msg = self.check_credentials_up_to_date()
        print(f"[CREDENTIALS] {cred_msg}")

        # Show timeline
        timeline = self.get_rotation_timeline(creds)
        if timeline["status"] == "dual_credentials_active":
            print(f"[TIMELINE] Rotation: {timeline['rotation_date']} | Cleanup: {timeline['cleanup_date']}")

        # Determine exit code
        if not valid:
            print("\n❌ FAILED: Local credentials are not valid. Run 'scripts/refresh-aws-credentials.ps1'")
            return 1

        if not in_grace_period and timeline["status"] == "dual_credentials_active":
            print("\n⚠️  WARNING: Grace period has expired. Old credentials are no longer valid.")
            print("             Run 'scripts/refresh-aws-credentials.ps1' immediately.")
            return 1

        if in_grace_period and timeline["status"] == "dual_credentials_active":
            cleanup_date = timeline["cleanup_date"]
            print(f"\n⚠️  ACTION NEEDED: Update your credentials before {cleanup_date}")
            print("             Run 'scripts/refresh-aws-credentials.ps1' to update now.")
            return 1

        print("\n✓ OK: Credentials are up to date")
        return 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Check credential rotation status")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--quiet", action="store_true", help="Only output exit code, no messages")
    args = parser.parse_args()

    checker = CredentialRotationChecker(region=args.region)
    exit_code = checker.run_checks()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
