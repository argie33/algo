#!/usr/bin/env python3
"""Update API Lambda configuration with proper environment variable escaping."""

import json
import subprocess
import sys
import os

def update_lambda_config(func_name, region, db_host, db_port, db_name, db_user, db_password, allowed_origins, cognito_region, layer_arn):
    """Update Lambda function configuration with environment variables.

    Reads existing environment first, merges new vars, then updates.
    This preserves Cognito and other vars set by Terraform.
    """

    # Step 1: Get existing function configuration to preserve existing env vars
    try:
        result = subprocess.run([
            'aws', 'lambda', 'get-function-configuration',
            '--function-name', func_name,
            '--region', region
        ], check=True, capture_output=True, text=True)

        existing_config = json.loads(result.stdout)
        existing_vars = existing_config.get('Environment', {}).get('Variables', {})
        print(f"Retrieved existing config with {len(existing_vars)} env vars")
    except Exception as e:
        print(f"Warning: Could not retrieve existing config: {e}", file=sys.stderr)
        existing_vars = {}

    # Step 2: Build merged environment variables (keep existing + update with new)
    merged_vars = existing_vars.copy()
    merged_vars.update({
        "DB_HOST": db_host,
        "DB_PORT": db_port,
        "DB_NAME": db_name,
        "DB_USER": db_user,
        "DB_PASSWORD": db_password,
        "DB_SSL": "prefer",
        "ALLOWED_ORIGINS": allowed_origins,
    })

    # Step 3: Build update config with merged vars
    config = {
        "FunctionName": func_name,
        "Environment": {
            "Variables": merged_vars
        },
        "Timeout": 300,
        "Layers": [layer_arn] if layer_arn else []
    }

    config_json = json.dumps(config)

    try:
        result = subprocess.run([
            'aws', 'lambda', 'update-function-configuration',
            '--cli-input-json', config_json,
            '--region', region
        ], check=True, capture_output=True, text=True)

        print("API Lambda configuration updated successfully")
        print(f"Updated {len(merged_vars)} environment variables")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error updating Lambda: {e.stderr}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 10:
        print("Usage: update_lambda_config.py FUNC REGION DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD ALLOWED_ORIGINS COGNITO_REGION LAYER_ARN", file=sys.stderr)
        sys.exit(1)

    func_name = sys.argv[1]
    region = sys.argv[2]
    db_host = sys.argv[3]
    db_port = sys.argv[4]
    db_name = sys.argv[5]
    db_user = sys.argv[6]
    db_password = sys.argv[7]
    allowed_origins = sys.argv[8]
    cognito_region = sys.argv[9]
    layer_arn = sys.argv[10] if len(sys.argv) > 10 else ""

    sys.exit(update_lambda_config(func_name, region, db_host, db_port, db_name, db_user, db_password, allowed_origins, cognito_region, layer_arn))
