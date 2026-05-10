#!/usr/bin/env python3
"""
Centralized credential manager for stock algo platform.

Single source of truth for all credentials:
- Database (username, password)
- Alpaca API keys
- SMTP/email credentials
- Other third-party API keys

Supports two sources:
1. AWS Secrets Manager (production, AWS Lambda/ECS)
2. Environment variables (local development, .env.local)

Does NOT support:
- Hardcoded credentials
- Default empty strings for security-critical credentials
"""

import logging
import os
from typing import Dict, Optional, Any

log = logging.getLogger(__name__)


class CredentialManager:
    """Centralized credential fetcher with caching and failover."""

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._is_aws = self._detect_aws()
        self._secrets_client = None

    def _detect_aws(self) -> bool:
        """Check if running in AWS Lambda/ECS."""
        return bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"))

    def _get_secrets_client(self):
        """Lazy-load boto3 Secrets Manager client."""
        if self._secrets_client is None:
            try:
                import boto3
                self._secrets_client = boto3.client('secretsmanager',
                                                     region_name=os.getenv('AWS_REGION', 'us-east-1'))
            except ImportError:
                log.warning("boto3 not available; falling back to environment variables only")
                self._secrets_client = False  # sentinel: tried and failed
        return self._secrets_client if self._secrets_client else None

    def get_password(self, secret_name: str, default: Optional[str] = None) -> str:
        """
        Fetch a password/secret from Secrets Manager or environment.

        Args:
            secret_name: Name of the secret (e.g., 'db/password', 'alpaca/secret')
            default: Default value if not found (should be None for required secrets)

        Returns:
            The secret value

        Raises:
            ValueError: If secret not found and no default provided
        """
        return self._get_secret(secret_name, default, is_password=True)

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> str:
        """Alias for get_password (get_secret is more generic)."""
        return self.get_password(secret_name, default)

    def _get_secret(self, secret_name: str, default: Optional[str] = None, is_password: bool = False) -> str:
        """
        Internal secret retrieval with caching.

        Priority:
        1. Cache (if present)
        2. AWS Secrets Manager (if in AWS and available)
        3. Environment variable (env var name is secret_name with '/' → '_' and uppercase)
        4. Default value (if provided)
        5. Raise ValueError (if required and not found)
        """
        # Check cache first
        if secret_name in self._cache:
            return self._cache[secret_name]

        # Try Secrets Manager if in AWS
        if self._is_aws:
            secret = self._fetch_from_secrets_manager(secret_name)
            if secret:
                self._cache[secret_name] = secret
                return secret

        # Fall back to environment variable
        # Convert 'db/password' → 'DB_PASSWORD'
        env_var = secret_name.upper().replace('/', '_')
        secret = os.getenv(env_var)

        if secret:
            self._cache[secret_name] = secret
            return secret

        # Use default if provided
        if default is not None:
            return default

        # Fail if required and not found
        raise ValueError(
            f"Required credential '{secret_name}' not found in Secrets Manager or environment variable '{env_var}'. "
            f"Set {env_var} environment variable or add secret to AWS Secrets Manager."
        )

    def _fetch_from_secrets_manager(self, secret_name: str) -> Optional[str]:
        """Fetch from AWS Secrets Manager. Returns None if not found."""
        try:
            client = self._get_secrets_client()
            if not client:
                return None

            # Try to get the secret by name
            response = client.get_secret_value(SecretId=secret_name)
            secret_value = response.get('SecretString') or response.get('SecretBinary', '')
            return secret_value if secret_value else None

        except Exception as e:
            log.debug(f"Could not fetch '{secret_name}' from Secrets Manager: {e}")
            return None

    def get_db_credentials(self) -> Dict[str, Any]:
        """Get database connection credentials as a dict."""
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'user': self.get_password('db/username', default='stocks'),
            'password': self.get_password('db/password'),  # REQUIRED - no default
            'database': os.getenv('DB_NAME', 'stocks'),
        }

    def get_alpaca_credentials(self) -> Dict[str, str]:
        """Get Alpaca API credentials as a dict."""
        return {
            'key': self.get_password('alpaca/key', default=os.getenv('APCA_API_KEY_ID')),
            'secret': self.get_password('alpaca/secret', default=os.getenv('APCA_API_SECRET_KEY')),
        }

    def get_smtp_credentials(self) -> Optional[Dict[str, Any]]:
        """Get SMTP credentials. Returns None if not configured."""
        password = self.get_password('smtp/password', default=os.getenv('ALERT_SMTP_PASSWORD'))
        if not password:
            return None
        return {
            'username': os.getenv('ALERT_SMTP_USER', ''),
            'password': password,
            'host': os.getenv('ALERT_SMTP_HOST', ''),
            'port': int(os.getenv('ALERT_SMTP_PORT', '587')),
        }

    def clear_cache(self):
        """Clear credential cache (useful for testing)."""
        self._cache.clear()


# Singleton instance
_manager = None


def get_credential_manager() -> CredentialManager:
    """Get the global credential manager instance."""
    global _manager
    if _manager is None:
        _manager = CredentialManager()
    return _manager


def get_password(secret_name: str, default: Optional[str] = None) -> str:
    """Module-level convenience function."""
    return get_credential_manager().get_password(secret_name, default)


def get_secret(secret_name: str, default: Optional[str] = None) -> str:
    """Module-level convenience function (alias)."""
    return get_credential_manager().get_secret(secret_name, default)


def get_db_credentials() -> Dict[str, str]:
    """Module-level convenience function."""
    return get_credential_manager().get_db_credentials()


def get_alpaca_credentials() -> Dict[str, str]:
    """Module-level convenience function."""
    return get_credential_manager().get_alpaca_credentials()


if __name__ == "__main__":
    # Simple test: try to get credentials
    logging.basicConfig(level=logging.INFO)
    try:
        db_creds = get_db_credentials()
        print("[OK] DB credentials loaded")
    except ValueError as e:
        print(f"[ERROR] DB credentials: {e}")

    try:
        alpaca_creds = get_alpaca_credentials()
        if alpaca_creds['key']:
            print("[OK] Alpaca credentials loaded")
    except ValueError as e:
        print(f"[ERROR] Alpaca credentials: {e}")
