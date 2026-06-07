"""
Lambda Configuration Validator

Verifies all critical configuration at Lambda startup.
Run this as a pre-flight check before deploying.

Usage:
  python config_validator.py [--fix-report]
"""

import os
import sys
import json
from typing import Dict, List, Tuple

class ConfigValidator:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks: Dict[str, bool] = {}

    def check_db_host(self) -> bool:
        """Verify DB_HOST points to RDS Proxy (not direct RDS)."""
        db_host = os.getenv('DB_HOST', '').strip()

        if not db_host:
            self.errors.append('DB_HOST: Environment variable not set')
            return False

        # RDS Proxy endpoints must contain 'proxy'
        is_direct_rds = ('db-' in db_host and 'rds.amazonaws.com' in db_host and 'proxy' not in db_host.lower())
        is_proxy = 'proxy' in db_host.lower() and 'rds.amazonaws.com' in db_host
        is_localhost = db_host.startswith('localhost') or db_host.startswith('127.')

        if is_direct_rds:
            self.errors.append(f"DB_HOST: '{db_host}' appears to be DIRECT RDS, not RDS Proxy. Must use RDS Proxy for connection pooling.")
            return False

        if is_proxy or is_localhost:
            return True

        self.warnings.append(f"DB_HOST: '{db_host}' does not match known patterns. Verify it points to RDS Proxy.")
        return True

    def check_frontend_url(self) -> bool:
        """Verify FRONTEND_URL is set or CloudFront domain is in Secrets Manager."""
        frontend_url = os.getenv('FRONTEND_URL', '').strip()
        is_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ

        if not is_lambda:
            # Local dev - not required
            return True

        if frontend_url:
            if not frontend_url.startswith('https://') and not frontend_url.startswith('http://'):
                self.warnings.append(f"FRONTEND_URL: '{frontend_url}' should start with https:// or http://")
            return True

        # FRONTEND_URL not set, try CloudFront Secrets Manager
        try:
            import boto3
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            try:
                response = secrets_client.get_secret_value(SecretId='algo/cloudfront-domain')
                secret = response.get('SecretString', '').strip()
                if secret:
                    return True
                else:
                    self.errors.append("FRONTEND_URL and algo/cloudfront-domain: Both not set or empty")
                    return False
            except secrets_client.exceptions.ResourceNotFoundException:
                self.errors.append("FRONTEND_URL not set AND algo/cloudfront-domain secret not found in Secrets Manager")
                return False
        except ImportError:
            self.warnings.append("boto3 not available - cannot check Secrets Manager for CloudFront domain")
            return False
        except Exception as e:
            self.errors.append(f"Error checking Secrets Manager for CloudFront domain: {e}")
            return False

    def check_cognito_config(self) -> bool:
        """Verify Cognito configuration is complete if authentication is enabled."""
        user_pool_id = os.getenv('COGNITO_USER_POOL_ID', '').strip()

        # If no user pool ID, Cognito is not configured (OK in dev mode)
        if not user_pool_id:
            dev_bypass = os.getenv('DEV_BYPASS_AUTH', '').lower()
            if dev_bypass == 'true':
                self.warnings.append("Cognito: Not configured (DEV_BYPASS_AUTH=true). This is ONLY for development!")
                return True
            else:
                self.warnings.append("Cognito: Not configured (users will not be able to authenticate)")
                return True

        # Cognito is enabled - verify all required vars
        client_id = os.getenv('COGNITO_CLIENT_ID', '').strip()
        region = os.getenv('COGNITO_REGION', '').strip() or 'us-east-1'

        if not client_id:
            self.errors.append("COGNITO_CLIENT_ID: Required when COGNITO_USER_POOL_ID is set")
            return False

        return True

    def check_database_credentials(self) -> bool:
        """Verify database authentication is set."""
        db_user = os.getenv('DB_USER', '').strip()
        db_password = os.getenv('DB_PASSWORD', '').strip()
        db_secret_arn = os.getenv('DB_SECRET_ARN', '').strip()

        if not db_user:
            self.errors.append("DB_USER: Environment variable not set")
            return False

        if not db_password and not db_secret_arn:
            self.errors.append("DB_PASSWORD: Must be set OR DB_SECRET_ARN must point to Secrets Manager secret")
            return False

        return True

    def check_database_name(self) -> bool:
        """Verify database name is set."""
        db_name = os.getenv('DB_NAME', '').strip() or 'stocks'
        if db_name:
            return True

        self.warnings.append("DB_NAME: Not set, using default 'stocks'")
        return True

    def check_dev_mode(self) -> bool:
        """Verify development mode is correctly configured."""
        is_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ
        dev_bypass = os.getenv('DEV_BYPASS_AUTH', '').lower()

        if dev_bypass == 'true' and is_lambda:
            self.errors.append("DEV_BYPASS_AUTH: Set to 'true' in Lambda (production). Must be 'false' or unset in production!")
            return False

        if dev_bypass == 'true' and not is_lambda:
            self.warnings.append("DEV_BYPASS_AUTH: Set to 'true' (development mode). Auth will be bypassed.")

        return True

    def run_all_checks(self) -> bool:
        """Run all configuration checks."""
        self.checks['db_host'] = self.check_db_host()
        self.checks['frontend_url'] = self.check_frontend_url()
        self.checks['cognito_config'] = self.check_cognito_config()
        self.checks['database_credentials'] = self.check_database_credentials()
        self.checks['database_name'] = self.check_database_name()
        self.checks['dev_mode'] = self.check_dev_mode()

        return len(self.errors) == 0

    def print_report(self) -> None:
        """Print validation report."""
        print("\n" + "="*80)
        print("LAMBDA CONFIGURATION VALIDATION REPORT")
        print("="*80 + "\n")

        # Errors
        if self.errors:
            print("❌ CRITICAL ERRORS (must fix before deployment):")
            for i, error in enumerate(self.errors, 1):
                print(f"   {i}. {error}")
            print()

        # Warnings
        if self.warnings:
            print("⚠️  WARNINGS (may need attention):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"   {i}. {warning}")
            print()

        # Checks
        if self.checks:
            print("✅ CONFIGURATION CHECKS:")
            for check, passed in self.checks.items():
                status = "✓" if passed else "✗"
                print(f"   {status} {check.replace('_', ' ').title()}")
            print()

        # Summary
        all_passed = len(self.errors) == 0
        if all_passed:
            print("✅ ALL CHECKS PASSED - Configuration is valid!")
        else:
            print("❌ CONFIGURATION HAS ERRORS - See above for details")

        print("\n" + "="*80 + "\n")

        return all_passed

    def get_json_report(self) -> str:
        """Return validation report as JSON."""
        return json.dumps({
            'errors': self.errors,
            'warnings': self.warnings,
            'checks': self.checks,
            'all_passed': len(self.errors) == 0,
        }, indent=2)


def main():
    """Run configuration validator."""
    validator = ConfigValidator()
    all_passed = validator.run_all_checks()
    validator.print_report()

    # Return exit code
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
