"""Dashboard credentials management for AWS and local API."""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class CredentialsProvider:
    """Handles AWS Secrets Manager, Terraform, and environment credentials."""

    @staticmethod
    def ensure_aws_profile() -> None:
        """Ensure AWS_PROFILE is set for AWS CLI operations."""
        if not os.getenv("AWS_PROFILE"):
            default_profile = "default"
            logger.debug(f"AWS_PROFILE not set; using '{default_profile}'")
            os.environ["AWS_PROFILE"] = default_profile

    @staticmethod
    def fetch_secrets_manager_credentials() -> tuple[str | None, str | None, str | None]:
        """Fetch dashboard credentials from AWS Secrets Manager.

        Returns: (dashboard_api_url, cognito_user_pool_id, cognito_client_id)
        """
        try:
            import json

            import boto3

            CredentialsProvider.ensure_aws_profile()
            secrets_client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))

            secret_name = os.getenv("DASHBOARD_SECRETS_NAME", "algo/dashboard-config")
            response = secrets_client.get_secret_value(SecretId=secret_name)

            if "SecretString" in response:
                secret = json.loads(response["SecretString"])
                return (
                    secret.get("api_url") or secret.get("dashboard_api_url"),
                    secret.get("cognito_user_pool_id"),
                    secret.get("cognito_user_pool_client_id") or secret.get("cognito_client_id"),
                )
        except Exception as e:
            logger.warning(f"Failed to fetch credentials from Secrets Manager: {e}")
        return None, None, None

    @staticmethod
    def fetch_terraform_credentials() -> tuple[str | None, str | None, str | None]:
        """Fetch dashboard credentials from Terraform outputs.

        Returns: (dashboard_api_url, cognito_user_pool_id, cognito_client_id)
        """
        try:
            tf_dir = CredentialsProvider._find_terraform_directory()
            if not tf_dir:
                return None, None, None

            if not CredentialsProvider._check_terraform_installed():
                return None, None, None

            if not CredentialsProvider._init_terraform(tf_dir):
                return None, None, None

            outputs = CredentialsProvider._get_terraform_outputs(tf_dir)
            if not outputs:
                return None, None, None

            return (
                CredentialsProvider._extract_tf_value(outputs, "dashboard_api_url"),
                CredentialsProvider._extract_tf_value(outputs, "cognito_user_pool_id"),
                CredentialsProvider._extract_tf_value(outputs, "cognito_client_id"),
            )
        except Exception as e:
            logger.warning(f"Failed to fetch credentials from Terraform: {e}")
        return None, None, None

    @staticmethod
    def _find_terraform_directory() -> str | None:
        """Find Terraform directory in repo root."""
        repo_root = Path(__file__).parent.parent.parent
        tf_dir = repo_root / "terraform"
        return str(tf_dir) if tf_dir.exists() else None

    @staticmethod
    def _check_terraform_installed() -> bool:
        """Check if Terraform is installed."""
        try:
            subprocess.run(["terraform", "--version"], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("Terraform not installed or not in PATH")
            return False

    @staticmethod
    def _init_terraform(tf_dir: str) -> bool:
        """Initialize Terraform directory."""
        try:
            subprocess.run(
                ["terraform", "init"],
                cwd=tf_dir,
                capture_output=True,
                check=True,
                timeout=60,
            )
            return True
        except Exception as e:
            logger.warning(f"Terraform init failed: {e}")
            return False

    @staticmethod
    def _get_terraform_outputs(tf_dir: str) -> dict | None:
        """Get Terraform outputs as JSON."""
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=tf_dir,
                capture_output=True,
                check=True,
                timeout=30,
                text=True,
            )
            import json
            return json.loads(result.stdout)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Failed to get Terraform outputs: {e}")
            return None

    @staticmethod
    def _extract_tf_value(outputs: dict, key: str) -> str | None:
        """Extract string value from Terraform output."""
        try:
            value = outputs.get(key, {}).get("value")
            return str(value) if value else None
        except Exception as e:
            logger.warning(f"Failed to extract Terraform value '{key}': {e}")
            return None

    @staticmethod
    def validate_api_url(url: str) -> bool:
        """Validate API URL format."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except Exception:
            return False
