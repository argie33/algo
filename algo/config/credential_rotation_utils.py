#!/usr/bin/env python3
"""
Credential Rotation Utilities

Manual credential management and rotation for:
- RDS database passwords
- API keys (Alpaca, SMTP)
- Testing rotation logic

Usage:
    python credential_rotation_utils.py rotate-rds-password
    python credential_rotation_utils.py rotate-alpaca-keys
    python credential_rotation_utils.py test-rotation
"""

import json
import logging
import os
import sys
import boto3
import psycopg2
import argparse
from typing import Dict, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class CredentialRotationManager:
    """Manage credential rotation for various AWS services."""

    def __init__(self, region: str = None, environment: str = "dev"):
        self.aws_region = region or os.getenv("AWS_REGION", "us-east-1")
        self.environment = environment
        self.secrets_client = boto3.client("secretsmanager", region_name=self.aws_region)
        self.rds_client = boto3.client("rds", region_name=self.aws_region)

    def get_secret(self, secret_name: str, stage: str = "AWSCURRENT") -> Dict:
        """Fetch secret from Secrets Manager."""
        try:
            response = self.secrets_client.get_secret_value(
                SecretId=secret_name,
                VersionStage=stage
            )
            return json.loads(response["SecretString"])
        except Exception as e:
            logger.error(f"Failed to fetch secret {secret_name}: {e}")
            raise

    def put_secret(self, secret_name: str, secret_value: Dict, stage: str = "AWSPENDING") -> str:
        """Store secret version in Secrets Manager."""
        try:
            response = self.secrets_client.put_secret_value(
                SecretId=secret_name,
                SecretString=json.dumps(secret_value),
                VersionStages=[stage]
            )
            logger.info(f"Created secret version {response['VersionId']} for {secret_name}")
            return response["VersionId"]
        except Exception as e:
            logger.error(f"Failed to put secret {secret_name}: {e}")
            raise

    def finish_rotation(self, secret_name: str, version_id: str) -> None:
        """Mark secret version as AWSCURRENT."""
        try:
            self.secrets_client.update_secret_version_stage(
                SecretId=secret_name,
                VersionStage="AWSCURRENT",
                MoveToVersionId=version_id
            )
            logger.info(f"Marked {version_id} as AWSCURRENT for {secret_name}")
        except Exception as e:
            logger.error(f"Failed to finish rotation: {e}")
            raise

    def rotate_rds_password(self, secret_name: str, db_instance_id: str, generate_new: bool = True) -> Dict:
        """
        Manually rotate RDS master password.

        Args:
            secret_name: Name of secret in Secrets Manager (e.g., "project-db-credentials-prod")
            db_instance_id: RDS instance identifier (e.g., "project-db")
            generate_new: If False, use password from user input
        """
        logger.info(f"Starting RDS password rotation for {db_instance_id}")

        try:
            # Get current credentials
            current_secret = self.get_secret(secret_name, "AWSCURRENT")
            logger.info(f"Current secret version: {current_secret.get('username')}@{current_secret.get('host')}")

            # Generate or get new password
            if generate_new:
                import secrets
                import string
                chars = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
                new_password = ''.join(secrets.choice(chars) for _ in range(32))
                logger.info(f"Generated new password (length: {len(new_password)})")
            else:
                new_password = input("Enter new password: ")

            # Update RDS password via AWS API
            logger.info(f"Updating RDS master password for {db_instance_id}...")
            self.rds_client.modify_db_instance(
                DBInstanceIdentifier=db_instance_id,
                MasterUserPassword=new_password,
                ApplyImmediately=True
            )
            logger.info("RDS password updated successfully")

            # Store new password in Secrets Manager
            new_secret = current_secret.copy()
            new_secret["password"] = new_password
            new_secret["rotated_at"] = datetime.utcnow().isoformat()

            self.put_secret(secret_name, new_secret, "AWSCURRENT")

            logger.info(f"✓ RDS password rotation completed for {db_instance_id}")

            return {
                "success": True,
                "secret_name": secret_name,
                "db_instance_id": db_instance_id,
                "rotated_at": new_secret["rotated_at"]
            }

        except Exception as e:
            logger.error(f"✗ RDS password rotation failed: {e}")
            return {"success": False, "error": str(e)}

    def rotate_alpaca_keys(self, secret_name: str, new_key_id: str = None, new_secret_key: str = None) -> Dict:
        """
        Manually rotate Alpaca API keys.

        Keys must be generated in Alpaca dashboard first.

        Args:
            secret_name: Name of secret in Secrets Manager (e.g., "project-algo-secrets-prod")
            new_key_id: New API key ID from Alpaca
            new_secret_key: New API secret key from Alpaca
        """
        logger.info(f"Starting Alpaca key rotation for {secret_name}")

        if not new_key_id or not new_secret_key:
            logger.error("Must provide both new_key_id and new_secret_key")
            return {"success": False, "error": "Missing credentials"}

        try:
            # Get current secret
            current_secret = self.get_secret(secret_name, "AWSCURRENT")

            # Create new secret with rotated keys
            new_secret = current_secret.copy()
            new_secret["APCA_API_KEY_ID"] = new_key_id
            new_secret["APCA_API_SECRET_KEY"] = new_secret_key
            new_secret["rotated_at"] = datetime.utcnow().isoformat()

            # Store in Secrets Manager
            self.put_secret(secret_name, new_secret, "AWSCURRENT")

            logger.info(f"✓ Alpaca key rotation completed for {secret_name}")
            logger.warning("Remember to delete old key from Alpaca dashboard: broker.alpaca.markets")

            return {
                "success": True,
                "secret_name": secret_name,
                "key_id": new_key_id[:10] + "***",  # Mask for security
                "rotated_at": new_secret["rotated_at"]
            }

        except Exception as e:
            logger.error(f"✗ Alpaca key rotation failed: {e}")
            return {"success": False, "error": str(e)}

    def test_rds_connection(self, secret_name: str, stage: str = "AWSCURRENT") -> bool:
        """Test connection to RDS with stored credentials."""
        try:
            secret = self.get_secret(secret_name, stage)

            logger.info(f"Testing RDS connection with {stage} credentials...")
            conn = psycopg2.connect(
                host=secret["host"],
                port=int(secret.get("port", 5432)),
                user=secret["username"],
                password=secret["password"],
                database="postgres",
                connect_timeout=5
            )
            cur = conn.cursor()
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            conn.close()

            logger.info(f"✓ Connection successful: {version.split(',')[0]}")
            return True

        except Exception as e:
            logger.error(f"✗ Connection failed: {e}")
            return False

    def view_rotation_history(self, secret_name: str) -> Dict:
        """Display rotation history for a secret."""
        try:
            response = self.secrets_client.describe_secret(SecretId=secret_name)

            logger.info(f"\nRotation History for {secret_name}:")
            logger.info(f"  ARN: {response['ARN']}")
            logger.info(f"  Created: {response['CreatedDate']}")

            if "RotationRules" in response and response["RotationEnabled"]:
                logger.info(f"  Rotation Enabled: Every {response['RotationRules'].get('AutomaticallyAfterDays', '?')} days")

            logger.info(f"\nVersion Stages:")
            for version_id, stages in response["VersionIdsToStages"].items():
                logger.info(f"  {version_id[:8]}...: {', '.join(stages)}")

            return response["VersionIdsToStages"]

        except Exception as e:
            logger.error(f"Failed to view rotation history: {e}")
            return {}

    def list_rotatable_secrets(self) -> list:
        """List all secrets with rotation enabled."""
        try:
            response = self.secrets_client.list_secrets(
                Filters=[{"Key": "name", "Values": [self.environment]}]
            )

            rotatable = []
            for secret in response.get("SecretList", []):
                if secret.get("RotationEnabled"):
                    rotatable.append({
                        "name": secret["Name"],
                        "arn": secret["ARN"],
                        "rotation_days": secret.get("RotationRules", {}).get("AutomaticallyAfterDays")
                    })

            logger.info(f"\nFound {len(rotatable)} secrets with rotation enabled:")
            for s in rotatable:
                logger.info(f"  {s['name']} (every {s['rotation_days']} days)")

            return rotatable

        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(description="Credential Rotation Utilities")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"), help="AWS region")
    parser.add_argument("--environment", default="dev", help="Environment (dev/staging/prod)")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # rotate-rds-password
    rds_parser = subparsers.add_parser("rotate-rds-password", help="Manually rotate RDS master password")
    rds_parser.add_argument("--secret-name", required=True, help="Secret name in Secrets Manager")
    rds_parser.add_argument("--db-instance-id", required=True, help="RDS instance ID")
    rds_parser.add_argument("--password", help="New password (if not provided, will be generated)")

    # rotate-alpaca-keys
    alpaca_parser = subparsers.add_parser("rotate-alpaca-keys", help="Manually rotate Alpaca API keys")
    alpaca_parser.add_argument("--secret-name", required=True, help="Secret name in Secrets Manager")
    alpaca_parser.add_argument("--key-id", required=True, help="New Alpaca key ID")
    alpaca_parser.add_argument("--secret-key", required=True, help="New Alpaca secret key")

    # test-connection
    test_parser = subparsers.add_parser("test-connection", help="Test RDS connection")
    test_parser.add_argument("--secret-name", required=True, help="Secret name in Secrets Manager")
    test_parser.add_argument("--stage", default="AWSCURRENT", help="Secret stage (AWSCURRENT/AWSPENDING)")

    # view-history
    history_parser = subparsers.add_parser("view-history", help="View rotation history")
    history_parser.add_argument("--secret-name", required=True, help="Secret name in Secrets Manager")

    # list-secrets
    subparsers.add_parser("list-secrets", help="List all rotatable secrets")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = CredentialRotationManager(region=args.region, environment=args.environment)

    if args.command == "rotate-rds-password":
        result = manager.rotate_rds_password(
            secret_name=args.secret_name,
            db_instance_id=args.db_instance_id,
            generate_new=(args.password is None)
        )
        print(json.dumps(result, indent=2))

    elif args.command == "rotate-alpaca-keys":
        result = manager.rotate_alpaca_keys(
            secret_name=args.secret_name,
            new_key_id=args.key_id,
            new_secret_key=args.secret_key
        )
        print(json.dumps(result, indent=2))

    elif args.command == "test-connection":
        success = manager.test_rds_connection(
            secret_name=args.secret_name,
            stage=args.stage
        )
        sys.exit(0 if success else 1)

    elif args.command == "view-history":
        manager.view_rotation_history(args.secret_name)

    elif args.command == "list-secrets":
        manager.list_rotatable_secrets()


if __name__ == "__main__":
    main()
