#!/usr/bin/env python3
"""
Credential Pipeline Verification Script

Verifies that the complete credentials pipeline is working:
1. PowerShell environment variables (local dev)
2. AWS Secrets Manager (production)
3. Lambda environment variables
4. Credential Manager integration
5. IAM roles and policies

Run this to diagnose credential setup issues before deployment.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Tuple, List

def check_mark(msg: str):
    return f"[OK] {msg}"

def error_mark(msg: str):
    return f"[ERROR] {msg}"

def warn_mark(msg: str):
    return f"[WARN] {msg}"

class CredentialAudit:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.successes: List[str] = []
        self.is_aws = bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"))
        self.is_lambda = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        self.is_ci = bool(os.getenv("CI"))

    def audit(self):
        """Run complete audit."""
        print("\n" + "=" * 70)
        print("CREDENTIAL PIPELINE AUDIT")
        print("=" * 70)

        print(f"\nEnvironment Detected:")
        print(f"  Local Dev: {not (self.is_aws or self.is_lambda or self.is_ci)}")
        print(f"  AWS: {self.is_aws}")
        print(f"  Lambda: {self.is_lambda}")
        print(f"  CI/CD: {self.is_ci}")

        self.check_environment_variables()
        self.check_credential_manager()
        self.check_aws_credentials()
        self.check_lambda_env_vars()
        self.print_results()

    def check_environment_variables(self):
        """Check required environment variables."""
        print("\n" + "-" * 70)
        print("1. ENVIRONMENT VARIABLES")
        print("-" * 70)

        # Database credentials
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_user = os.getenv("DB_USER", "stocks")
        db_name = os.getenv("DB_NAME", "stocks")
        db_password = os.getenv("DB_PASSWORD")

        if db_host:
            self.successes.append("DB_HOST is set")
            print(check_mark(f"DB_HOST = {db_host}"))
        else:
            self.errors.append("DB_HOST is not set (REQUIRED)")
            print(error_mark("DB_HOST is not set (REQUIRED)"))

        if db_port:
            print(check_mark(f"DB_PORT = {db_port}"))
        else:
            print(f"  DB_PORT = 5432 (default)")

        if db_user:
            print(f"  DB_USER = {db_user} (default: stocks)")

        if db_name:
            print(f"  DB_NAME = {db_name} (default: stocks)")

        if db_password:
            self.successes.append("DB_PASSWORD is set")
            print(check_mark("DB_PASSWORD is set"))
        elif not self.is_aws and not self.is_lambda:
            self.errors.append("DB_PASSWORD is not set (REQUIRED for local dev)")
            print(error_mark("DB_PASSWORD is not set (REQUIRED for local dev)"))
        else:
            # In Lambda, DB_PASSWORD comes from Secrets Manager via DB_SECRET_ARN
            print(warn_mark("DB_PASSWORD not in env (expected in Lambda - fetched from Secrets Manager)"))

        # AWS credentials
        aws_region = os.getenv("AWS_REGION")
        if aws_region:
            print(check_mark(f"AWS_REGION = {aws_region}"))
        elif self.is_lambda:
            self.warnings.append("AWS_REGION not set in Lambda (auto-detected)")
            print(warn_mark("AWS_REGION not set (Lambda auto-detects)"))
        else:
            print(f"  AWS_REGION not set")

        # Alpaca credentials (optional)
        alpaca_key = os.getenv("APCA_API_KEY_ID")
        alpaca_secret = os.getenv("APCA_API_SECRET_KEY")

        if alpaca_key and alpaca_secret:
            self.successes.append("Alpaca credentials are set")
            print(check_mark("Alpaca credentials configured"))
        else:
            self.warnings.append("Alpaca credentials not set (optional - needed for live trading)")
            print(warn_mark("Alpaca credentials not configured (optional - needed for trading)"))

        # Cognito (for Lambda)
        cognito_pool = os.getenv("COGNITO_USER_POOL_ID")
        cognito_client = os.getenv("COGNITO_CLIENT_ID")

        if self.is_lambda:
            if cognito_pool:
                print(check_mark(f"COGNITO_USER_POOL_ID = {cognito_pool}"))
            else:
                self.errors.append("COGNITO_USER_POOL_ID not set in Lambda")
                print(error_mark("COGNITO_USER_POOL_ID not set in Lambda"))

            if cognito_client:
                print(check_mark(f"COGNITO_CLIENT_ID = {cognito_client}"))
            else:
                self.errors.append("COGNITO_CLIENT_ID not set in Lambda")
                print(error_mark("COGNITO_CLIENT_ID not set in Lambda"))
        else:
            print(f"  COGNITO variables (Lambda only)")

        # Database Secret ARN (for Lambda)
        db_secret_arn = os.getenv("DB_SECRET_ARN")
        if self.is_lambda:
            if db_secret_arn:
                print(check_mark(f"DB_SECRET_ARN = {db_secret_arn}"))
            else:
                self.errors.append("DB_SECRET_ARN not set in Lambda")
                print(error_mark("DB_SECRET_ARN not set in Lambda"))
        else:
            print(f"  DB_SECRET_ARN (Lambda only)")

    def check_credential_manager(self):
        """Check Python credential manager."""
        print("\n" + "-" * 70)
        print("2. CREDENTIAL MANAGER")
        print("-" * 70)

        try:
            from config.credential_manager import get_credential_manager

            cm = get_credential_manager()
            self.successes.append("CredentialManager instantiated")
            print(check_mark("CredentialManager imported and instantiated"))

            # Try to get DB credentials
            try:
                db_creds = cm.get_db_credentials()
                if db_creds and isinstance(db_creds, dict):
                    host = db_creds.get("host")
                    user = db_creds.get("user")
                    print(check_mark(f"DB credentials loaded: {user}@{host}"))
                    self.successes.append("DB credentials loaded from CredentialManager")
            except ValueError as e:
                self.errors.append(f"CredentialManager DB credentials failed: {str(e)[:100]}")
                print(error_mark(f"DB credentials failed: {str(e)[:100]}"))

            # Try to get Alpaca credentials
            try:
                alpaca = cm.get_alpaca_credentials()
                if alpaca and alpaca.get("key"):
                    print(check_mark("Alpaca credentials loaded"))
                else:
                    print(warn_mark("Alpaca credentials not configured (optional)"))
            except Exception as e:
                print(warn_mark(f"Alpaca credentials failed (optional): {str(e)[:100]}"))

        except ImportError as e:
            self.errors.append(f"CredentialManager import failed: {e}")
            print(error_mark(f"CredentialManager import failed: {e}"))

    def check_aws_credentials(self):
        """Check AWS access and Secrets Manager."""
        print("\n" + "-" * 70)
        print("3. AWS CREDENTIALS & SECRETS MANAGER")
        print("-" * 70)

        try:
            import boto3

            # Try to get STS identity
            sts = boto3.client("sts", region_name=os.getenv("AWS_REGION", "us-east-1"))
            try:
                identity = sts.get_caller_identity()
                account = identity["Account"]
                arn = identity["Arn"]
                self.successes.append(f"AWS credentials valid")
                print(check_mark(f"AWS credentials valid: {arn}"))
            except Exception as e:
                self.warnings.append(f"AWS credentials not configured or invalid")
                print(warn_mark(f"AWS credentials not available: {str(e)[:100]}"))
                return

            # Try to access Secrets Manager
            region = os.getenv("AWS_REGION", "us-east-1")
            sm = boto3.client("secretsmanager", region_name=region)

            db_secret_arn = os.getenv("DB_SECRET_ARN")
            if db_secret_arn:
                try:
                    response = sm.get_secret_value(SecretId=db_secret_arn)
                    print(check_mark(f"Secrets Manager readable: {db_secret_arn[:50]}..."))
                    self.successes.append("Secrets Manager DB secret accessible")
                except Exception as e:
                    self.errors.append(f"Secrets Manager access failed: {str(e)[:100]}")
                    print(error_mark(f"Secrets Manager failed: {str(e)[:100]}"))
            else:
                print(f"  DB_SECRET_ARN not set (Lambda only)")

        except ImportError:
            print(warn_mark("boto3 not installed - skipping AWS checks"))

    def check_lambda_env_vars(self):
        """Check if running in Lambda and verify env vars."""
        print("\n" + "-" * 70)
        print("4. LAMBDA ENVIRONMENT VARIABLES")
        print("-" * 70)

        if self.is_lambda:
            print(check_mark("Running in Lambda"))

            required = [
                "DB_SECRET_ARN",
                "COGNITO_USER_POOL_ID",
                "COGNITO_CLIENT_ID",
                "NODE_ENV"
            ]

            for var in required:
                if os.getenv(var):
                    print(check_mark(f"{var} = {os.getenv(var)[:50]}"))
                else:
                    self.errors.append(f"Lambda env var missing: {var}")
                    print(error_mark(f"{var} not set"))
        else:
            print(f"  Not running in Lambda (local dev or CI)")

    def print_results(self):
        """Print audit results."""
        print("\n" + "=" * 70)
        print("AUDIT RESULTS")
        print("=" * 70)

        if self.successes:
            print(f"\n[OK] PASSED ({len(self.successes)}):")
            for msg in self.successes:
                print(f"  - {msg}")

        if self.warnings:
            print(f"\n[WARN] WARNINGS ({len(self.warnings)}):")
            for msg in self.warnings:
                print(f"  - {msg}")

        if self.errors:
            print(f"\n[ERROR] ERRORS ({len(self.errors)}):")
            for msg in self.errors:
                print(f"  - {msg}")
            print("\n" + "=" * 70)
            print("RECOMMENDATIONS:")
            print("=" * 70)
            print("\nFor local development:")
            print("  1. Set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD in PowerShell")
            print("  2. Run: python3 config/credential_validator.py")
            print("  3. See: LOCAL_CRED_SETUP.md for detailed instructions")
            print("\nFor GitHub Actions / Lambda:")
            print("  1. Set GitHub Secrets: AWS_ACCOUNT_ID, DB_SECRET_ARN, etc.")
            print("  2. Verify Terraform sets Lambda environment variables")
            print("  3. See: CREDENTIALS_SETUP.md for complete guide")
            sys.exit(1)
        else:
            print("\n" + "=" * 70)
            print("[OK] ALL CHECKS PASSED")
            print("=" * 70)
            sys.exit(0)


if __name__ == "__main__":
    audit = CredentialAudit()
    audit.audit()
