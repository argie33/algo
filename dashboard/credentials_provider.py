"""Dashboard credentials management for AWS and local API."""

import logging
import os
import subprocess
from pathlib import Path
from typing import cast

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
    def fetch_secrets_manager_credentials() -> tuple[str, str, str]:
        """Fetch dashboard credentials from AWS Secrets Manager.

        CRITICAL: Fails fast on any credential missing. No fallback behavior.
        Credentials are required for AWS mode — missing values are fatal errors.

        Returns: (dashboard_api_url, cognito_user_pool_id, cognito_client_id)
        Raises: RuntimeError if any credential missing or unavailable
        """
        import json

        import boto3

        CredentialsProvider.ensure_aws_profile()
        try:
            secrets_client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))

            secret_name = os.getenv("DASHBOARD_SECRETS_NAME", "algo/dashboard-config")
            response = secrets_client.get_secret_value(SecretId=secret_name)

            if "SecretString" not in response:
                raise RuntimeError(f"No SecretString in response from {secret_name}")

            secret = json.loads(response["SecretString"])

            # Try primary key first, then fallback to alternate name with explicit logging
            api_url = secret.get("api_url")
            if not api_url:
                api_url = secret.get("dashboard_api_url")
                if api_url:
                    logger.warning("[CREDS] Using fallback key 'dashboard_api_url' for API URL (primary 'api_url' missing)")
            if not api_url:
                raise RuntimeError(
                    f"dashboard_api_url not found in {secret_name}. "
                    f"Neither 'api_url' nor 'dashboard_api_url' keys are present. "
                    f"Check Secrets Manager configuration."
                )

            pool_id = secret.get("cognito_user_pool_id")
            if not pool_id:
                raise RuntimeError(f"cognito_user_pool_id not found in {secret_name}")

            # Try primary key first, then fallback to alternate name with explicit logging
            client_id = secret.get("cognito_user_pool_client_id")
            if not client_id:
                client_id = secret.get("cognito_client_id")
                if client_id:
                    logger.warning("[CREDS] Using fallback key 'cognito_client_id' for client ID (primary 'cognito_user_pool_client_id' missing)")
            if not client_id:
                raise RuntimeError(
                    f"cognito_client_id not found in {secret_name}. "
                    f"Neither 'cognito_user_pool_client_id' nor 'cognito_client_id' keys are present. "
                    f"Check Secrets Manager configuration."
                )

            return (api_url, pool_id, client_id)
        except RuntimeError:
            raise
        except Exception as e:
            msg = f"Failed to fetch dashboard credentials from Secrets Manager: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

    @staticmethod
    def fetch_terraform_credentials() -> tuple[str, str, str]:
        """Fetch dashboard credentials from Terraform outputs.

        CRITICAL: Fails fast. Raises RuntimeError if credentials cannot be obtained.
        No fallback behavior — missing Terraform credentials are a fatal error for AWS mode.

        Returns: (dashboard_api_url, cognito_user_pool_id, cognito_client_id)
        Raises: RuntimeError if Terraform unavailable or credentials missing
        """
        tf_dir = CredentialsProvider._find_terraform_directory()
        if not tf_dir:
            raise RuntimeError("Terraform directory not found. Credentials required for AWS mode.")

        if not CredentialsProvider._check_terraform_installed():
            raise RuntimeError("Terraform not installed. Credentials required for AWS mode.")

        try:
            if not CredentialsProvider._init_terraform(tf_dir):
                raise RuntimeError(f"Failed to initialize Terraform in {tf_dir}")

            outputs = CredentialsProvider._get_terraform_outputs(tf_dir)
            if not outputs:
                raise RuntimeError(f"No outputs from Terraform in {tf_dir}")

            api_url = CredentialsProvider._extract_tf_value(outputs, "dashboard_api_url")
            if not api_url:
                raise RuntimeError("dashboard_api_url not found in Terraform outputs")

            pool_id = CredentialsProvider._extract_tf_value(outputs, "cognito_user_pool_id")
            if not pool_id:
                raise RuntimeError("cognito_user_pool_id not found in Terraform outputs")

            client_id = CredentialsProvider._extract_tf_value(outputs, "cognito_client_id")
            if not client_id:
                raise RuntimeError("cognito_client_id not found in Terraform outputs")

            return (api_url, pool_id, client_id)
        except RuntimeError:
            raise
        except Exception as e:
            msg = f"Failed to fetch dashboard credentials from Terraform: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

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
    def _get_terraform_outputs(tf_dir: str) -> dict[str, object]:
        """Get Terraform outputs as JSON.

        Raises RuntimeError if outputs cannot be retrieved.
        """
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

            return cast(dict[str, object], json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Terraform output command failed: {e.stderr}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to get Terraform outputs: {e}") from e

    @staticmethod
    def _extract_tf_value(outputs: dict[str, object], key: str) -> str:
        """Extract string value from Terraform output.

        Raises RuntimeError if value missing or invalid.
        """
        try:
            if key not in outputs:
                raise RuntimeError(f"Key '{key}' not found in Terraform outputs")

            output_entry = outputs[key]
            if not isinstance(output_entry, dict):
                raise RuntimeError(f"Terraform output '{key}' is not a dict: {type(output_entry)}")

            value = output_entry.get("value")
            if not value:
                raise RuntimeError(f"No value found for Terraform output '{key}'")

            return str(value)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to extract Terraform value '{key}': {e}") from e

    @staticmethod
    def validate_api_url(url: str) -> bool:
        """Validate API URL format."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except Exception as e:
            logger.error(
                f"URL validation failed for API endpoint: {e}. "
                f"Cannot validate API URL format — check configuration."
            )
            raise RuntimeError(
                f"URL validation failed: {e}. "
                "API endpoint configuration is invalid. Cannot proceed."
            ) from e
