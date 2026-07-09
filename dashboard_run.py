#!/usr/bin/env python3
"""Entry point for dashboard - run from project root as: python dashboard_run.py

Automatically fetches AWS API configuration from Terraform outputs.
Falls back to environment variables if Terraform is not available.
"""

import json
import os
import subprocess
import sys

def get_terraform_outputs() -> dict:
    """Fetch Terraform outputs from terraform directory."""
    try:
        terraform_dir = os.path.join(os.path.dirname(__file__), "terraform")
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            outputs = json.loads(result.stdout)
            return {
                "api_url": outputs.get("api_gateway_endpoint", {}).get("value"),
                "user_pool_id": outputs.get("cognito_user_pool_id", {}).get("value"),
                "client_id": outputs.get("cognito_user_pool_client_id", {}).get("value"),
            }
    except Exception as e:
        print(f"Note: Could not fetch Terraform outputs ({type(e).__name__})", file=sys.stderr)
    return {}

# Get configuration from Terraform or environment variables
terraform_config = get_terraform_outputs()
api_url = terraform_config.get("api_url") or os.environ.get("DASHBOARD_API_URL")
user_pool_id = terraform_config.get("user_pool_id") or os.environ.get("COGNITO_USER_POOL_ID")
client_id = terraform_config.get("client_id") or os.environ.get("COGNITO_CLIENT_ID")

# Set AWS configuration BEFORE any imports
if api_url:
    os.environ["DASHBOARD_API_URL"] = api_url
os.environ.setdefault("COGNITO_USER_POOL_ID", user_pool_id or "")
os.environ.setdefault("COGNITO_CLIENT_ID", client_id or "")
os.environ.setdefault("ENVIRONMENT", "dev")

# Add repo root to path to allow package imports
_repo_root = os.path.dirname(os.path.abspath(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Run the dashboard module
from dashboard.dashboard import main

if __name__ == "__main__":
    main()
