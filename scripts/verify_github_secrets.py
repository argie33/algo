#!/usr/bin/env python3
"""
Verify GitHub Secrets are properly configured for credential management.

This script checks that required secrets exist in GitHub and will be
available to Terraform during deployment.

REQUIRED SECRETS:
  - ALPACA_API_KEY_ID: Alpaca paper trading API key
  - ALPACA_API_SECRET_KEY: Alpaca paper trading secret key
  - JWT_SECRET: JWT token signing secret
  - FRED_API_KEY: Federal Reserve Economic Data API key
  - AWS_ACCOUNT_ID: AWS account ID for role assumption
  - GITHUB_ACTIONS_ROLE_NAME: IAM role for GitHub Actions

RUN: python scripts/verify_github_secrets.py
"""

import json
import os
import subprocess
import sys

REQUIRED_SECRETS = {
    "ALPACA_API_KEY_ID": "Alpaca API Key ID",
    "ALPACA_API_SECRET_KEY": "Alpaca API Secret Key",
    "JWT_SECRET": "JWT signing secret",
    "FRED_API_KEY": "FRED economic data API key",
    "AWS_ACCOUNT_ID": "AWS Account ID",
    "GITHUB_ACTIONS_ROLE_NAME": "GitHub Actions IAM Role Name",
}


def get_repo() -> str:
    """Auto-detect repo from git remote or use environment variable."""
    try:
        result = subprocess.run(
            ["git", "config", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
            cwd=os.getcwd(),
        )
        url = result.stdout.strip()
        # Extract owner/repo from git@github.com:owner/repo.git or https://github.com/owner/repo.git
        if "github.com" in url:
            if url.startswith("git@"):
                return url.split(":")[-1].replace(".git", "")
            else:
                return "/".join(url.split("/")[-2:]).replace(".git", "")
    except Exception:
        pass
    return os.getenv("GITHUB_REPO", "argie33/algo")


def get_github_secrets():
    try:
        repo = get_repo()
        result = subprocess.run(
            ["gh", "secret", "list", "-R", repo, "--json", "name"],
            capture_output=True,
            text=True,
            check=True,
        )
        secrets = json.loads(result.stdout)
        return {s["name"] for s in secrets}
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: Could not fetch GitHub secrets (gh CLI not installed or not authenticated)")
        print("  Install: https://cli.github.com")
        print("  Authenticate: gh auth login")
        return set()


def main():
    print("=" * 80)
    print("GITHUB SECRETS VERIFICATION")
    print("=" * 80)

    existing_secrets = get_github_secrets()

    if not existing_secrets:
        print("\nERROR: Could not connect to GitHub. Make sure:")
        print("  1. GitHub CLI (gh) is installed: https://cli.github.com")
        print("  2. You are authenticated: gh auth login")
        sys.exit(1)

    print(f"\nFound {len(existing_secrets)} secrets in GitHub\n")

    missing = []
    found = []

    for secret_name, description in REQUIRED_SECRETS.items():
        if secret_name in existing_secrets:
            print(f"  [OK] {secret_name:30} - {description}")
            found.append(secret_name)
        else:
            print(f"  [MISSING] {secret_name:30} - {description}")
            missing.append(secret_name)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Found: {len(found)}/{len(REQUIRED_SECRETS)}")
    print(f"Missing: {len(missing)}/{len(REQUIRED_SECRETS)}")

    if missing:
        repo = get_repo()
        print(f"\nCRITICAL: {len(missing)} secrets missing. Set them in GitHub before deployment:")
        print(f"\nhttps://github.com/{repo}/settings/secrets/actions")
        print("\nRequired secrets to add:")
        for secret in missing:
            print(f"  - {secret}: {REQUIRED_SECRETS[secret]}")
        print("\nCommand to set a secret:")
        print(f"  gh secret set SECRET_NAME -R {repo} < secret-value.txt")
        sys.exit(1)
    else:
        print("\n[SUCCESS] All required GitHub secrets are configured!")
        print("\nDeployment ready. Terraform will use these secrets during 'terraform apply'.")
        sys.exit(0)


if __name__ == "__main__":
    main()
