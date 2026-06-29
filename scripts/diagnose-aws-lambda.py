#!/usr/bin/env python3
"""
AWS Lambda Diagnostic Script

Run this to identify what's failing when Lambda tries to access Secrets Manager and database.
Outputs a checklist of what's working and what's broken.
"""
import json
import logging
import os
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_environment_variables():
    """Check if required AWS Lambda environment variables are set."""
    print("\n=== ENVIRONMENT VARIABLES ===")
    required_vars = [
        'AWS_REGION',
        'AWS_EXECUTION_ENV',
        'AWS_LAMBDA_FUNCTION_NAME',
        'DB_SECRET_ARN',
        'DB_HOST',
        'DB_PORT',
        'DB_NAME',
        'DB_USER',
    ]

    missing = []
    for var in required_vars:
        val = os.getenv(var)
        status = "✓ SET" if val else "✗ MISSING"
        print(f"  {var:30s} {status}")
        if not val:
            missing.append(var)

    return len(missing) == 0, missing


def check_boto3():
    """Check if boto3 is available."""
    print("\n=== BOTO3 ===")
    try:
        import boto3
        print(f"  ✓ boto3 available (version: {boto3.__version__})")
        return True
    except ImportError as e:
        print(f"  ✗ boto3 NOT available: {e}")
        return False


def check_secrets_manager_access():
    """Try to connect to Secrets Manager."""
    print("\n=== SECRETS MANAGER ACCESS ===")

    aws_region = os.getenv('AWS_REGION', 'us-east-1')
    secret_arn = os.getenv('DB_SECRET_ARN')

    if not secret_arn:
        print(f"  ✗ DB_SECRET_ARN not set - cannot test Secrets Manager access")
        return False

    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client('secretsmanager', region_name=aws_region)
        print(f"  Testing Secrets Manager in region: {aws_region}")
        print(f"  Attempting to fetch secret: {secret_arn}")

        try:
            response = client.get_secret_value(SecretId=secret_arn)
            secret_string = response.get('SecretString')

            if secret_string:
                try:
                    secret_data = json.loads(secret_string)
                    print(f"  ✓ Secret fetched and parsed successfully")
                    print(f"    Fields: {', '.join(secret_data.keys())}")

                    required_fields = ['host', 'port', 'username', 'password', 'dbname']
                    missing_fields = [f for f in required_fields if f not in secret_data]
                    if missing_fields:
                        print(f"  ✗ Missing fields in secret: {', '.join(missing_fields)}")
                        return False
                    return True
                except json.JSONDecodeError as e:
                    print(f"  ✗ Secret is not valid JSON: {e}")
                    return False
            else:
                print(f"  ✗ Secret exists but has no SecretString")
                return False
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"  ✗ Secret not found (check ARN)")
            elif e.response['Error']['Code'] == 'AccessDenied':
                print(f"  ✗ Access denied (check IAM permissions)")
            else:
                print(f"  ✗ Secrets Manager error: {e}")
            return False
    except ImportError:
        print(f"  ✗ boto3 not available")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False


def check_database_connection():
    """Try to connect to database."""
    print("\n=== DATABASE CONNECTION ===")

    try:
        import psycopg2
        from config.credential_manager import get_db_credentials

        try:
            creds = get_db_credentials()
            print(f"  ✓ Database credentials fetched")
            print(f"    Host: {creds['host']}")
            print(f"    Port: {creds['port']}")
            print(f"    User: {creds['user']}")
            print(f"    Database: {creds['database']}")

            # Try to connect
            print(f"\n  Attempting database connection...")
            conn = psycopg2.connect(
                host=creds['host'],
                port=creds['port'],
                user=creds['user'],
                password=creds['password'],
                database=creds['database'],
                sslmode='require',
                connect_timeout=5
            )
            print(f"  ✓ Database connection successful!")
            conn.close()
            return True
        except Exception as e:
            print(f"  ✗ Failed to connect to database: {e}")
            return False
    except ImportError as e:
        print(f"  ✗ Required module not available: {e}")
        return False


def main():
    """Run all diagnostic checks."""
    print("=" * 60)
    print("AWS LAMBDA DIAGNOSTIC")
    print("=" * 60)

    results = {
        'env_vars': check_environment_variables(),
        'boto3': check_boto3(),
    }

    if results['boto3']:
        results['secrets_manager'] = check_secrets_manager_access()
        if results['secrets_manager']:
            results['database'] = check_database_connection()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_pass = all(v if isinstance(v, bool) else v[0] for v in results.values())
    if all_pass:
        print("✓ All checks passed!")
        return 0
    else:
        print("✗ Some checks failed. Review output above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
