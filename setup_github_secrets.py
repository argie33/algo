#!/usr/bin/env python3
"""
Automatically configure GitHub secrets via API
No need to manually go to GitHub Settings
"""

import requests
import json
import sys
import subprocess
from pathlib import Path

def get_github_token():
    """Get GitHub token from user"""
    print("\n" + "="*80)
    print("GITHUB SECRET SETUP - VIA API")
    print("="*80)
    print("\nTo set secrets automatically, you need a GitHub Personal Access Token.")
    print("\nCreate one at: https://github.com/settings/tokens")
    print("  - Click 'Generate new token (classic)'")
    print("  - Scopes needed: repo (full control)")
    print("  - Copy the token")
    print("\nPaste your GitHub token:")

    token = input("> ").strip()

    if not token:
        print("ERROR: No token provided")
        sys.exit(1)

    return token

def get_repo_info():
    """Get repository owner and name from git remote"""
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True
        ).strip()

        # Extract owner/repo from URL
        # Format: https://github.com/owner/repo.git or git@github.com:owner/repo.git
        if "github.com" in remote_url:
            parts = remote_url.replace("git@github.com:", "https://github.com/").replace(".git", "").split("/")
            owner = parts[-2]
            repo = parts[-1]
            return owner, repo
    except:
        pass

    print("ERROR: Could not detect GitHub repository")
    print("Make sure you're in a git repository with origin remote set to GitHub")
    sys.exit(1)

def get_aws_account_id():
    """Get AWS account ID from user"""
    print("\nEnter your AWS Account ID (12-digit number):")
    print("(This was shown by the SETUP_EVERYTHING.sh script)")

    account_id = input("> ").strip()

    if not account_id or len(account_id) != 12 or not account_id.isdigit():
        print("ERROR: Invalid AWS Account ID")
        sys.exit(1)

    return account_id

def get_db_credentials():
    """Get database credentials from user"""
    print("\nEnter RDS Username (default: stocks):")
    username = input("> ").strip() or "stocks"

    print("\nEnter RDS Password:")
    password = input("> ").strip()

    if not password:
        print("ERROR: Password required")
        sys.exit(1)

    return username, password

def set_secret(token, owner, repo, secret_name, secret_value):
    """Set a single secret via GitHub API"""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # Get public key for encryption
    public_key_url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    key_response = requests.get(public_key_url, headers=headers)

    if key_response.status_code != 200:
        print(f"ERROR: Could not get public key: {key_response.text}")
        return False

    key_data = key_response.json()
    public_key = key_data["key"]
    key_id = key_data["key_id"]

    # Encrypt the secret
    try:
        from nacl import pwhash, secret, utils
        from nacl.public import PublicKey
        import base64

        public_key_obj = PublicKey(public_key.encode(), encoder=base64.b64_encode)
        sealed_box = secret.SealedBox(public_key_obj)
        encrypted = sealed_box.encrypt(secret_value.encode())
        encoded_secret = base64.b64encode(encrypted.ciphertext).decode()
    except ImportError:
        print("ERROR: PyNaCl not installed")
        print("Install: pip install pynacl")
        sys.exit(1)

    # Set the secret
    data = {
        "encrypted_value": encoded_secret,
        "key_id": key_id
    }

    response = requests.put(url, headers=headers, json=data)

    if response.status_code in [201, 204]:
        return True
    else:
        print(f"ERROR setting {secret_name}: {response.text}")
        return False

def main():
    print("\nCollecting information...")

    # Get inputs
    token = get_github_token()
    owner, repo = get_repo_info()
    aws_account_id = get_aws_account_id()
    db_username, db_password = get_db_credentials()

    print(f"\nRepository: {owner}/{repo}")
    print(f"AWS Account: {aws_account_id}")
    print(f"DB Username: {db_username}")

    print("\n" + "="*80)
    print("Setting GitHub Secrets...")
    print("="*80 + "\n")

    secrets = {
        "AWS_ACCOUNT_ID": aws_account_id,
        "RDS_USERNAME": db_username,
        "RDS_PASSWORD": db_password
    }

    all_success = True
    for secret_name, secret_value in secrets.items():
        print(f"Setting {secret_name}...", end=" ", flush=True)
        if set_secret(token, owner, repo, secret_name, secret_value):
            print("✓ OK")
        else:
            print("✗ FAILED")
            all_success = False

    print("\n" + "="*80)

    if all_success:
        print("SUCCESS! All secrets configured.")
        print("="*80)
        print("\nNext step: Deploy")
        print("  git push origin main")
        print("\nGitHub Actions will automatically deploy everything.")
        return 0
    else:
        print("FAILED: Some secrets could not be set")
        print("="*80)
        print("\nTroubleshoot:")
        print("  1. Verify GitHub token is valid")
        print("  2. Verify token has 'repo' scope")
        print("  3. Check GitHub API status: https://www.githubstatus.com")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        sys.exit(1)
