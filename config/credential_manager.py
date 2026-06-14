#!/usr/bin/env python3
"""
Centralized credential manager for stock algo platform.

Single source of truth for all credentials:
- Database (username, password)
- Alpaca API keys
- SMTP/email credentials
- Other third-party API keys

Credential Sources (Priority Order):
1. Environment variables (CI, local development)
2. AWS Secrets Manager (production, AWS Lambda/ECS)

IMPORTANT: Credentials are NEVER loaded from .env files - all must be set via environment variables.

Does NOT support:
- Hardcoded credentials
- Default empty strings for security-critical credentials
"""

import json as _json
import logging
import os
import time
import threading
from typing import Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# Database defaults
DEFAULT_DB_PORT = "5432"
DEFAULT_DB_USER = "stocks"
DEFAULT_DB_NAME = "stocks"

# Cache TTL for credential secrets (5 minutes to balance freshness with API costs)
CREDENTIAL_CACHE_TTL_SECONDS = 300

class CredentialManager:
    """Centralized credential fetcher with caching and TTL-based expiration."""

    def __init__(self):
        self._cache: Dict[str, Tuple[str, float]] = {}  # key -> (value, timestamp)
        self._is_aws = self._detect_aws()
        self._secrets_client = None

    def _detect_aws(self) -> bool:
        """Check if running in AWS Lambda/ECS or if AWS mode is forced.

        Returns True if:
        - Running in Lambda/ECS (AWS_EXECUTION_ENV is set)
        - FORCE_AWS env var is explicitly set to true (allows local access to AWS Secrets Manager)
        """
        # Check if forced by env var (allows local dev to access AWS Secrets Manager)
        if os.getenv("FORCE_AWS", "").lower() in ("true", "1", "yes"):
            return True
        # Check if running in AWS Lambda/ECS
        return bool(os.getenv("AWS_EXECUTION_ENV"))

    def _get_secrets_client(self):
        """Lazy-load boto3 Secrets Manager client."""
        if self._secrets_client is None:
            try:
                import boto3
                import botocore.config
                # Timeouts for Secrets Manager API calls (must handle VPC latency).
                # VPC requests to Secrets Manager endpoint can take 5-10s on cold-start.
                # connect_timeout=10: Allow 10s for TCP handshake through NAT/endpoint
                # read_timeout=15: Allow 15s for full response (includes API processing)
                # max_attempts=2: 1 retry for transient failures (still under 30s total)
                _cfg = botocore.config.Config(connect_timeout=10, read_timeout=15,
                                              retries={'max_attempts': 2})
                self._secrets_client = boto3.client('secretsmanager',
                                                     region_name=os.getenv('AWS_REGION', 'us-east-1'),
                                                     config=_cfg)
            except ImportError:
                logger.warning("boto3 not available; falling back to environment variables only")
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
        Internal secret retrieval with caching and TTL-based expiration.

        Priority:
        1. Cache (if present and not expired)
        2. AWS Secrets Manager (if in AWS and available)
        3. Environment variable (env var name is secret_name with '/' → '_' and uppercase)
        4. Default value (if provided)
        5. Raise ValueError (if required and not found)
        """
        # Check cache with TTL
        if secret_name in self._cache:
            cached_value, timestamp = self._cache[secret_name]
            age = time.time() - timestamp
            if age < CREDENTIAL_CACHE_TTL_SECONDS:
                return cached_value
            else:
                # Cache expired, remove it and fetch fresh
                del self._cache[secret_name]

        # Try Secrets Manager if in AWS
        if self._is_aws:
            secret = self._fetch_from_secrets_manager(secret_name)
            if secret:
                self._cache[secret_name] = (secret, time.time())
                return secret

        # Fall back to environment variable
        env_var = secret_name.upper().replace('/', '_')
        secret = os.getenv(env_var)

        if secret:
            self._cache[secret_name] = (secret, time.time())
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
            logger.debug(f"Could not fetch '{secret_name}' from Secrets Manager: {e}")
            return None

    def get_db_credentials(self) -> Dict[str, Any]:
        """Get database connection credentials as a dict.

        In AWS Lambda the RDS secret is a JSON blob stored under the ARN given by
        DB_SECRET_ARN. We fetch and parse that blob rather
        than looking up individual secret names, which don't exist in this setup.
        Falls back to individual env vars for local dev.

        Result is cached in self._cache to avoid a Secrets Manager API call on every
        DatabaseContext creation (which is called 10+ times per orchestrator run).
        Cache uses TTL to ensure fresh credentials are fetched periodically.
        """
        import json as _json

        _DB_CREDS_CACHE_KEY = '__db_credentials__'
        if _DB_CREDS_CACHE_KEY in self._cache:
            cached_value, timestamp = self._cache[_DB_CREDS_CACHE_KEY]
            age = time.time() - timestamp
            if age < CREDENTIAL_CACHE_TTL_SECONDS:
                return cached_value

        secret_arn = os.getenv('DB_SECRET_ARN')
        if secret_arn and self._is_aws:
            try:
                client = self._get_secrets_client()
                if client:
                    response = client.get_secret_value(SecretId=secret_arn)
                    creds = _json.loads(response.get('SecretString', '{}'))
                    # Prefer DB_HOST env var (proxy endpoint set by Terraform) over
                    # the secret's host field (which may point to direct RDS endpoint).
                    db_host = os.getenv('DB_HOST') or os.getenv('DB_ENDPOINT') or creds.get('host')
                    if not db_host:
                        raise ValueError("DB_HOST not set in Secrets Manager or environment")
                    password = creds.get('password')
                    if not password:
                        raise ValueError("password not found in DB_SECRET_ARN")
                    result = {
                        'host': db_host,
                        'port': int(creds.get('port') or os.getenv('DB_PORT', '5432')),
                        'user': creds.get('username', 'stocks'),
                        'password': password,
                        'database': creds.get('dbname') or os.getenv('DB_NAME', 'stocks'),
                    }
                    self._cache[_DB_CREDS_CACHE_KEY] = (result, time.time())
                    return result
            except Exception as e:
                logger.warning("Failed to load DB credentials from secret ARN %s: %s — falling back to env vars", secret_arn, e)

        # DB_HOST is required - no localhost fallback for safety
        db_host = os.getenv('DB_HOST') or os.getenv('DB_ENDPOINT')
        if not db_host:
            raise ValueError("DB_HOST not set in environment. Set DB_HOST before using credential manager.")

        result = {
            'host': db_host,
            'port': int(os.getenv('DB_PORT', '5432')),
            'user': self.get_password('db/username', default='stocks'),
            'password': self.get_password('db/password'),
            'database': os.getenv('DB_NAME', 'stocks'),
        }
        self._cache[_DB_CREDS_CACHE_KEY] = (result, time.time())
        return result

    def get_alpaca_credentials(self, user_id: Optional[str] = None) -> Dict[str, str]:
        """Get Alpaca API credentials as a dict.

        Always fetches fresh credentials from Secrets Manager. Never returns cached/stale credentials
        for normal operation. Cache is only used as a last resort if all sources fail.

        Supports per-user credential isolation for multi-tenant trading.

        Args:
            user_id: Cognito sub (e.g., 'us-east-1_XJpLb9SKX:userid-12345'). If provided,
                     tries user-specific secret first before falling back to shared.

        Checks in order:
        1. User-specific secret: algo/alpaca/{user_id} (if user_id provided)
        2. ALGO_SECRETS_ARN env var → JSON blob (APCA_API_KEY_ID / APCA_API_SECRET_KEY fields)
        3. AWS Secrets Manager 'algo/alpaca' JSON blob (api_key, api_secret fields)
        4. Individual secrets 'alpaca/key' and 'alpaca/secret' (legacy)
        5. Environment variables APCA_API_KEY_ID and APCA_API_SECRET_KEY
        6. Last-resort: Cached credentials (only if all above fail)

        Raises ValueError if credentials not found from any source.
        """
        _ALPACA_CREDS_CACHE_KEY = '__alpaca_credentials__'

        # Step 1: Try user-specific secret if user_id provided
        if user_id and self._is_aws:
            try:
                client = self._get_secrets_client()
                if client:
                    user_secret_id = f"algo/alpaca/{user_id}"
                    try:
                        response = client.get_secret_value(SecretId=user_secret_id)
                        creds = _json.loads(response.get('SecretString', '{}'))
                        key = creds.get('api_key') or creds.get('APCA_API_KEY_ID')
                        secret = creds.get('api_secret') or creds.get('APCA_API_SECRET_KEY')
                        if key and secret:
                            logger.info(f"[CREDENTIALS] User-scoped Alpaca credentials loaded for {user_id}")
                            return {'key': key, 'secret': secret}
                    except client.exceptions.ResourceNotFoundException:
                        logger.debug(f"[CREDENTIALS] No user-specific Alpaca secret for {user_id}, falling back to shared")
                    except Exception as e:
                        logger.warning(f"[CREDENTIALS] Could not fetch user-specific Alpaca credentials for {user_id}: {e}")
            except Exception as e:
                logger.warning(f"[CREDENTIALS] Error trying user-specific Alpaca secret: {e}")

        # Step 2: Try ALGO_SECRETS_ARN (Terraform-managed secret: algo-algo-secrets-dev)
        # LIVE MODE EXCEPTION: ALGO_SECRETS_ARN always contains PAPER keys (hardcoded in deploy
        # workflow as ALPACA_API_KEY_ID). For live trading, skip this source and fall through to
        # algo/alpaca which is updated by update-credentials.yml -f trading_mode=live.
        algo_secrets_arn = os.getenv('ALGO_SECRETS_ARN')
        is_paper_mode = os.getenv('ALPACA_PAPER_TRADING', 'true').strip().lower() != 'false'
        if algo_secrets_arn and self._is_aws and is_paper_mode:
            try:
                client = self._get_secrets_client()
                if client:
                    response = client.get_secret_value(SecretId=algo_secrets_arn)
                    creds = _json.loads(response.get('SecretString', '{}'))
                    key = creds.get('APCA_API_KEY_ID')
                    secret = creds.get('APCA_API_SECRET_KEY')
                    if key and secret:
                        logger.info(f"[CREDENTIALS] Alpaca credentials loaded from ALGO_SECRETS_ARN (paper mode)")
                        return {'key': key, 'secret': secret}
                    else:
                        logger.warning(f"[CREDENTIALS] ALGO_SECRETS_ARN found but missing Alpaca key fields")
            except Exception as e:
                logger.error(f"[CREDENTIALS] Could not fetch Alpaca credentials from ALGO_SECRETS_ARN: {e}")
        elif algo_secrets_arn and self._is_aws and not is_paper_mode:
            logger.info("[CREDENTIALS] Live mode: skipping ALGO_SECRETS_ARN (contains paper keys), using algo/alpaca")

        # Step 3: Try 'algo/alpaca' JSON blob (legacy secrets module format)
        if self._is_aws:
            try:
                client = self._get_secrets_client()
                if client:
                    alpaca_secret_id = os.getenv('ALPACA_LEGACY_SECRET_ID', 'algo/alpaca')
                    response = client.get_secret_value(SecretId=alpaca_secret_id)
                    creds = _json.loads(response.get('SecretString', '{}'))
                    key = creds.get('api_key')
                    secret = creds.get('api_secret')
                    if key and secret:
                        return {'key': key, 'secret': secret}
            except Exception as e:
                logger.debug(f"Could not fetch 'algo/alpaca' from Secrets Manager: {e}")

        # Step 4: Fall back to individual secrets (legacy format)
        try:
            key = self.get_password('alpaca/key', default=None)
        except ValueError:
            key = os.getenv('APCA_API_KEY_ID')

        try:
            secret = self.get_password('alpaca/secret', default=None)
        except ValueError:
            secret = os.getenv('APCA_API_SECRET_KEY')

        if key and secret:
            logger.info(f"[CREDENTIALS] Alpaca credentials loaded successfully")
            return {'key': key, 'secret': secret}

        # FIX H-3: Secrets Manager completely unavailable - check cache before failing
        if _ALPACA_CREDS_CACHE_KEY in self._cache:
            cached_creds, timestamp = self._cache[_ALPACA_CREDS_CACHE_KEY]
            age = time.time() - timestamp
            # Use cache even if expired (last resort when Secrets Manager is down)
            logger.warning(f"[CREDENTIALS_H3_FALLBACK] Secrets Manager unavailable, using cached Alpaca credentials (age={age:.0f}s)")
            return cached_creds

        # No credentials found and no cache - fail hard
        logger.error("[CREDENTIALS] Alpaca credentials NOT FOUND - trades cannot be executed!")
        logger.error("[CREDENTIALS] Checked: ALGO_SECRETS_ARN, algo/alpaca secret, legacy secrets, env vars, and cache")
        logger.error("[CREDENTIALS] This error occurs when Secrets Manager is unreachable AND no cached credentials are available")
        raise ValueError(
            "Alpaca API credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) not found. "
            "Set these environment variables or configure 'algo/alpaca' secret in AWS Secrets Manager. "
            "If Secrets Manager is unreachable, check CloudWatch alarm [ALPACA_CREDS_FETCH_FAILED]."
        )

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
        """Clear credential cache (useful for testing or forcing a refresh)."""
        self._cache.clear()

    def clear_expired_credentials(self):
        """Remove expired credentials from cache without clearing everything."""
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if now - timestamp >= CREDENTIAL_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            del self._cache[key]

    def invalidate_alpaca_credentials(self):
        """FIX S-17: Clear cached Alpaca credentials when detected as invalid (e.g., 401 from API).

        Call this when Alpaca returns 401 Unauthorized to force a refetch on next request.
        Also emits CloudWatch metric for ops team to trigger manual rotation if needed.
        """
        _ALPACA_CREDS_CACHE_KEY = '__alpaca_credentials__'
        if _ALPACA_CREDS_CACHE_KEY in self._cache:
            cached_creds, timestamp = self._cache[_ALPACA_CREDS_CACHE_KEY]
            age = time.time() - timestamp
            logger.warning(
                f"[CREDENTIALS_INVALID] Alpaca credentials detected as invalid (401). "
                f"Clearing cache (credentials were {age:.0f}s old). Next request will refetch from Secrets Manager."
            )
            del self._cache[_ALPACA_CREDS_CACHE_KEY]

            # Emit CloudWatch alarm metric for ops to investigate credential rotation
            try:
                import boto3
                cloudwatch = boto3.client('cloudwatch', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                cloudwatch.put_metric_data(
                    Namespace='AlgoTradingPlatform',
                    MetricData=[
                        {
                            'MetricName': 'AlpacaCredentialsInvalidated',
                            'Value': 1,
                            'Unit': 'Count',
                        }
                    ]
                )
                logger.info("[CREDENTIALS_INVALID] CloudWatch metric emitted: AlpacaCredentialsInvalidated")
            except Exception as e:
                logger.warning(f"[CREDENTIALS_INVALID] Could not emit CloudWatch metric: {e}")
        else:
            logger.info("[CREDENTIALS_INVALID] Alpaca credentials not in cache (already cleared or never cached)")


# Singleton instance (thread-safe)
_manager = None
_manager_lock = threading.Lock()

def get_credential_manager() -> CredentialManager:
    """Get the global credential manager instance (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _manager
    if _manager is None:
        with _manager_lock:
            # Double-check pattern to avoid race conditions
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

def get_alpaca_credentials(user_id: Optional[str] = None) -> Dict[str, str]:
    """Module-level convenience function for Alpaca credentials.

    Args:
        user_id: Optional Cognito sub for user-scoped credentials.
                 If None, uses shared/default credentials.
    """
    return get_credential_manager().get_alpaca_credentials(user_id=user_id)

def get_db_password() -> str:
    """Get database password only.

    Replaces credential_helper.get_db_password() after consolidation.
    Uses DB_SECRET_ARN in AWS Lambda, falls back to environment variables.
    """
    creds = get_db_credentials()
    return creds['password']

def get_db_config() -> Dict[str, Any]:
    """Get full database configuration dict.

    Replaces credential_helper.get_db_config() after consolidation.
    Returns host, port, user, password, database.
    """
    return get_db_credentials()

def clear_credential_cache():
    """Clear the credential cache.

    Called at Lambda invocation start to ensure fresh credentials are fetched
    for each invocation. This is important for credential rotation: if a Lambda
    stays warm after credentials are rotated, we want to pick up the new ones
    on the next invocation.

    Safe to call even if no manager exists yet (creates fresh one).
    """
    mgr = get_credential_manager()
    mgr.clear_cache()
    return True

def clear_expired_credentials():
    """Remove only expired credentials from cache, keeping fresh ones.

    This is called at Lambda invocation start instead of clearing the entire cache.
    It respects the 5-minute TTL: credentials fresher than TTL are kept, stale ones
    are removed so they'll be refetched on next access. This balances credential
    rotation (stale creds are refreshed) with cost (we don't hit Secrets Manager
    on every invocation).
    """
    mgr = get_credential_manager()
    mgr.clear_expired_credentials()
    return True

def invalidate_alpaca_credentials():
    """FIX S-17: Clear cached Alpaca credentials when detected as invalid (e.g., 401 from API).

    Call this from trade executor when Alpaca returns 401 Unauthorized.
    Forces a refetch of credentials on next request.
    Also emits CloudWatch metric for ops team to investigate.
    """
    mgr = get_credential_manager()
    mgr.invalidate_alpaca_credentials()

if __name__ == "__main__":
    # Simple test: try to get credentials
    try:
        db_creds = get_db_credentials()
        logger.info("[OK] DB credentials loaded")
    except ValueError as e:
        logger.info(f"[ERROR] DB credentials: {e}")

    try:
        alpaca_creds = get_alpaca_credentials()
        if alpaca_creds['key']:
            logger.info("[OK] Alpaca credentials loaded")
    except ValueError as e:
        logger.info(f"[ERROR] Alpaca credentials: {e}")
