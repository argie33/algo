#!/usr/bin/env python3
"""
Pre-commit hook: Check secrets freshness and validity.

Prevents committing code when:
1. Secrets are stale (not rotated recently)
2. Required secrets are missing
3. Duplicate secrets exist
4. Credential loading fails

Exit codes:
  0: All checks pass
  1: One or more checks fail
"""

import datetime
import subprocess
import sys

# Fix Windows encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Configuration
REQUIRED_SECRETS = [
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "JWT_SECRET",
    "FRED_API_KEY",
    "AWS_ACCOUNT_ID",
    "AWS_GITHUB_ACTIONS_ROLE_ARN",
    "DB_PASSWORD",
    "DB_USER",
    "DB_NAME",
]

DUPLICATE_PAIRS = [
    ("ALPACA_API_KEY", "ALPACA_API_KEY_ID"),
    ("ALPACA_SECRET_KEY", "ALPACA_API_SECRET_KEY"),
]

ROTATION_THRESHOLD_DAYS = 90
REPO = "argie33/algo"


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Run command and return (code, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check_required_secrets() -> tuple[bool, str]:
    returncode, stdout, stderr = run_cmd(["gh", "secret", "list", "--repo", REPO])

    if returncode != 0:
        return False, f"Failed to list secrets: {stderr}"

    found = {line.split("\t")[0] for line in stdout.split("\n") if line.strip()}
    missing = [s for s in REQUIRED_SECRETS if s not in found]

    if missing:
        return False, f"Missing required secrets: {missing}"

    return True, f"✓ All {len(REQUIRED_SECRETS)} required secrets present"


def check_no_duplicates() -> tuple[bool, str]:
    returncode, stdout, _stderr = run_cmd(["gh", "secret", "list", "--repo", REPO])

    if returncode != 0:
        return True, "Could not check duplicates (skipping)"

    found = {line.split("\t")[0] for line in stdout.split("\n") if line.strip()}
    duplicates = []

    for old, new in DUPLICATE_PAIRS:
        if old in found and new in found:
            duplicates.append(f"{old} (old) vs {new} (new)")

    if duplicates:
        return False, f"Duplicate secrets found: {duplicates}"

    return True, "✓ No duplicate secrets"


def check_secrets_freshness() -> tuple[bool, str]:
    returncode, stdout, _stderr = run_cmd(["gh", "secret", "list", "--repo", REPO])

    if returncode != 0:
        return True, "Could not check freshness (skipping)"

    now = datetime.datetime.now(datetime.timezone.utc)
    stale_secrets = []

    for line in stdout.split("\n"):
        if not line.strip():
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        name = parts[0]
        updated_str = parts[1]

        # Skip known long-lived secrets (static config)
        if name in ["DB_NAME", "DB_USER", "AWS_ACCOUNT_ID", "API_GATEWAY_URL"]:
            continue

        try:
            updated_dt = datetime.datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            age_days = (now - updated_dt).days

            if age_days > ROTATION_THRESHOLD_DAYS:
                stale_secrets.append((name, age_days))
        except Exception:
            pass  # Skip parsing errors

    if stale_secrets:
        msg = "Stale secrets found (not rotated in > 90 days):\n"
        for name, age in stale_secrets:
            msg += f"  - {name}: {age} days old\n"
        msg += "Run: python3 scripts/rotate_secrets_automated.py --rotate-aws"
        return False, msg

    return True, "✓ All secrets recently rotated"


def check_credential_loading() -> tuple[bool, str]:
    try:
        from config.credential_manager import get_credential_manager

        mgr = get_credential_manager()

        # Test key credentials
        try:
            mgr.get_db_credentials()
        except Exception as e:
            return False, f"Database credentials cannot be loaded: {e}"

        try:
            mgr.get_alpaca_credentials()
        except Exception:
            # OK if Alpaca not available (paper trading optional)
            pass

        return True, "✓ Credentials can be loaded"
    except ImportError:
        return True, "Could not check credential loading (skipping)"


def main() -> int:
    """Run all checks."""
    print("=" * 80)
    print("PRE-COMMIT: Checking secrets freshness & validity")
    print("=" * 80)

    checks = [
        ("Required Secrets", check_required_secrets),
        ("No Duplicates", check_no_duplicates),
        ("Secrets Freshness", check_secrets_freshness),
        ("Credential Loading", check_credential_loading),
    ]

    failed = []

    for check_name, check_fn in checks:
        try:
            success, message = check_fn()
            status = "✓" if success else "✗"
            print(f"{status} {check_name}: {message}")

            if not success:
                failed.append(check_name)
        except Exception as e:
            print(f"✗ {check_name}: Unexpected error: {e}")
            failed.append(check_name)

    print("=" * 80)

    if failed:
        print(f"✗ FAILED: {len(failed)} check(s) failed")
        print("\nFix these issues before committing:")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print("✓ All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
