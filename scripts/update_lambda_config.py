#!/usr/bin/env python3
"""Update API Lambda configuration with proper environment variable escaping."""

import json
import subprocess
import sys
import os

def update_lambda_config(func_name, region, db_host, db_port, db_name, db_user, db_password, allowed_origins, cognito_region, layer_arn):
    """Update Lambda function configuration with environment variables."""

    config = {
        "FunctionName": func_name,
        "Environment": {
            "Variables": {
                "DB_HOST": db_host,
                "DB_PORT": db_port,
                "DB_NAME": db_name,
                "DB_USER": db_user,
                "DB_PASSWORD": db_password,
                "DB_SSL": "prefer",
                "ALLOWED_ORIGINS": allowed_origins,
                "COGNITO_REGION": cognito_region
            }
        },
        "Timeout": 300,
        "Layers": [layer_arn]
    }

    config_json = json.dumps(config)

    try:
        result = subprocess.run([
            'aws', 'lambda', 'update-function-configuration',
            '--cli-input-json', config_json,
            '--region', region
        ], check=True, capture_output=True, text=True)

        print("API Lambda configuration updated successfully")
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
