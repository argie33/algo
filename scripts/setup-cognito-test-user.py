#!/usr/bin/env python3
"""Setup or reset Cognito test user for dashboard testing."""

import sys
import os
import json
import boto3
from botocore.exceptions import ClientError


def setup_test_user():
    """Create or reset Cognito test user."""

    # Get Cognito config from environment
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")
    test_email = os.environ.get(
        "COGNITO_TEST_USER_EMAIL", "edgebrookecapital@gmail.com"
    )
    test_password = os.environ.get("COGNITO_TEST_USER_PASSWORD", "TestPassword123!")

    if not (user_pool_id and client_id):
        print(
            "[ERROR] Cognito not configured. Set COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID"
        )
        return False

    try:
        cognito = boto3.client("cognito-idp", region_name="us-east-1")

        # Try to delete existing user
        print(f"[1/3] Checking for existing user: {test_email}...")
        try:
            cognito.admin_delete_user(UserPoolId=user_pool_id, Username=test_email)
            print("  [OK] Deleted existing user")
        except cognito.exceptions.UserNotFoundException:
            print("  [OK] No existing user found")
        except Exception as e:
            print(f"  [WARNING] Could not delete user: {e}")

        # Create new user
        print(f"[2/3] Creating test user: {test_email}...")
        try:
            cognito.admin_create_user(
                UserPoolId=user_pool_id,
                Username=test_email,
                TemporaryPassword=test_password,
                MessageAction="SUPPRESS",  # Don't send welcome email
            )
            print("  [OK] User created")
        except ClientError as e:
            if e.response["Error"]["Code"] == "UsernameExistsException":
                print("  [OK] User already exists")
            else:
                raise

        # Set permanent password
        print("[3/3] Setting permanent password...")
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=test_email,
            Password=test_password,
            Permanent=True,
        )
        print("  [OK] Password set")

        # Verify user can authenticate
        print("\n[Verification] Testing authentication...")
        auth_response = cognito.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": test_email, "PASSWORD": test_password},
        )

        if auth_response.get("AuthenticationResult", {}).get("AccessToken"):
            print("  [OK] Authentication successful")
            print("\nTest user ready:")
            print(f"  Email: {test_email}")
            print(f"  Password: {test_password}")
            print("\nTo use with dashboard:")
            print(f"  $env:COGNITO_USERNAME = '{test_email}'")
            print(f"  $env:COGNITO_PASSWORD = '{test_password}'")
            print("  python tools/dashboard/dashboard.py")

            # Save to cache file for convenience
            cache_file = os.path.expanduser("~/.algo/cognito_credentials.json")
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump({"username": test_email, "password": test_password}, f)
            print(f"\n  Cached to: {cache_file}")
            return True
        else:
            print("  [ERROR] Authentication test failed")
            return False

    except ClientError as e:
        print(f"[ERROR] AWS Cognito error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Set env vars from Terraform if not already set
    if not os.environ.get("COGNITO_USER_POOL_ID"):
        try:
            import subprocess

            api_url = (
                subprocess.check_output(
                    ["terraform", "output", "-raw", "api_url"],
                    cwd="terraform",
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            user_pool_id = (
                subprocess.check_output(
                    ["terraform", "output", "-raw", "cognito_user_pool_id"],
                    cwd="terraform",
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            client_id = (
                subprocess.check_output(
                    ["terraform", "output", "-raw", "cognito_user_pool_client_id"],
                    cwd="terraform",
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )

            os.environ["COGNITO_USER_POOL_ID"] = user_pool_id
            os.environ["COGNITO_CLIENT_ID"] = client_id
        except Exception as e:
            print(f"[WARNING] Could not auto-load Terraform outputs: {e}")
            sys.exit(1)

    if setup_test_user():
        sys.exit(0)
    else:
        sys.exit(1)
